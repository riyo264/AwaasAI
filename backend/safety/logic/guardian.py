"""Guardian logic — elderly-alone triage + check-in-before-alarm.

Flow:
  evaluate_context (deterministic anomalies + vulnerability overlay)
    → situation + heightened vigilance when a vulnerable person is alone
    → collect the raised concerns
    → LLM triage: rank by danger, pick the ONE most dangerous + relevant,
      and choose the response — raise the alarm NOW (extreme) or gently CHECK IN
      with the person first (less serious) before escalating
    → deterministic guardrails: an extreme concern always auto-alarms and
      notifies family; the LLM can never downgrade it.

Reuses the safety narrator's Groq helper. Everything degrades gracefully to a
deterministic decision if the LLM is unavailable, so the Guardian never blocks.
"""
from __future__ import annotations

import base64
import json
import logging
from datetime import datetime, timezone

import httpx

from safety.app.config import get_settings
from safety.logic import context_service
from safety.logic.narrator import _call_groq
from safety.models.guardian import CheckinVerdict, GuardianConcern, GuardianDecision

logger = logging.getLogger(__name__)

GROQ_WHISPER_URL = "https://api.groq.com/openai/v1/audio/transcriptions"

# Concerns that are inherently an emergency for a vulnerable person alone —
# raise the alarm immediately, never "check in first". Note: we key on the
# TYPE of emergency (a fall, abnormal vitals, a very long silence, a gas/fire
# hazard) — NOT on raw severity, because the ×2 elderly escalation would push
# almost everything to "critical" and leave nothing to check in about.
_EXTREME_TYPES = {"sos", "health_alert", "global_inactivity"}
_GAS_HAZARD_TYPES = {"duration_exceeded", "device_active_too_long", "device_left_on"}
_SEV_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def _is_extreme(c) -> bool:
    if c.type in _EXTREME_TYPES:
        return True
    if c.type == "unsafe_at_night":
        return True  # an open door/window at night with a vulnerable person alone
    dev = (c.device or "").lower()
    if ("gas" in dev or "stove" in dev) and c.type in _GAS_HAZARD_TYPES:
        return True  # a burning stove for an elderly person alone is an emergency
    return False
_DISTRESS = ("help", "fallen", "fall", "can't", "cannot", "hurt", "pain", "chest",
             "dizzy", "breathe", "emergency", "bachao", "madad")

TRIAGE_SYSTEM = """You are "the Guardian" — a caring presence watching over a VULNERABLE person who
is HOME ALONE. A deterministic engine has raised the concerns below (already
escalated for how vulnerable the person is). Act like a sensible, loving adult in
the house. Always refer to the person BY NAME.

Your job:
1. Rank the concerns by real danger to the person (most → least).
2. Pick the SINGLE most dangerous AND most relevant concern to act on right now.
3. Choose the response AND match your TONE to it — this is important, the three
   levels must FEEL different:
   - "check_in"  → LOW/MEDIUM worry (a missed routine, a mildly unusual habit).
     TONE: WARM and GENTLE, a soft nudge — never alarming. You are just checking,
     they are probably fine. e.g. "Ramesh, I noticed you haven't taken your
     morning medicine yet — everything alright?"
   - "auto_alarm" for a HAZARD (gas/stove left on, an unsafe open door/window at
     night, a device running dangerously long, especially alongside another
     concern). TONE: FIRM and SERIOUS — name the danger plainly and state the
     protective action you are taking and that you're alerting family NOW. Notably
     more urgent than a check-in. e.g. "The gas stove has been left on far too
     long with Ramesh home alone — that's dangerous. I'm shutting it off and
     alerting the family right now."
   - "auto_alarm" for a MEDICAL EMERGENCY (an SOS/fall, abnormal vitals, a very
     long total silence). TONE: the GRAVEST urgency — immediate, decisive, no
     hesitation. e.g. "This is an emergency — Ramesh has pressed the SOS after a
     fall. I'm calling the family and emergency services this instant."
If the input contains "independent_layers_agree", two or more INDEPENDENT safety
layers (behavioral / environmental / vitals) point the same way. Signals that
corroborate each other are almost certainly real — treat the situation as more
serious than any single concern suggests, and say plainly that the signs agree
(e.g. "no movement from Ramesh AND the gas left burning").

4. Write:
   - "spoken": one or two sentences in the tone above. For auto_alarm, state
     what's wrong AND that you're alerting family. For check_in, a WARM question.
   - "checkin_prompt": the exact gentle question to ask the person (check_in only).
   - "explanation": a warm, plain-language 2-4 sentence explanation of WHY this
     matters for THIS person RIGHT NOW — connect it to how vulnerable they are,
     the routine or hazard involved, and WHY you chose to check in vs alarm. Speak
     like a caring family member explaining their thinking out loud. No jargon.
   - "family_message": a concise message to the family (used when alarming).

Never mention energy, cost, JSON, or internal field names. Return STRICT JSON:
{"danger_rank":["<type>",...],"flagged_type":"<type>","mode":"auto_alarm|check_in",
"spoken":"<line>","checkin_prompt":"<question|null>","explanation":"<why this matters>",
"notify_family":true|false,"family_message":"<message>","reason":"<why this concern>"}"""

