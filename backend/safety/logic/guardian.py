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
    dev = (c.device or "").lower()
    if ("gas" in dev or "stove" in dev) and c.type in _GAS_HAZARD_TYPES:
        return True  # a burning stove for an elderly person alone is an emergency
    return False
_DISTRESS = ("help", "fallen", "fall", "can't", "cannot", "hurt", "pain", "chest",
             "dizzy", "breathe", "emergency", "bachao", "madad")

TRIAGE_SYSTEM = """You are "the Guardian" — a calm, caring presence watching over a VULNERABLE
person (an elderly person) who is HOME ALONE. A deterministic engine has raised
the concerns below (already escalated for vulnerability). Act like a sensible
adult in the house.

Your job:
1. Rank the concerns by real danger to the person (most → least).
2. Pick the SINGLE most dangerous AND most relevant concern to act on right now.
3. Choose the response:
   - "auto_alarm" for EXTREME situations — a fall/SOS, abnormal vitals, a very
     long silence, or a fire/gas hazard: raise the alarm and alert family at once.
   - "check_in" for LESS SERIOUS concerns — a missed medicine, a mildly unusual
     routine, a device left on: FIRST gently check on the person (they may be
     fine) before alarming anyone.
4. Write:
   - "spoken": for auto_alarm, a short urgent line stating what's wrong and that
     you're alerting family; for check_in, a WARM question to the person.
   - "checkin_prompt": the exact question to ask the person (check_in only).
   - "family_message": a concise message to the family (used when alarming).
Because the person is elderly and alone, lean cautious.

Return STRICT JSON:
{"danger_rank":["<type>",...],"flagged_type":"<type>","mode":"auto_alarm|check_in",
"spoken":"<line>","checkin_prompt":"<question|null>","notify_family":true|false,
"family_message":"<message>","reason":"<why this concern>"}"""

CHECKIN_SYSTEM = """You are "the Guardian" for an elderly person home alone. You gently checked in
because of a concern, and they replied. Decide what to do.

- "stand_down" ONLY if the reply clearly reassures you they're fine (e.g. "I'm
  okay, just resting", "already took it"). Then give a warm acknowledgement.
- "escalate" if they express any distress, ask for help, mention a fall/pain, or
  the reply is empty/unclear. Then alert the family.

Return STRICT JSON:
{"verdict":"stand_down|escalate","spoken":"<your reply to them>",
"notify_family":true|false,"family_message":"<message to family|null>",
"reason":"<why>"}"""


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


async def _triage(concerns: list[GuardianConcern], situation: str, person: str,
                  now: datetime, language: str = "en") -> dict | None:
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

    if not concerns:
        decision.mode = "all_clear"
        decision.posture = "safe"
        decision.spoken = f"All calm — {person} is home and everything looks normal."
        return decision

    concerns_sorted = sorted(concerns, key=_rank_key, reverse=True)
    extreme = [c for c in concerns if _is_extreme(c)]

    triage = await _triage(concerns, situation, person, now, language)
    decision.llm_powered = bool(triage)

    # LLM proposal (or deterministic fallback).
    if triage:
        decision.danger_rank = [t for t in triage.get("danger_rank", []) if isinstance(t, str)]
        flagged_type = triage.get("flagged_type")
        decision.reason = triage.get("reason", "")
        llm_spoken = (triage.get("spoken") or "").strip()
        llm_checkin = (triage.get("checkin_prompt") or "").strip() or None
        llm_family = (triage.get("family_message") or "").strip() or None
        llm_mode = triage.get("mode")
    else:
        flagged_type = concerns_sorted[0].type
        decision.danger_rank = [c.type for c in concerns_sorted]
        llm_spoken = llm_checkin = llm_family = llm_mode = None

    # ── Deterministic guardrails (safety floor) ──────────────────────────────
    if extreme:
        # An extreme concern ALWAYS auto-alarms + notifies family; the LLM can
        # never downgrade it or "check in first".
        flagged = sorted(extreme, key=_rank_key, reverse=True)[0]
        decision.mode = "auto_alarm"
        decision.posture = "emergency"
        decision.notify_family = True
        decision.flagged = flagged
        decision.spoken = llm_spoken or (
            f"Urgent — {flagged.detail or flagged.type.replace('_', ' ')}. "
            f"I'm alerting the family now."
        )
        decision.family_message = llm_family or (
            f"Emergency for {person}: {flagged.detail or flagged.type}. Please respond."
        )
    else:
        # Non-extreme → check in with the person BEFORE alarming.
        flagged = next((c for c in concerns if c.type == flagged_type), concerns_sorted[0])
        decision.mode = "check_in"
        decision.posture = "concern" if flagged.severity in ("high", "critical") else "watchful"
        decision.flagged = flagged
        decision.checkin_prompt = llm_checkin or (
            f"{person}, I noticed {flagged.detail or flagged.type.replace('_', ' ')}. "
            f"Is everything okay?"
        )
        decision.spoken = llm_spoken or decision.checkin_prompt
        # No family notification yet — that's decided after the check-in reply.
        decision.notify_family = False
        decision.family_message = llm_family  # prepared, sent only if escalated

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
            notify_family=bool(res.get("notify_family")) or verdict == "escalate",
            family_message=(res.get("family_message") or None),
            reason=res.get("reason", ""),
            transcript=reply,
            llm_powered=True,
        )

    # Fallback: reassuring reply → stand down, else escalate.
    reassuring = any(w in low for w in ("fine", "okay", "ok", "good", "resting", "already", "took", "theek"))
    if reassuring:
        return CheckinVerdict(verdict="stand_down", spoken="Glad you're okay — I'll keep watch.",
                              reason="reassuring reply", transcript=reply)
    return CheckinVerdict(verdict="escalate", spoken="I'll let the family know, just to be safe.",
                          notify_family=True,
                          family_message=f"{person} gave an unclear reply to a check-in ({concern_detail}).",
                          reason="unclear reply", transcript=reply)
