"""Ambient sound API — the household "ear".

The browser classifies mic audio locally (MediaPipe YAMNet) and posts the
detected sound here. We interpret it against the live house context + any learned
sound-routine, optionally log it as an event (so routines keep learning), and
return a prompt/action for the UI. Detection is free & on-device; interpretation
is deterministic — no paid or rate-limited model is required.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

import re

from patterns.app.config import get_settings
from patterns.logic import (
    ambient_llm,
    ambient_sense,
    ambient_sounds,
    event_service,
    pattern_service,
)
from patterns.logic.ambient_sounds import ambient_device_id
from patterns.models.ambient import (
    AmbientInterpretation,
    AmbientListenRequest,
    AmbientObserveRequest,
    AmbientRoutine,
)
from patterns.models.events import DeviceAction, DeviceType, EventCreate
from patterns.models.patterns import TimePattern

router = APIRouter(prefix="/ambient", tags=["ambient"])


def _resolve_clock(current_time: str | None) -> datetime:
    now = datetime.now(timezone.utc)
    if not current_time:
        return now
    try:
        h, m = current_time.split(":")
        return now.replace(hour=int(h), minute=int(m), second=0, microsecond=0)
    except (ValueError, AttributeError):
        return now


def _learned_routine(household_id: str, sound_key: str) -> dict | None:
    """The learned TimePattern (if any) for this ambient sound."""
    dev = ambient_device_id(sound_key)
    for p in pattern_service.get_patterns(household_id):
        if isinstance(p, TimePattern) and p.device == dev and p.action == "ACTIVE":
            return {
                "usual_time": p.usual_time,
                "window_minutes": p.window_minutes,
                "confidence": p.confidence,
            }
    return None


_SEV_RANK = {"info": 0, "suggest": 1, "warn": 2, "alert": 3}


async def _apply_sense(household_id: str, interp: dict, clock, people: list, active: list,
                       language: str = "en") -> dict:
    """Run the sense-making strategy (deterministic) and, when it flags the sound,
    generate a caring narration (LLM). Call AFTER the event is logged so counts
    include the current occurrence."""
    key = interp.get("sound")
    sense = ambient_sense.evaluate(household_id, key, clock)
    interp["sense_strategy"] = sense["strategy"]

    # When a sound has a sense strategy, its verdict is authoritative on severity
    # (it knows the sound's own baseline); leave severity as-is otherwise.
    sv = sense.get("severity")
    if sv:
        interp["severity"] = sv
    if sense["flagged"]:
        interp["flagged"] = True
        interp["sense_reason"] = sense["reason"]
        interp["evidence"] = sense["evidence"]

    # Narrate EVERY recognised household sound through the narrator LLM — the
    # flagged concerns AND the ordinary informational ones ("the chai's boiling",
    # "someone's at the door") — so the home always speaks up with context.
    # (Open-vocabulary Gemini sounds already carry their own spoken line.)
    recognised = interp.get("recognised", True)
    known = ambient_sounds.get_sound(interp.get("sound")) is not None
    if recognised and (known or sense["flagged"] or sense["always_narrate"]):
        narr = await ambient_llm.narrate({
            "sound": interp.get("label"),
            "meaning": interp.get("meaning"),
            "prompt": interp.get("prompt"),
            "severity": interp.get("severity"),
            "reason": sense.get("reason"),
            "evidence": sense.get("evidence"),
            "timing": interp.get("timing"),
            "time": clock.strftime("%H:%M"),
            "people_home": people,
            "active_devices": active,
        }, language)
        interp["narration"] = narr.get("narration", "")
        interp["narration_llm"] = narr.get("narration_llm", False)
        interp["explanation"] = narr.get("explanation", "")
    return interp


@router.get("/sounds")
def list_sounds() -> dict:
    """The sound taxonomy — used by the browser to map YAMNet labels to household
    sounds and to render the (fallback) simulate buttons."""
    return {"sounds": ambient_sounds.taxonomy()}


@router.post("/{household_id}/observe", response_model=AmbientInterpretation)
async def observe(household_id: str, body: AmbientObserveRequest) -> AmbientInterpretation:
    """Interpret a detected household sound against context + learned routines,
    then run sense-making (rate/burst/surface/instant) and narrate any flag."""
    # Resolve the canonical sound (explicit key wins, else map the raw label).
    key = body.sound or ambient_sounds.map_yamnet_label(body.yamnet_label or "")
    if not key:
        return AmbientInterpretation(
            sound=body.yamnet_label or "unknown", label=body.yamnet_label or "Unknown sound",
            recognised=False, meaning="Not a household sound we act on.",
            prompt="", confidence=body.confidence,
        )

    clock = _resolve_clock(body.current_time)
    learned = _learned_routine(household_id, key)
    result = ambient_sounds.interpret(
        key,
        hour=clock.hour,
        now_min=clock.hour * 60 + clock.minute,
        people_home=body.people_home,
        active_devices=body.active_devices,
        learned=learned,
    )

    result["confidence"] = body.confidence
    result["logged"] = False
    if body.ingest and result.get("recognised"):
        # Log FIRST so the sense-making counts include this occurrence.
        result["logged"] = _log_ambient(household_id, key, clock, body.confidence, "ambient_live")

    await _apply_sense(household_id, result, clock, body.people_home, body.active_devices, body.language)
    return AmbientInterpretation(**result)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (text or "sound").lower()).strip("_") or "sound"


def _log_ambient(household_id: str, key: str, clock, confidence: float, source: str) -> bool:
    event_service.store_event(EventCreate(
        household_id=household_id,
        device_id=ambient_device_id(key),
        device_type=DeviceType.OTHER,
        room="home",
        action=DeviceAction.ACTIVE,
        triggered_by="ambient",
        timestamp=clock,
        metadata={"sound": key, "source": source,
                  "confidence_pct": int(round(confidence * 100))},
    ))
    return True


@router.post("/{household_id}/listen", response_model=AmbientInterpretation)
async def listen(household_id: str, body: AmbientListenRequest) -> AmbientInterpretation:
    """Identify a recorded mic clip with the audio LLM (Gemini) and interpret it.

    Gemini is the *ear* — it recognises ANY household sound in open vocabulary.
    When the sound matches a known taxonomy key, we overlay the DETERMINISTIC
    interpreter's verified action + expected/unusual timing; otherwise we use
    Gemini's open-vocabulary reasoning directly. Falls back gracefully if the key
    is missing or the call fails, so the simulate path always works.
    """
    settings = get_settings()
    clock = _resolve_clock(body.current_time)
    ctx = {
        "current_time": body.current_time,
        "people_home": body.people_home,
        "active_devices": body.active_devices,
    }
    gem = await ambient_llm.listen(body.audio_base64, body.mime_type or "audio/wav", ctx)

    if gem is None:
        msg = (
            "The audio ear needs a free GEMINI_API_KEY in backend/.env."
            if not settings.gemini_api_key
            else "Couldn't make out the sound — try again, or tap a sound to simulate."
        )
        return AmbientInterpretation(
            sound="unknown", label="Didn't catch that", recognised=False,
            meaning=msg, prompt=msg, source="gemini", llm_powered=bool(settings.gemini_api_key),
        )

    key = gem.get("sound_key")
    known = ambient_sounds.get_sound(key) if key else None
    confidence = float(gem.get("confidence") or 0.9)

    if known:
        # Overlay Gemini's richer language on the deterministic (verified) result.
        learned = _learned_routine(household_id, key)
        interp = ambient_sounds.interpret(
            key, hour=clock.hour, now_min=clock.hour * 60 + clock.minute,
            people_home=body.people_home, active_devices=body.active_devices, learned=learned,
        )
        interp["prompt"] = gem.get("prompt") or interp["prompt"]
        interp["meaning"] = gem.get("description") or interp["meaning"]
        log_key = key
    else:
        # Open-vocabulary: trust Gemini's reasoning (advisory action).
        urgency = gem.get("urgency", "info")
        act = gem.get("suggested_action") or {}
        action = None
        if act.get("device") and act.get("action"):
            action = {"device": act["device"], "action": act["action"],
                      "requires_confirmation": urgency in ("suggest", "warn")}
        interp = {
            "sound": key or "other",
            "label": gem.get("primary_sound") or "Household sound",
            "emoji": "🔊",
            "recognised": True,
            "category": gem.get("category", "activity"),
            "severity": urgency if urgency in ambient_sounds.SEVERITIES else "info",
            "meaning": gem.get("description", ""),
            "prompt": gem.get("prompt", ""),
            "suggested_action": action,
            "requires_confirmation": bool(action and action.get("requires_confirmation")),
            "timing": "new",
            "routine_note": "",
        }
        log_key = _slug(gem.get("primary_sound"))

    interp.update({
        "confidence": confidence,
        "description": gem.get("description", ""),
        "likely_activity": gem.get("likely_activity", ""),
        "detected_raw": gem.get("primary_sound", ""),
        "llm_powered": True,
        "source": "gemini",
        "logged": False,
    })
    if body.ingest:
        interp["logged"] = _log_ambient(household_id, log_key, clock, confidence, "ambient_llm")

    # Sense-making runs on the reconciled canonical key (open-vocab has no profile).
    interp["sound"] = key if known else (key or "other")
    await _apply_sense(household_id, interp, clock, body.people_home, body.active_devices, body.language)
    return AmbientInterpretation(**interp)


@router.get("/{household_id}/routines", response_model=list[AmbientRoutine])
def learned_routines(household_id: str) -> list[AmbientRoutine]:
    """The sound routines the engine has learned for this home (ambient_* patterns)."""
    out: list[AmbientRoutine] = []
    for p in pattern_service.get_patterns(household_id):
        if not (isinstance(p, TimePattern) and p.device.startswith("ambient_")):
            continue
        key = p.device[len("ambient_"):]
        meta = ambient_sounds.get_sound(key)
        out.append(AmbientRoutine(
            sound=key,
            label=meta.label if meta else key,
            emoji=meta.emoji if meta else "🔊",
            usual_time=p.usual_time,
            window_minutes=p.window_minutes,
            confidence=p.confidence,
            occurrences=p.occurrences,
        ))
    out.sort(key=lambda r: r.usual_time)
    return out


@router.post("/{household_id}/seed")
def seed(household_id: str) -> dict:
    """Seed 30 days of ambient-sound history + extract sound routines (demo)."""
    from patterns.tests.sample_data_ambient import generate

    removed = event_service.delete_household_events(household_id)
    stored = event_service.store_events(generate(days=30))
    patterns = pattern_service.extract_and_store(household_id)
    ambient_patterns = [p for p in patterns if getattr(p, "device", "").startswith("ambient_")]
    return {
        "household_id": household_id,
        "events_cleared": removed,
        "events_stored": len(stored),
        "sound_routines_learned": len(ambient_patterns),
    }
