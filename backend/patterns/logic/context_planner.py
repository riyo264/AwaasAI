"""Turn a spoken/typed occasion note into temporary pattern adjustments.

Flow:  audio → (Groq Whisper) transcript → (Groq LLM) plan → validate → preview.

The LLM knows the Indian festival calendar and the home's learned patterns, and
proposes a small set of TEMPORARY, dated adjustments (add/shift/suppress/adjust)
that overlay the routines for the occasion. Every shift/suppress/adjust must
reference a REAL learned pattern (resolve-or-drop) so nothing is hallucinated.
The base patterns are never modified; the user confirms before anything applies.
"""
from __future__ import annotations

import base64
import json
import logging
from datetime import datetime, timedelta, timezone

import httpx

from patterns.app.config import get_settings
from patterns.logic import pattern_service
from patterns.logic.narrator import _verify_ctx

logger = logging.getLogger(__name__)

GROQ_WHISPER_URL = "https://api.groq.com/openai/v1/audio/transcriptions"

_VALID_TYPES = {"add", "shift", "suppress", "adjust"}

SYSTEM_PROMPT = """You adapt a home's LEARNED daily routines to a one-off occasion the user mentions
— a festival, guests, a party, travel, or someone unwell. You know the Indian
festival calendar (Diwali, Navratri, Holi, Raksha Bandhan, Pongal, Onam, Eid,
Christmas, etc.) and typical Indian-household customs, and you plan like a
thoughtful house manager.

You are given: the user's note, TODAY's date, the home's learned patterns (JSON,
each with a pattern_id, device, action and usual time), and the known devices.

Produce 4–8 TEMPORARY adjustments for the relevant day — never permanent.
Adjustment types:
  - "add"      : a new temporary action — device + action + new_time REQUIRED.
  - "shift"    : move an existing pattern — target_pattern_id + new_time REQUIRED.
  - "suppress" : skip an existing pattern that day — target_pattern_id.
  - "adjust"   : a qualitative tweak to an existing pattern — target_pattern_id +
                 description (e.g. play festival bhajans instead of the usual).

Craft the plan like a good day-plan, not a random list:
- Cover the WHOLE day when the occasion deserves it (morning prep → evening peak).
- Mix the types: include at least one "shift" and one "add" when they make sense.
- Anchor every shift to the pattern's learned time and state the change in the
  description (e.g. "Pooja lamp an hour earlier — 06:00 instead of 07:01").
- description: short (≤ 12 words), starts with the routine, states the change.
- reason: ONE warm sentence tying the change to the occasion's custom
  (e.g. "Diwali pooja is performed at dawn, before the diyas are lit").

Occasion playbooks (use judgement, adapt to the actual devices):
- Festival: pooja earlier & longer; diya/decoration lights ON at dusk; festival
  bhajans instead of the usual; a longer evening cooking window on the stove;
  skip noisy chores (water motor / vacuum) during celebrations.
- Guests / party: hall & dining lit and cooled BEFORE arrival; dinner shifted
  later; porch light earlier for arrivals; skip the usual early switch-offs
  (TV / dining light) so the evening can run long.
- Travel / away: suppress comfort routines (TV, geyser, chai, bhajans); KEEP
  security (porch light ON at dusk); shift the water motor to just before return.
- Unwell at home: a quieter home — suppress the loud bell/speaker; geyser ON
  again mid-day for warm water; medicine reminder earlier; evening lights dim
  and TV off early.

Hard rules:
- shift / suppress / adjust MUST reference a real pattern_id from the list.
- Prefer the home's actual devices; "add" may introduce ONE sensible new device
  (e.g. decoration_lights) when the occasion clearly calls for it.
- Resolve the occasion's DATE from the note relative to today (ISO YYYY-MM-DD).
- summary: one friendly line a smart-home app would show, mentioning the
  occasion and the shape of the day (e.g. "Diwali day: dawn pooja, diyas at
  dusk and a longer dinner window.").

Return STRICT JSON:
{"occasion":"<short>","occasion_date":"YYYY-MM-DD","summary":"<one line>",
"adjustments":[{"type":"add|shift|suppress|adjust","target_pattern_id":"<id|null>",
"device":"<id|null>","action":"ON|OFF|null","new_time":"HH:MM|null",
"description":"<what changes>","reason":"<why, tied to the occasion>"}]}"""


