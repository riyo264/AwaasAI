"""LLM narrator — turns a detected :class:`ContextObject` into a natural,
spoken-style "Alexa says…" line for the frontend notification.

Design
======
* The deterministic pattern engine decides *what* is true (anomalies, context
  type). This module only decides *how to say it* in friendly language.
* Supports two LLM backends controlled by ``LLM_PROVIDER``:
  - ``"bedrock"`` — AWS Bedrock (Converse API) using the configured model.
  - ``"groq"`` — Groq (OpenAI-compatible chat completions).
* If the chosen provider errors / times out, we fall back to the other, then
  to a template sentence so the notification ALWAYS appears — the feature
  degrades gracefully and never blocks the UI.
* Pure function of the context object → easy to test and cache.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import functools
import boto3
import httpx

from safety.app.config import get_settings
from safety.models.context import ContextObject, ContextType

logger = logging.getLogger(__name__)

@functools.lru_cache(maxsize=1)
def _verify_ctx():
    """TLS verification for outbound LLM calls.

    Behind a corporate TLS-intercepting proxy the proxy's root CA lives in the
    OS trust store but NOT in certifi's bundle, so httpx's default verification
    fails with CERTIFICATE_VERIFY_FAILED and the narrator silently falls back to
    templated text. ``truststore`` builds an SSLContext backed by the OS trust
    store, fixing this. We scope it to the httpx client only (never the global
    ssl module) so boto3/DynamoDB is unaffected. Falls back to httpx's default
    (``True``) when truststore is unavailable or the platform has no OS store.
    """
    try:
        import ssl

        import truststore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except Exception:  # pragma: no cover - default verification is fine
        return True

SYSTEM_PROMPT = """You are Alexa, the guardian voice of a home SAFETY system that protects a
vulnerable person living at home (an elderly person, a child alone, a pregnant
woman alone, or someone unwell).

You are given a STRUCTURED CONTEXT describing the current state of the home: the
time, who is home and how vulnerable they are, any safety/health/security issues
a deterministic engine detected, and the routines those issues relate to.

This is a SAFETY net, NOT an energy or convenience assistant. NEVER talk about
saving energy, electricity, kilowatt-hours, money, or bills. Only talk about
SAFETY, HEALTH, and WELLBEING.

