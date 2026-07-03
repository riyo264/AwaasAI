"""Guardian API — elderly-alone protective flow.

    board state → assess → triage (flag the worst concern)
        → auto_alarm (extreme)  OR  check_in (less serious) → respond → verdict

Reuses the evaluate request shape from the context route so the dashboard can
send the exact same "dollhouse" state it already builds.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter
from pydantic import BaseModel, Field

from safety.logic import guardian
from safety.models.events import Event
from safety.models.guardian import CheckinVerdict, GuardianDecision
from safety.routes.context import EvaluateStateRequest, _resolve_now

router = APIRouter(prefix="/guardian", tags=["guardian"])


@router.post("/{household_id}/assess", response_model=GuardianDecision)
async def assess(household_id: str, body: EvaluateStateRequest) -> GuardianDecision:
    """Run the deterministic safety evaluation, then the Guardian triage."""
    now = _resolve_now(body.current_time)
    eff_now = now or datetime.now(timezone.utc)
    extra_recent = [
        Event(
            household_id=household_id,
            device_id=s.device_id,
            device_type=s.device_type,
            room=s.room,
            action=s.action,
            triggered_by=s.triggered_by,
            timestamp=eff_now - timedelta(minutes=s.minutes_ago),
            metadata=s.metadata,
        )
        for s in body.signals
    ]
    return await guardian.assess(
        household_id,
        active_devices=body.active_devices,
        people_home=body.people_home,
        device_on_since=body.device_on_since,
        now=now,
        profiles=body.profiles,
        extra_recent=extra_recent,
        ignore_stored_events=body.ignore_stored_events,
        healthy_baseline=body.healthy_baseline,
        skip_completions=body.skip_completions,
        language=body.language,
    )


class CheckinRespondRequest(BaseModel):
    text: str | None = Field(None, description="Typed reply (or send audio).")
    audio_base64: str | None = Field(None, description="Spoken reply (Groq Whisper, webm ok).")
    audio_format: str = "webm"
    person: str = "your family member"
    concern_detail: str = Field("", description="What the check-in was about.")
    language: str = Field("en", description="Reply language: en|hi|hinglish|ta|te|bn|mr.")


@router.post("/{household_id}/checkin/respond", response_model=CheckinVerdict)
async def checkin_respond(household_id: str, body: CheckinRespondRequest) -> CheckinVerdict:
    """Interpret the person's reply to a check-in → stand down or escalate."""
    reply = (body.text or "").strip()
    if not reply and body.audio_base64:
        reply = await guardian.transcribe(body.audio_base64, body.audio_format or "webm")
    return await guardian.checkin_respond(body.person, body.concern_detail, reply, body.language)