async def _call_groq_plan(system: str, user_msg: str, settings) -> dict | None:
    """Groq JSON call for the planner — needs a larger budget than the narrator
    (a full-day plan with 4–8 reasoned adjustments doesn't fit in 500 tokens)."""
    if not settings.groq_api_key:
        logger.info("Planner skipped: GROQ_API_KEY not set.")
        return None
    payload = {
        "model": settings.groq_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.5,
        "max_tokens": 1400,
        "response_format": {"type": "json_object"},
    }
    try:
        async with httpx.AsyncClient(
            timeout=settings.narrator_timeout_seconds, verify=_verify_ctx()
        ) as client:
            resp = await client.post(
                settings.groq_chat_url,
                headers={
                    "Authorization": f"Bearer {settings.groq_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        if resp.status_code != 200:
            logger.error("Planner Groq error %s: %s", resp.status_code, resp.text[:300])
            return None
        raw = resp.json()["choices"][0]["message"]["content"].strip()
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Planner Groq returned non-JSON.")
        return None
    except Exception as e:  # pragma: no cover - network
        logger.error("Planner Groq call failed: %s: %s", type(e).__name__, e)
        return None


async def transcribe(audio_base64: str, fmt: str = "webm") -> str:
    """Groq Whisper STT. Accepts webm/wav/mp3 directly. Returns '' on failure."""
    s = get_settings()
    if not s.groq_api_key:
        return ""
    try:
        audio = base64.b64decode(audio_base64)
        async with httpx.AsyncClient(timeout=30.0, verify=_verify_ctx()) as client:
            resp = await client.post(
                GROQ_WHISPER_URL,
                headers={"Authorization": f"Bearer {s.groq_api_key}"},
                files={"file": (f"note.{fmt}", audio, f"audio/{fmt}")},
                data={"model": "whisper-large-v3-turbo", "response_format": "json"},
            )
        if resp.status_code != 200:
            logger.error("Whisper error %s: %s", resp.status_code, resp.text[:200])
            return ""
        return resp.json().get("text", "").strip()
    except Exception as e:  # pragma: no cover - network
        logger.error("Whisper call failed: %s: %s", type(e).__name__, e)
        return ""


def _pattern_brief(patterns) -> tuple[list[dict], set[str], set[str]]:
    """Compact patterns for the LLM + the sets of valid ids/devices."""
    brief, ids, devices = [], set(), set()
    for p in patterns:
        t = getattr(p, "usual_time", None) or getattr(p, "usual_start_time", None)
        dev = getattr(p, "device", None)
        row = {
            "pattern_id": p.pattern_id,
            "device": dev,
            "action": getattr(p, "action", None),
            "time": t,
            "type": p.pattern_type.value,
        }
        if isinstance(getattr(p, "description", None), str):
            row["description"] = p.description
        brief.append(row)
        ids.add(p.pattern_id)
        if dev:
            devices.add(dev)
    return brief, ids, devices


def _validate(adjustments: list, valid_ids: set[str]) -> list[dict]:
    """Keep only well-formed adjustments; drop hallucinated pattern references."""
    out = []
    for a in adjustments or []:
        if not isinstance(a, dict):
            continue
        atype = (a.get("type") or "").lower()
        if atype not in _VALID_TYPES:
            continue
        if atype in {"shift", "suppress", "adjust"}:
            if a.get("target_pattern_id") not in valid_ids:
                continue  # resolve-or-drop — no hallucinated targets
        if atype == "shift" and not a.get("new_time"):
            continue  # a shift without a time is a no-op
        if atype == "add" and not a.get("device"):
            continue
        if not a.get("description"):
            continue
        out.append({
            "type": atype,
            "target_pattern_id": a.get("target_pattern_id"),
            "device": a.get("device"),
            "action": a.get("action"),
            "new_time": a.get("new_time"),
            "description": a.get("description"),
            "reason": a.get("reason", ""),
        })
    return out[:8]


async def plan(household_id: str, text: str, *, now: datetime | None = None) -> dict:
    """Produce a previewable ContextPlan dict from the user's note."""
    now = now or datetime.now(timezone.utc)
    patterns = pattern_service.get_patterns(household_id)
    brief, valid_ids, devices = _pattern_brief(patterns)

    settings = get_settings()
    user_payload = {
        "note": text,
        "today": now.date().isoformat(),
        "tomorrow": (now + timedelta(days=1)).date().isoformat(),
        "known_devices": sorted(devices),
        "learned_patterns": brief,
    }
    llm = await _call_groq_plan(SYSTEM_PROMPT, json.dumps(user_payload), settings)

    if not isinstance(llm, dict):
        return {
            "household_id": household_id, "transcript": text, "occasion": "",
            "occasion_date": (now + timedelta(days=1)).date().isoformat(),
            "summary": "Couldn't reach the planner — please try again.",
            "adjustments": [], "llm_powered": False,
        }

    adjustments = _validate(llm.get("adjustments"), valid_ids)
    return {
        "household_id": household_id,
        "transcript": text,
        "occasion": llm.get("occasion", ""),
        "occasion_date": llm.get("occasion_date")
        or (now + timedelta(days=1)).date().isoformat(),
        "summary": llm.get("summary", ""),
        "adjustments": adjustments,
        "llm_powered": True,
    }