CHECKIN_SYSTEM = """You are "the Guardian" for an elderly person home alone. You gently checked in
because of a concern, and they replied. Decide what to do.

- "stand_down" ONLY if the reply clearly reassures you they're fine (e.g. "I'm
  okay, just resting", "already took it"). Then give a warm acknowledgement.
- "escalate" if they express any distress, ask for help, mention a fall/pain, or
  the reply is empty/unclear. Then alert the family.

Also write "explanation": a warm 1-3 sentence account of WHY you decided to stand
down or escalate, based on what they said — like a caring family member. No jargon.

Return STRICT JSON:
{"verdict":"stand_down|escalate","spoken":"<your reply to them>",
"explanation":"<why you decided this>","notify_family":true|false,
"family_message":"<message to family|null>","reason":"<why>"}"""


def _situation(safety) -> tuple[str, bool, str]:
    """(situation, vigilance, person_name) from the SafetyAssessment."""
    if safety is None:
        return "occupied", False, "your family member"
    person = "your family member"
    if safety.most_vulnerable and safety.occupant_labels:
        person = safety.occupant_labels.get(safety.most_vulnerable, person)
    if safety.vulnerable_alone:
        kind = (safety.most_vulnerable_kind or "vulnerable").lower()
        return f"{kind}_alone", True, person
    if safety.occupants:
        return "occupied", False, person
    return "empty", False, person


def _rank_key(c: GuardianConcern) -> tuple[int, int]:
    return (1 if _is_extreme(c) else 0, _SEV_RANK.get(c.severity, 1))


def _fallback_explanation(person: str, flagged: GuardianConcern, mode: str) -> str:
    """A warm, plain-language 'why I think this' — used when the LLM is offline,
    so the reasoning still reads genuine (mirrors the pattern-engine narrator)."""
    detail = (flagged.detail or flagged.type.replace("_", " ")).rstrip(".")
    if mode == "auto_alarm":
        if flagged.type in {"sos", "health_alert"}:
            return (
                f"{person} is home alone and a direct health signal just fired — {detail}. "
                f"With no one else there to help, this can't wait for a check-in, so I'm "
                f"alerting the family and emergency contacts straight away."
            )
        if flagged.type == "unsafe_at_night":
            return (
                f"It's night and {person} is home alone with an entry point open — {detail}. "
                f"An open door or window overnight is a real security risk for someone "
                f"vulnerable, so I've secured it and let the family know."
            )
        if flagged.type == "global_inactivity":
            return (
                f"There's been no sign of {person} for a worrying stretch while they're home "
                f"alone. A long silence like this for a vulnerable person is exactly when a "
                f"quiet fall or fainting goes unnoticed — so I'm raising it now."
            )
        return (
            f"{person} is home alone and this is a genuine hazard — {detail}. On its own one "
            f"sign might wait, but here more than one thing points the same way, so I'm "
            f"acting on it now and keeping the family informed."
        )
    return (
        f"I noticed {detail}. It's very likely nothing — {person} may simply be resting or "
        f"running a little late — but because they're home alone I'd rather gently check than "
        f"assume. If they reassure me I'll stand down; if not, I'll bring the family in."
    )


async def _triage(concerns: list[GuardianConcern], situation: str, person: str,
                  now: datetime, language: str = "en", layers=None) -> dict | None:
    from safety.logic import lang
    settings = get_settings()
    payload = {
        "situation": situation,
        "person": person,
        "time": now.strftime("%H:%M"),
        "concerns": [
            {"type": c.type, "severity": c.severity, "detail": c.detail, "device": c.device}
            for c in concerns
        ],
    }
    if layers is not None and layers.corroborated:
        payload["independent_layers_agree"] = layers.headline
    return await _call_groq(TRIAGE_SYSTEM + lang.directive(language), json.dumps(payload), settings)