You ACT — you do not ask permission. When something is unsafe, Alexa takes the
protective action itself and states it plainly. NEVER say "Would you like me
to…", "Want me to…", or "Shall I…". Instead say what you ARE doing
("I'm turning off the gas now", "I'm alerting the family", "I've closed the
window and locked it").

Produce TWO things, returned as a JSON object:

1. "alexa_response": ONE or TWO short, clear, calm-but-urgent sentences spoken
   out loud RIGHT NOW. State the danger briefly, then state the protective
   ACTION Alexa is taking. Match urgency to severity:
     - CRITICAL / EMERGENCY (SOS, abnormal vitals, gas left on, prolonged total
       inactivity): urgent and decisive. Example:
       "This is an emergency — Grandpa pressed the SOS. I'm calling the family
        and emergency contacts right now."
       "The gas stove has been left on far too long — that's dangerous. I'm
        shutting off the gas and alerting the family."
     - HIGH (open door/window at night for someone vulnerable, abnormal
       inactivity): firm and protective. Example:
       "The front door has been open late at night with Meera home alone — I've
        locked it and notified the family."
     - If everything is safe, give a brief, reassuring all-clear.

2. "explanation": a longer paragraph (3-5 sentences) explaining WHY this is a
   safety concern — connect the current state to the person's vulnerability and
   the learned routine, and say WHY it is dangerous and what you did about it.

Rules for BOTH fields:
- This is SAFETY only. NEVER mention energy, kilowatt-hours, watts, cost, money,
  or savings. NEVER ask the user to do something — Alexa does it.
- Use ONLY facts provided. NEVER invent vitals or figures.
- Sound human, calm, and protective — urgent when it's serious, never flippant.
- NEVER mention JSON, "anomaly", "pattern", "confidence", or internal field names.
- Refer to people and devices in plain words: grandpa_activity -> "Grandpa",
  bedroom_window -> "the bedroom window", kitchen_gas_stove -> "the gas stove",
  grandpa_wearable -> "Grandpa's wearable".

Respond with a JSON object exactly like:
{"alexa_response": "...", "explanation": "..."}"""


# Rough typical power draw (watts) per device kind, used only to give the LLM a
# grounded energy estimate to mention. Approximate household figures — good
# enough for a "you could save ~X kWh" nudge, never billed against anything.
_DEVICE_WATTS = {
    "fan": 60,
    "light": 15,
    "ac": 1500,
    "tv": 100,
    "motor": 750,
    "door": 0,
    "tube": 40,
    # Indian-context appliances
    "stove": 1200,
    "kettle": 1500,
    "inverter": 800,
    "clothesline": 0,
}


def _device_watts(device_id: str) -> int:
    kind = (device_id or "").split("_")[-1]
    return _DEVICE_WATTS.get(kind, 50)




def _humanize_device(device_id: str) -> str:
    """son_room_fan -> "son's room fan"; water_motor -> "water motor".

    Reads the id as ``<location...>_<device>`` and renders it in natural word
    order without awkward duplicated words.
    """
    if not device_id:
        return "device"
    parts = device_id.split("_")
    device = parts[-1]
    location_tokens = parts[:-1]
    pretty_device = {
        "fan": "fan",
        "light": "light",
        "ac": "air conditioner",
        "tv": "TV",
        "motor": "motor",
        "door": "door",
        "presence": "presence sensor",
        "stove": "gas stove",
        "kettle": "kettle",
        "inverter": "inverter",
        "clothesline": "clothesline",
    }.get(device, device)
    location = " ".join(location_tokens).replace("son", "son's").strip()
    return f"{location} {pretty_device}".strip() if location else pretty_device


# Friendly names for the people/roles behind activity, presence and medicine
# sensors (``grandpa_activity`` -> "Grandpa", ``maid_presence`` -> "the house
# helper", ``grandma_medicine`` -> "Grandma's medicine").
_PERSON_LABELS = {
    "grandpa": "Grandpa",
    "grandfather": "Grandpa",
    "grandma": "Grandma",
    "grandmother": "Grandma",
    "son": "your son",
    "daughter": "your daughter",
    "mother": "Mom",
    "father": "Dad",
    "maid": "the house helper",
    "helper": "the house helper",
    "cook": "the cook",
    "driver": "the driver",
    "caretaker": "the caretaker",
}


def _person_label(token: str) -> str:
    token = (token or "").strip().lower()
    return _PERSON_LABELS.get(token, token.replace("-", " ").title() or "someone")


def _humanize_subject(device_id: str) -> str:
    """Render a people-/care-centric sensor id as a natural subject.

    Falls back to :func:`_humanize_device` for ordinary electrical devices so
    the narrator can call this uniformly for any anomaly.
    """
    if not device_id:
        return "someone"
    for suffix in ("_activity", "_presence"):
        if device_id.endswith(suffix):
            return _person_label(device_id[: -len(suffix)])
    if device_id.endswith("_medicine"):
        return f"{_person_label(device_id[: -len('_medicine')])}'s medicine"
    return _humanize_device(device_id)


def _fallback_line(context: ContextObject) -> str:
    """Deterministic, no-network Alexa sentence built straight from the context."""
    anomalies = context.anomalies or []
    if not anomalies:
        return "Everything looks normal at home right now. I'll keep an eye on things."

    # Lead with the highest-severity anomaly, summarise the rest.
    leads = []
    for a in anomalies[:2]:
        dev = _humanize_device(a.device or "")
        subj = _humanize_subject(a.device or "")
        if a.type.value == "device_left_on":
            leads.append(f"the {dev} was left on")
        elif a.type.value == "duration_exceeded":
            leads.append(f"the {dev} has been running dangerously long")
        elif a.type.value == "device_active_too_long":
            leads.append(f"the {dev} has been left running far too long")
        elif a.type.value == "missed_routine":
            leads.append(f"the {dev} didn't run at its usual time")
        elif a.type.value == "inactivity":
            leads.append(f"there's been no sign of {subj}'s usual activity")
        elif a.type.value == "missed_arrival":
            leads.append(f"{subj} hasn't returned home at the usual time")
        elif a.type.value == "missed_medicine":
            leads.append(f"{subj}'s medicine was missed")
        elif a.type.value == "unexpected_activity":
            leads.append(f"someone was active outside the usual schedule")
        elif a.type.value == "global_inactivity":
            leads.append("there's been no activity in the home for a worryingly long time")
        elif a.type.value == "unsafe_at_night":
            leads.append(f"the {dev} is open in the middle of the night")
        elif a.type.value == "health_alert":
            leads.append("a health reading is abnormal")
        elif a.type.value == "sos":
            leads.append("an SOS has been triggered")
        else:
            leads.append(f"something is unsafe with the {dev}")

    joined = " and ".join(leads)
    # SAFETY tone: Alexa states the danger and the protective ACTION it is taking.
    # It never asks permission and never mentions energy/cost.
    types = {a.type.value for a in anomalies}
    if "sos" in types:
        return f"This is an emergency — {joined}. I'm alerting the family and emergency contacts right now."
    if "health_alert" in types:
        return f"This needs urgent attention — {joined}. I'm notifying the family and emergency contacts immediately."
    if "global_inactivity" in types:
        return f"I'm concerned — {joined}. I'm checking in and alerting the family now."
    if types & {"duration_exceeded", "device_active_too_long"} and any(
        (a.device or "").endswith(("gas_stove", "_motor")) for a in anomalies
    ):
        return f"This is dangerous — {joined}. I'm shutting it off and notifying the family."
    if "unsafe_at_night" in types:
        return f"For safety, {joined}. I've secured it and notified the family."
    if "unexpected_activity" in types:
        return f"Something's not right — {joined}. I'm checking the cameras and alerting the family."
    if types & {"inactivity", "missed_arrival", "missed_medicine"}:
        return f"I'm watching out — {joined}. I'm sending a reminder and letting the family know."
    return f"For safety, {joined}. I'm taking care of it and keeping the family informed."


def _pattern_time_for_device(context: ContextObject, device: str) -> str | None:
    """The clock time of the routine most relevant to ``device``, if known."""
    for p in context.relevant_patterns or []:
        if p.time and device and device in (p.description or ""):
            return p.time
    return None


def _fallback_explanation(context: ContextObject) -> str:
    """Deterministic, no-network 'why' paragraph built from the context.

    Mirrors what the LLM would explain: ties the current clock + device state to
    the learned routine for each detected issue.
    """
    anomalies = context.anomalies or []
    now = context.current_time
    if not anomalies:
        on = ", ".join(_humanize_device(d) for d in (context.active_devices or []))
        on_part = f" The devices currently on ({on}) all match the usual routine for this time." if on else ""
        return (
            f"As of {now}, nothing stands out. I compared what's happening now "
            f"against the routines this home usually follows and everything lines "
            f"up.{on_part} I'll keep watching and let you know if anything changes."
        )

    sentences: list[str] = []
    for a in anomalies:
        dev = _humanize_device(a.device or "")
        subj = _humanize_subject(a.device or "")
        when = _pattern_time_for_device(context, a.device or "")
        if a.type.value == "device_left_on":
            usual = f" Normally it's switched off around {when}." if when else ""
            sentences.append(
                f"The {dev} is still on at {now}.{usual} Since it's well past the "
                f"usual time, it looks like it was left on by mistake."
            )
        elif a.type.value == "duration_exceeded":
            sentences.append(
                f"The {dev} has been running far longer than it normally does, "
                f"which usually means it was forgotten or something is off."
            )
        elif a.type.value == "device_active_too_long":
            sentences.append(
                f"The {dev} has been on for an unusually long stretch with no sign "
                f"of being turned off."
            )
        elif a.type.value == "missed_routine":
            usual = f" It usually runs around {when}." if when else ""
            sentences.append(
                f"The {dev} hasn't run yet today.{usual} Since that time has "
                f"passed, it may have been skipped."
            )
        elif a.type.value == "inactivity":
            usual = f" {subj} is usually active around {when}." if when else ""
            sentences.append(
                f"I haven't noticed {subj}'s usual activity yet today.{usual} "
                f"Since that time has passed without any sign, it seemed worth a "
                f"gentle check-in."
            )
        elif a.type.value == "missed_arrival":
            usual = f" {subj} usually gets home around {when}." if when else ""
            sentences.append(
                f"{subj} hasn't returned home yet.{usual} As that time has gone "
                f"by, you may want to check in."
            )
        elif a.type.value == "missed_medicine":
            usual = f" The dose is usually taken around {when}." if when else ""
            sentences.append(
                f"{subj} hasn't been confirmed today.{usual} A quick reminder "
                f"might help."
            )
        elif a.type.value == "unexpected_activity":
            usual = f" The usual time for this is around {when}." if when else ""
            sentences.append(
                f"{subj} was active at an unusual hour today.{usual} Because it "
                f"falls well outside the normal schedule, it stood out as worth "
                f"a look."
            )
        elif a.type.value == "global_inactivity":
            sentences.append(
                "I haven't detected any activity in the home for a long stretch "
                "while someone is meant to be there. With an elderly member home, "
                "a prolonged silence like this is worth checking on right away."
            )
        elif a.type.value == "unsafe_at_night":
            sentences.append(
                f"The {dev} is open during the night.{(' Normally it is closed by ' + when + '.') if when else ''} "
                f"An open entry point overnight is a security risk, especially "
                f"with a vulnerable person at home."
            )
        elif a.type.value == "health_alert":
            sentences.append(
                "A reading from the wearable is outside its safe range. Health "
                "signals like this are treated as urgent so the family can act "
                "quickly."
            )
        elif a.type.value == "sos":
            sentences.append(
                "An SOS was triggered at home. This is the highest-priority "
                "signal — it means someone is asking for help."
            )
        else:
            sentences.append(f"Something looks off with the {dev}.")

    intro = (
        "Here's why this matters for safety: I compare what's happening right now "
        "against the routines this home usually follows, and weigh it by how "
        "vulnerable the person at home is. "
    )
    outro = " I've taken the protective step and kept the family informed."
    return intro + " ".join(sentences) + outro


def _hhmm_to_min(hhmm: str) -> int | None:
    try:
        h, m = hhmm.strip().split(":")
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return None


def _fmt_hours(minutes: float) -> str:
    """45 -> '45 minutes'; 150 -> '2.5 hours'."""
    if minutes < 60:
        return f"{int(round(minutes))} minutes"
    hrs = minutes / 60.0
    return f"{hrs:.1f} hours"


def _fmt_energy(wh: float) -> str:
    """Watt-hours -> a friendly 'X kWh' / 'Y watt-hours' string."""
    if wh >= 1000:
        return f"{wh / 1000:.2f} kilowatt-hours"
    return f"{int(round(wh))} watt-hours"


def _energy_facts(context: ContextObject) -> list[str]:
    """Grounded timing + energy facts the LLM can quote in the main message.

    Built deterministically from the context so the numbers are real (not
    hallucinated): how long a device has been on / past its usual time, and the
    estimated energy that could be saved by switching it off now.
    """
    facts: list[str] = []
    now_min = _hhmm_to_min(context.current_time or "")

    # Map device -> the usual clock time of its most relevant routine.
    usual_time: dict[str, str] = {}
    for p in context.relevant_patterns or []:
        if p.time and p.description:
            for a in context.anomalies or []:
                if a.device and a.device in p.description:
                    usual_time.setdefault(a.device, p.time)

    for a in context.anomalies or []:
        dev_id = a.device or ""
        dev = _humanize_device(dev_id)
        watts = _device_watts(dev_id)
        detail = a.detail or ""

        if a.type.value == "device_left_on":
            off = re.search(r"(\d{1,2}:\d{2})", detail)
            off_min = _hhmm_to_min(off.group(1)) if off else None
            if off_min is not None and now_min is not None and now_min > off_min:
                past = now_min - off_min
                wh = watts * (past / 60.0)
                facts.append(
                    f"{dev} ({dev_id}): usually switched off by {off.group(1)}; "
                    f"it's now {context.current_time}, about {_fmt_hours(past)} past that. "
                    f"At ~{watts} W, roughly {_fmt_energy(wh)} could be saved by "
                    f"turning it off now."
                )
            else:
                facts.append(f"{dev} ({dev_id}): on past its usual off-time. ~{watts} W.")

        elif a.type.value == "duration_exceeded":
            run = re.search(r"running\s+(\d+)\s*min", detail)
            usual = re.search(r"usual\s*~?\s*(\d+)\s*min", detail)
            if run:
                ran = int(run.group(1))
                wh = watts * (ran / 60.0)
                start = usual_time.get(dev_id)
                since = f" (on since around {start})" if start else ""
                usual_part = f", about {int(round(ran / int(usual.group(1))))}x its usual {usual.group(1)}-minute cycle" if usual else ""
                facts.append(
                    f"{dev} ({dev_id}): running for {_fmt_hours(ran)}{since}{usual_part}. "
                    f"At ~{watts} W, about {_fmt_energy(wh)} used so far."
                )

        elif a.type.value == "device_active_too_long":
            facts.append(
                f"{dev} ({dev_id}): on for an unusually long stretch. ~{watts} W; "
                f"turning it off would stop further waste."
            )

        elif a.type.value == "missed_routine":
            when = usual_time.get(dev_id)
            when_part = f" (usually around {when})" if when else ""
            facts.append(
                f"{dev} ({dev_id}): expected to run earlier today{when_part} but "
                f"hasn't yet as of {context.current_time}."
            )

        elif a.type.value in ("inactivity", "missed_arrival", "missed_medicine"):
            subj = _humanize_subject(dev_id)
            when = usual_time.get(dev_id)
            when_part = f" around {when}" if when else ""
            verb = {
                "inactivity": "is usually active",
                "missed_arrival": "usually returns home",
                "missed_medicine": "is usually taken",
            }[a.type.value]
            facts.append(
                f"{subj} ({dev_id}): {verb}{when_part}, but nothing has been seen "
                f"today as of {context.current_time}."
            )

        elif a.type.value == "unexpected_activity":
            subj = _humanize_subject(dev_id)
            # detail already embeds the observed + usual times.
            facts.append(f"{subj} ({dev_id}): {detail}")

    return facts


def _build_user_message(context: ContextObject) -> str:
    """Compact, readable summary of the SAFETY context for the LLM."""
    lines = [
        f"Time: {context.current_time}",
        f"Context type: {context.context_type.value}",
    ]

    # Who is home + how vulnerable they are drives the whole safety judgement.
    safety = context.safety
    if safety:
        if safety.occupant_labels:
            parts = []
            for pid, name in safety.occupant_labels.items():
                kind = safety.most_vulnerable_kind if pid == safety.most_vulnerable else "adult"
                parts.append(f"{name} ({kind})")
            lines.append(f"People home (refer to them by NAME): {', '.join(parts)}")
        elif safety.occupants:
            lines.append(f"People home: {', '.join(safety.occupants)}")
        if safety.most_vulnerable:
            name = (safety.occupant_labels or {}).get(
                safety.most_vulnerable, safety.most_vulnerable
            )
            kind = safety.most_vulnerable_kind or "vulnerable"
            alone = " and is home ALONE" if safety.vulnerable_alone else " (with support)"
            lines.append(
                f"Most vulnerable person home: {name} ({kind}){alone}. "
                f"Speak about THIS person by name."
            )
        lines.append(
            f"Home safety status: {safety.status.value} "
            f"(safety score {safety.safety_score}/100)."
        )
    else:
        people = [p for p, home in (context.people_home or {}).items() if home]
        if people:
            lines.append(f"People home: {', '.join(people)}")

    if context.active_devices:
        lines.append(f"Devices/sensors currently active: {', '.join(context.active_devices)}")

    if context.anomalies:
        lines.append("Detected SAFETY issues (most severe first):")
        for a in sorted(
            context.anomalies,
            key=lambda x: {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(x.severity, 2),
        ):
            esc = (
                f" (escalated from {a.base_severity} because a vulnerable person is home)"
                if a.base_severity and a.base_severity != a.severity
                else ""
            )
            lines.append(f"  - [{a.severity}]{esc} {a.type.value} on {a.device}: {a.detail}")
    else:
        lines.append("Detected issues: none — the home is currently safe.")

    if context.relevant_patterns:
        lines.append("Relevant routines (for context):")
        for p in context.relevant_patterns[:4]:
            when = f" around {p.time}" if p.time else ""
            lines.append(f"  - {p.description}{when}")

    lines.append(
        "Remember: this is a SAFETY system. Speak only about safety/health. "
        "NEVER mention energy or cost. State the protective action you are taking; "
        "do not ask permission."
    )
    return "\n".join(lines)


async def _call_groq(system: str, user_msg: str, settings) -> dict | None:
    """Call Groq and return parsed JSON response, or None on failure."""
    if not settings.groq_api_key:
        logger.info("Groq skipped: GROQ_API_KEY not set.")
        return None

    payload = {
        "model": settings.groq_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.6,
        "max_tokens": 500,
        "response_format": {"type": "json_object"},
    }

    try:
        async with httpx.AsyncClient(timeout=settings.narrator_timeout_seconds) as client:
            resp = await client.post(
                settings.groq_chat_url,
                headers={
                    "Authorization": f"Bearer {settings.groq_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        if resp.status_code != 200:
            logger.error("Narrator Groq error %s: %s", resp.status_code, resp.text[:300])
            return None
        raw = resp.json()["choices"][0]["message"]["content"].strip()
        parsed = json.loads(raw)
        return parsed
    except json.JSONDecodeError:
        logger.warning("Groq returned non-JSON; raw=%s", raw[:200] if raw else "")
        return None
    except Exception as e:
        logger.error("Groq call failed: %s: %s", type(e).__name__, e)
        return None


async def _call_bedrock(system: str, user_msg: str, settings) -> dict | None:
    """Call AWS Bedrock Converse API and return parsed JSON response, or None."""
    import asyncio

    try:
        client = boto3.client(
            "bedrock-runtime",
            region_name=settings.aws_region,
        )

        # Bedrock Converse API — works with all Bedrock-supported models
        # including nvidia.nemotron-super-3-120b
        response = await asyncio.to_thread(
            client.converse,
            modelId=settings.bedrock_model_id,
            system=[{"text": system}],
            messages=[
                {
                    "role": "user",
                    "content": [{"text": user_msg + "\n\nRespond with a JSON object exactly like: {\"alexa_response\": \"...\", \"explanation\": \"...\"}"}],
                }
            ],
            inferenceConfig={
                "temperature": 0.6,
                "maxTokens": 500,
            },
        )

        raw = response["output"]["message"]["content"][0]["text"].strip()
        # Try to extract JSON from the response (model may wrap in markdown)
        json_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group())
            return parsed
        logger.warning("Bedrock response has no JSON; raw=%s", raw[:200])
        return None
    except Exception as e:
        logger.error("Bedrock call failed: %s: %s", type(e).__name__, e)
        return None


async def narrate(context: ContextObject) -> dict:
    """Produce an Alexa-style spoken line + a detailed 'why' explanation.

    Returns ``{"alexa_response", "explanation", "llm_powered", "reasoning"}``.
    Always succeeds — falls back to deterministic text if the LLM is
    unavailable.
    """
    settings = get_settings()
    fallback = _fallback_line(context)
    fallback_explanation = _fallback_explanation(context)

    user_msg = _build_user_message(context)
    provider = (settings.llm_provider or "groq").lower().strip()

    # Try providers in order of preference
    if provider == "bedrock":
        providers = [("bedrock", _call_bedrock), ("groq", _call_groq)]
    else:
        providers = [("groq", _call_groq), ("bedrock", _call_bedrock)]

    for name, call_fn in providers:
        logger.info("Narrator: trying %s...", name)
        parsed = await call_fn(SYSTEM_PROMPT, user_msg, settings)
        if parsed:
            line = (parsed.get("alexa_response") or "").strip()
            explanation = (parsed.get("explanation") or "").strip()
            if line:
                return {
                    "alexa_response": line,
                    "explanation": explanation or fallback_explanation,
                    "llm_powered": True,
                    "reasoning": f"Phrased by {name} LLM from the detected context.",
                }

    # Both providers failed or neither is configured
    reason_parts = []
    if not settings.groq_api_key:
        reason_parts.append("GROQ_API_KEY not set")
    if provider == "bedrock":
        reason_parts.append("Bedrock call failed (check AWS credentials/model access)")
    reason = "; ".join(reason_parts) if reason_parts else "All LLM providers failed"
    reason += " — using deterministic fallback."

    return {
        "alexa_response": fallback,
        "explanation": fallback_explanation,
        "llm_powered": False,
        "reasoning": reason,
    }


# ─── Per-anomaly narration (one focused message per issue) ───────────────────

# Order issues most-urgent-first so the spoken queue leads with what matters.
_SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}
# When one device trips several detectors, prefer the most *specific* one. The
# absolute "active too long" safety-net and a generic "missed routine" are the
# least specific, so a precise device_left_on / duration_exceeded wins.
_TYPE_SPECIFICITY = {"device_active_too_long": 2, "missed_routine": 1}
# Cap how many issues we narrate individually so a noisy what-if state can't
# fan out into dozens of concurrent LLM calls (and dozens of pop-ups).
MAX_NARRATIONS = 6


def _dedupe_by_device(anomalies: list) -> list:
    """One issue per device, most-urgent-and-specific first.

    Sorting by (severity, specificity) before de-duplicating means that when a
    device trips multiple detectors (e.g. a fan flagged both ``device_left_on``
    and ``device_active_too_long``) we keep the single most informative anomaly
    and drop the redundant one — fewer LLM calls and fewer duplicate pop-ups.
    Anomalies without a device (rare) are always kept.
    """
    ordered = sorted(
        anomalies,
        key=lambda a: (
            _SEVERITY_RANK.get(a.severity, 1),
            _TYPE_SPECIFICITY.get(a.type.value, 0),
        ),
    )
    seen: set[str] = set()
    out: list = []
    for a in ordered:
        if a.device is not None:
            if a.device in seen:
                continue
            seen.add(a.device)
        out.append(a)
    return out



def _single_anomaly_context(context: ContextObject, anomaly) -> ContextObject:
    """Build a context narrowed to ONE anomaly so the LLM can speak about it in
    full detail instead of cramming every issue into a single short paragraph.

    The sub-context keeps the shared facts (time, who's home, active devices)
    but exposes only the one anomaly and the learned pattern(s) it relates to,
    and re-derives its own ``context_type`` so the narration tone matches.
    """
    from safety.context_builder.builder import _classify

    related = [
        p
        for p in (context.relevant_patterns or [])
        if anomaly.related_pattern_id and p.pattern_id == anomaly.related_pattern_id
    ]
    if not related:
        # No direct id link — keep patterns that mention this device by name.
        related = [
            p
            for p in (context.relevant_patterns or [])
            if anomaly.device and anomaly.device in (p.description or "")
        ]

    return ContextObject(
        context_type=_classify([anomaly]),
        household_id=context.household_id,
        current_time=context.current_time,
        people_home=context.people_home,
        active_devices=context.active_devices,
        relevant_patterns=related,
        anomalies=[anomaly],
        recent_events=context.recent_events,
    )


async def narrate_each(context: ContextObject) -> list[dict]:
    """Narrate EACH detected issue as its own focused Alexa line.

    Instead of one prompt describing every anomaly at once (which forces the LLM
    to compress and drop specifics), this splits the context into one sub-context
    per anomaly, narrates them concurrently, and returns an ordered list — most
    severe first — so the frontend can show/speak them one-by-one as a sequence
    of floating notifications.

    Each returned item has the same shape as :func:`narrate` plus ``device``,
    ``anomaly_type`` and ``severity`` so the UI can label and order them. When
    there are no anomalies a single "all clear" item is returned.
    """
    anomalies = list(context.anomalies or [])
    if not anomalies:
        one = await narrate(context)
        one.update({"device": None, "anomaly_type": None, "severity": "low"})
        return [one]

    ordered = _dedupe_by_device(anomalies)[:MAX_NARRATIONS]
    sub_contexts = [_single_anomaly_context(context, a) for a in ordered]
    results = await asyncio.gather(*(narrate(c) for c in sub_contexts))

    out: list[dict] = []
    for anomaly, result in zip(ordered, results):
        item = dict(result)
        item["device"] = anomaly.device
        item["anomaly_type"] = anomaly.type.value
        item["severity"] = anomaly.severity
        out.append(item)
    return out
