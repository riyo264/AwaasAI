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

import boto3
import httpx
import functools
from patterns.app.config import get_settings
from patterns.models.context import ContextObject, ContextType

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

SYSTEM_PROMPT = """You are Alexa, the voice and reasoning engine of a calm, helpful smart-home assistant.

You are given a STRUCTURED CONTEXT describing the current state of a household:
the time, who is home, which devices are on, any issues a deterministic engine
detected, the learned routines those issues relate to, and an "Energy & timing
facts" section with concrete numbers (how long a device has been on, how far past
its usual time it is, and the estimated energy wasted so far).

Produce TWO things, returned as a JSON object:

1. "alexa_response": ONE or TWO short, natural, friendly sentences a smart speaker
   would say out loud RIGHT NOW. Crucially, weave in ONE or TWO of the CONCRETE
   SPECIFICS from the facts — for example: the time the device was switched on,
   how many hours it has been running, how far past its usual off-time it is, or
   roughly how much energy could be saved by turning it off. Make it sound
   natural, not like a data dump.
   Good examples:
     - "The fan in the son's room has been on since 7:30 AM — that's over 3 hours
        past when it's usually switched off, and turning it off now would save
        about 0.2 kilowatt-hours. Want me to do that?"
     - "Your water motor has been running for about 45 minutes, three times longer
        than its usual 15-minute cycle — shall I switch it off?"
   If everything is normal, give a brief, warm all-clear (no numbers needed).

2. "explanation": a longer, friendly paragraph (3-5 sentences) that explains the
   REASONING — WHY the system flagged this. Connect the current state to the
   learned routines and include the supporting numbers (usual time, hours
   elapsed, energy estimate). Shown when the user taps "See more", so it can be
   more detailed, but stay plain and friendly.

Rules for BOTH fields:
- Use ONLY the numbers provided in the facts. NEVER invent figures. If a fact is
  not given, don't state it.
- Sound human and warm. NEVER mention JSON, the words "anomaly", "pattern",
  "confidence", or any internal field names.
- Refer to devices and rooms in plain words (son_room_fan -> "the fan in the
  son's room", water_motor -> "the water motor"). Say energy as "kilowatt-hours"
  (or "watt-hours" for small amounts), and times naturally ("7:30 AM", "3 hours").
- People-/care-/security sensors are NOT appliances — speak about the PERSON:
  grandpa_activity -> "Grandpa", ananya_presence -> "Ananya",
  maid_presence -> "the house helper", grandma_medicine -> "Grandma's medicine".
  For a water motor running long, you may gently note the overhead tank may
  already be full.

Tone for the people-centric situations (be caring, never alarmist):
- Elderly inactivity / a child who hasn't returned / a missed medicine: warm,
  concerned, and suggest a gentle check-in or reminder — e.g. "I haven't noticed
  Grandpa's usual morning activity yet today. Would you like me to check in on
  him?" or "Ananya usually returns from tuition by now. Want me to check in?"
- Activity at an unusual hour (a helper entering off-schedule): calm but alert,
  and offer to check the cameras — e.g. "Someone entered the house outside the
  usual schedule. Would you like me to check the security cameras?"

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
            leads.append(f"the {dev} is still on")
        elif a.type.value == "duration_exceeded":
            leads.append(f"the {dev} has been running much longer than usual")
        elif a.type.value == "device_active_too_long":
            leads.append(f"the {dev} has been on for a very long time")
        elif a.type.value == "missed_routine":
            leads.append(f"the {dev} didn't run at its usual time")
        elif a.type.value == "inactivity":
            leads.append(f"there's been no sign of {subj}'s usual activity")
        elif a.type.value == "missed_arrival":
            leads.append(f"{subj} hasn't returned home at the usual time")
        elif a.type.value == "missed_medicine":
            leads.append(f"{subj} seems to have been missed")
        elif a.type.value == "unexpected_activity":
            leads.append(f"{subj} was active outside the usual schedule")
        else:
            leads.append(f"something seems off with the {dev}")

    joined = " and ".join(leads)
    # Care/security situations warrant a check-in tone rather than "take care of it".
    types = {a.type.value for a in anomalies}
    if "unexpected_activity" in types:
        return f"Heads up — {joined}. Would you like me to check the cameras?"
    if types & {"inactivity", "missed_arrival", "missed_medicine"}:
        return f"Just checking in — {joined}. Would you like me to send a reminder or check in?"
    extra = ""
    if len(anomalies) > 2:
        more = len(anomalies) - 2
        noun = "thing" if more == 1 else "things"
        extra = f" There{' is' if more == 1 else ' are'} {more} more {noun} I noticed too."
    return f"Heads up — {joined}. Would you like me to take care of it?{extra}"


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
        else:
            sentences.append(f"Something looks off with the {dev}.")

    intro = (
        "Here's why I flagged this: I compare what's happening right now against "
        "the routines this home has followed over the past weeks. "
    )
    outro = " You can ask me to turn things off or just dismiss this if it's intentional."
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
    """Compact, readable summary of the context for the LLM."""
    lines = [
        f"Time: {context.current_time}",
        f"Context type: {context.context_type.value}",
    ]
    people = [p for p, home in (context.people_home or {}).items() if home]
    if people:
        lines.append(f"People home: {', '.join(people)}")
    if context.active_devices:
        lines.append(f"Devices currently on: {', '.join(context.active_devices)}")

    if context.anomalies:
        lines.append("Detected issues:")
        for a in context.anomalies:
            lines.append(f"  - [{a.severity}] {a.type.value} on {a.device}: {a.detail}")
    else:
        lines.append("Detected issues: none — everything is normal.")

    if context.relevant_patterns:
        lines.append("Relevant routines:")
        for p in context.relevant_patterns[:5]:
            when = f" around {p.time}" if p.time else ""
            lines.append(f"  - {p.description}{when}")

    facts = _energy_facts(context)
    if facts:
        lines.append("Energy & timing facts (use these exact numbers):")
        lines.extend(f"  - {f}" for f in facts)

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
        async with httpx.AsyncClient(timeout=settings.narrator_timeout_seconds, verify = _verify_ctx()) as client:
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


async def narrate(context: ContextObject, language: str = "en") -> dict:
    """Produce an Alexa-style spoken line + a detailed 'why' explanation.

    Returns ``{"alexa_response", "explanation", "llm_powered", "reasoning"}``.
    Always succeeds — falls back to deterministic text if the LLM is
    unavailable.
    """
    from patterns.logic import lang
    settings = get_settings()
    fallback = _fallback_line(context)
    fallback_explanation = _fallback_explanation(context)

    system = SYSTEM_PROMPT + lang.directive(language)
    user_msg = _build_user_message(context)
    provider = (settings.llm_provider or "groq").lower().strip()

    # Try providers in order of preference
    if provider == "bedrock":
        providers = [("bedrock", _call_bedrock), ("groq", _call_groq)]
    else:
        providers = [("groq", _call_groq), ("bedrock", _call_bedrock)]

    for name, call_fn in providers:
        logger.info("Narrator: trying %s...", name)
        parsed = await call_fn(system, user_msg, settings)
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
    from patterns.context_builder.builder import _classify

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


async def narrate_each(context: ContextObject, language: str = "en") -> list[dict]:
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
        one = await narrate(context, language)
        one.update({"device": None, "anomaly_type": None, "severity": "low"})
        return [one]

    ordered = _dedupe_by_device(anomalies)[:MAX_NARRATIONS]
    sub_contexts = [_single_anomaly_context(context, a) for a in ordered]
    results = await asyncio.gather(*(narrate(c, language) for c in sub_contexts))

    out: list[dict] = []
    for anomaly, result in zip(ordered, results):
        item = dict(result)
        item["device"] = anomaly.device
        item["anomaly_type"] = anomaly.type.value
        item["severity"] = anomaly.severity
        out.append(item)
    return out