def _decision_shell(household_id: str, ctx, situation: str, vigilance: bool, person: str,
                    concerns: list[GuardianConcern]) -> GuardianDecision:
    s = ctx.safety
    return GuardianDecision(
        household_id=household_id, situation=situation, vigilance=vigilance, person=person,
        all_concerns=concerns,
        safety_status=(s.status.value if s else "safe"),
        safety_score=(s.safety_score if s else 100.0),
    )


async def assess(
    household_id: str,
    *,
    active_devices: list[str],
    people_home: dict | None,
    device_on_since: dict | None,
    now: datetime | None,
    profiles=None,
    extra_recent=None,
    ignore_stored_events: bool = False,
    healthy_baseline: bool = False,
    skip_completions: list[str] | None = None,
    language: str = "en",
) -> GuardianDecision:
    ctx = context_service.evaluate_context(
        household_id,
        active_devices=active_devices,
        people_home=people_home,
        device_on_since=device_on_since,
        now=now,
        profiles=profiles,
        extra_recent=extra_recent,
        ignore_stored_events=ignore_stored_events,
        healthy_baseline=healthy_baseline,
        skip_completions=skip_completions,
    )
    now = now or datetime.now(timezone.utc)
    situation, vigilance, person = _situation(ctx.safety)

    concerns = [
        GuardianConcern(
            type=a.type.value, device=a.device, severity=a.severity, detail=a.detail or "",
            base_severity=a.base_severity, vulnerability_factor=a.vulnerability_factor,
        )
        for a in ctx.anomalies
    ]
    decision = _decision_shell(household_id, ctx, situation, vigilance, person, concerns)
    # Defense-in-depth view (computed by the safety overlay) for display + the
    # corroboration escalation below.
    layers = ctx.safety.layers if ctx.safety else None
    decision.layers = layers

    if not concerns:
        decision.mode = "all_clear"
        decision.posture = "safe"
        decision.spoken = f"All calm — {person} is home and everything looks normal."
        return decision

    concerns_sorted = sorted(concerns, key=_rank_key, reverse=True)
    extreme = [c for c in concerns if _is_extreme(c)]

    # Cross-layer corroboration: independent layers agreeing (e.g. no movement
    # AND gas left on) is an emergency even if no single concern is "extreme".
    # Promote the worst concern into the extreme path so it auto-alarms.
    if not extreme and layers and layers.corroborated_emergency:
        extreme = [concerns_sorted[0]]
        decision.corroboration_promoted = True

    triage = await _triage(concerns, situation, person, now, language, layers=layers)
    decision.llm_powered = bool(triage)

    # LLM proposal (or deterministic fallback).
    if triage:
        decision.danger_rank = [t for t in triage.get("danger_rank", []) if isinstance(t, str)]
        flagged_type = triage.get("flagged_type")
        decision.reason = triage.get("reason", "")
        llm_spoken = (triage.get("spoken") or "").strip()
        llm_checkin = (triage.get("checkin_prompt") or "").strip() or None
        llm_family = (triage.get("family_message") or "").strip() or None
        llm_explanation = (triage.get("explanation") or "").strip() or None
        llm_mode = triage.get("mode")
    else:
        flagged_type = concerns_sorted[0].type
        decision.danger_rank = [c.type for c in concerns_sorted]
        llm_spoken = llm_checkin = llm_family = llm_explanation = llm_mode = None

    # ── Deterministic guardrails (safety floor) ──────────────────────────────
    if extreme:
        # An extreme concern ALWAYS auto-alarms + notifies family; the LLM can
        # never downgrade it or "check in first".
        flagged = sorted(extreme, key=_rank_key, reverse=True)[0]
        decision.mode = "auto_alarm"
        decision.posture = "emergency"
        decision.notify_family = True
        decision.flagged = flagged
        detail = flagged.detail or flagged.type.replace("_", " ")
        # A medical emergency gets the gravest tone; a hazard is serious but not
        # a medical alarm — so the two auto-alarm cases still sound different.
        if flagged.type in {"sos", "health_alert", "global_inactivity"}:
            default_spoken = (
                f"This is an emergency — {detail}. I'm calling {person}'s family "
                f"and emergency contacts right now."
            )
        else:
            default_spoken = (
                f"This is dangerous — {detail}. With {person} home alone, I'm "
                f"acting on it now and alerting the family immediately."
            )
        decision.spoken = llm_spoken or default_spoken
        decision.family_message = llm_family or (
            f"Emergency for {person}: {detail}. Please respond."
        )
    else:
        # Non-extreme → gently check in with the person BEFORE alarming anyone.
        flagged = next((c for c in concerns if c.type == flagged_type), concerns_sorted[0])
        decision.mode = "check_in"
        decision.posture = "concern" if flagged.severity in ("high", "critical") else "watchful"
        decision.flagged = flagged
        detail = flagged.detail or flagged.type.replace("_", " ")
        decision.checkin_prompt = llm_checkin or (
            f"{person}, I noticed {detail}. Are you doing okay? Just checking in — "
            f"no rush."
        )
        decision.spoken = llm_spoken or decision.checkin_prompt
        # No family notification yet — that's decided after the check-in reply.
        decision.notify_family = False
        decision.family_message = llm_family  # prepared, sent only if escalated

    # The genuine "why I think this" reasoning (LLM, else a caring fallback).
    decision.explanation = llm_explanation or _fallback_explanation(
        person, flagged, decision.mode
    )
    return decision


# ─── Check-in reply → verdict ────────────────────────────────────────────────


async def transcribe(audio_base64: str, fmt: str = "webm") -> str:
    s = get_settings()
    if not s.groq_api_key:
        return ""
    try:
        audio = base64.b64decode(audio_base64)
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                GROQ_WHISPER_URL,
                headers={"Authorization": f"Bearer {s.groq_api_key}"},
                files={"file": (f"reply.{fmt}", audio, f"audio/{fmt}")},
                data={"model": "whisper-large-v3-turbo", "response_format": "json"},
            )
        if resp.status_code != 200:
            logger.error("Whisper error %s: %s", resp.status_code, resp.text[:200])
            return ""
        return resp.json().get("text", "").strip()
    except Exception as e:  # pragma: no cover - network
        logger.error("Whisper failed: %s: %s", type(e).__name__, e)
        return ""


async def checkin_respond(person: str, concern_detail: str, reply_text: str,
                          language: str = "en") -> CheckinVerdict:
    from safety.logic import lang
    reply = (reply_text or "").strip()
    low = reply.lower()

    # Deterministic floor: explicit distress or no reply → escalate, no matter what.
    if not reply or any(w in low for w in _DISTRESS):
        base = CheckinVerdict(
            verdict="escalate",
            spoken=("Okay, I'm getting help right away." if reply else
                    "I didn't hear a response — I'm alerting the family now."),
            explanation=(
                f"{person} said something that worried me, so I'm not taking any chances — "
                f"I'm bringing the family in right away."
                if reply else
                f"{person} didn't answer my check-in. With them home alone, silence is exactly "
                f"when I should act rather than wait, so I'm alerting the family now."
            ),
            notify_family=True,
            family_message=f"{person} did not respond well to a check-in ({concern_detail}). Please check on them.",
            reason="distress or no response",
            transcript=reply,
        )
        return base

    settings = get_settings()
    payload = {"person": person, "concern": concern_detail, "reply": reply}
    res = await _call_groq(CHECKIN_SYSTEM + lang.directive(language), json.dumps(payload), settings)
    if isinstance(res, dict) and res.get("verdict") in ("stand_down", "escalate"):
        verdict = res["verdict"]
        return CheckinVerdict(
            verdict=verdict,
            spoken=(res.get("spoken") or "").strip() or (
                "Glad you're okay — I'll keep watch." if verdict == "stand_down"
                else "Alright, I'm letting the family know."),
            explanation=(res.get("explanation") or "").strip() or (
                f"{person} reassured me they're alright, so there's no need to worry the family — "
                f"I'll simply keep watching." if verdict == "stand_down"
                else f"{person}'s reply left me unsure they're okay, so I'd rather be safe and let "
                f"the family know."),
            notify_family=bool(res.get("notify_family")) or verdict == "escalate",
            family_message=(res.get("family_message") or None),
            reason=res.get("reason", ""),
            transcript=reply,
            llm_powered=True,
        )

    # Fallback: reassuring reply → stand down, else escalate.
    reassuring = any(w in low for w in ("fine", "okay", "ok", "good", "resting", "already", "took", "theek"))
    if reassuring:
        return CheckinVerdict(
            verdict="stand_down", spoken="Glad you're okay — I'll keep watch.",
            explanation=(f"{person} told me they're fine, so this was a false alarm — no need to "
                         f"worry the family. I'll keep a quiet eye out."),
            reason="reassuring reply", transcript=reply)
    return CheckinVerdict(
        verdict="escalate", spoken="I'll let the family know, just to be safe.",
        explanation=(f"{person}'s answer wasn't clearly reassuring, and with them home alone I'd "
                     f"rather err on the side of caution and bring the family in."),
        notify_family=True,
        family_message=f"{person} gave an unclear reply to a check-in ({concern_detail}).",
        reason="unclear reply", transcript=reply)
