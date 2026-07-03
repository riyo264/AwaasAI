"""Context API: produce the AI-ready context object (Bedrock hand-off).

This endpoint is the MVP's final deliverable. It returns the structured
:class:`ContextObject`. In a future phase this payload is forwarded to Amazon
Bedrock for reasoning — that step is intentionally NOT implemented here.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from safety.models.context import ContextObject
from safety.models.events import DeviceAction, DeviceType, Event
from safety.models.safety import PersonProfile
from safety.logic import context_service, narrator

router = APIRouter(prefix="/context", tags=["context"])


class NarrationResponse(BaseModel):
    """The spoken-style Alexa line produced from a context object."""

    alexa_response: str = Field(..., description="Natural-language line to speak/show.")
    explanation: str = Field(
        "",
        description="Longer 'why' paragraph shown when the user taps 'See more'.",
    )
    llm_powered: bool = Field(..., description="True if phrased by the LLM, False if fallback.")
    reasoning: str = Field("", description="Why this phrasing / which path was used.")


class NarrationItem(NarrationResponse):
    """One per-anomaly narration, with the issue it describes."""

    device: str | None = Field(None, description="Device/person the issue is about.")
    anomaly_type: str | None = Field(None, description="The anomaly type narrated.")
    severity: str = Field("low", description="Issue severity: high / medium / low.")


class NarrationListResponse(BaseModel):
    """An ordered list of per-anomaly narrations (most severe first)."""

    narrations: list[NarrationItem] = Field(default_factory=list)



class EvaluateSignal(BaseModel):
    """A synthetic momentary signal injected into the what-if evaluation.

    Powers the live dashboard's panic buttons and "quiet house" demo: an SOS
    press, a wearable health ALERT, or a "last seen" activity ping. It is turned
    into an ephemeral recent event (timestamped ``minutes_ago`` before the demo
    clock) so the event-reading detectors fire — without persisting anything.
    """

    device_id: str = Field(..., examples=["grandpa_wearable"])
    device_type: DeviceType = DeviceType.OTHER
    room: str = "home"
    action: DeviceAction
    triggered_by: str = "system"
    minutes_ago: float = Field(
        0.0, ge=0.0, description="How long before the demo clock this signal fired."
    )
    metadata: dict | None = None


class EvaluateStateRequest(BaseModel):
    """A user-supplied what-if snapshot to compare against learned patterns."""

    current_time: str | None = Field(
        None,
        description="Simulated current time as HH:MM (or full ISO). None = real now.",
        examples=["10:00"],
    )
    active_devices: list[str] = Field(
        default_factory=list,
        description="Device IDs the user marks as currently ON / OPEN.",
        examples=[["son_room_fan", "son_room_light"]],
    )
    people_home: dict[str, bool] = Field(
        default_factory=dict,
        description="Optional map of person -> presence flag.",
    )
    device_on_since: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Optional map of device_id -> ISO time it turned on. Enables "
            "duration-based anomalies; omit for a pure ON/OFF check."
        ),
    )
    profiles: list[PersonProfile] | None = Field(
        None,
        description=(
            "Ephemeral cast: who is home right now and how vulnerable. When set, "
            "the vulnerability lens is driven entirely by this list instead of "
            "the persisted profile table — nothing is written to the database, so "
            "the UI can add/remove people live and watch concerns re-escalate."
        ),
    )
    signals: list[EvaluateSignal] = Field(
        default_factory=list,
        description="Synthetic momentary signals (SOS / health ALERT / last-seen ping).",
    )
    ignore_stored_events: bool = Field(
        False,
        description=(
            "Drop the stored event tail and judge only against `signals`. Used "
            "for a clean inactivity demo where seeded events would count as "
            "signs of life."
        ),
    )
    healthy_baseline: bool = Field(
        False,
        description=(
            "Treat today's routines-so-far as done → the home stays CALM unless "
            "the user deliberately creates a situation. Prevents phantom "
            "'missed routine' flags from the passing demo clock."
        ),
    )
    skip_completions: list[str] = Field(
        default_factory=list,
        description="Device ids whose routine is deliberately MISSED (e.g. ['grandma_medicine']).",
    )
    language: str = Field("en", description="Narration language: en|hi|hinglish|ta|te|bn|mr.")


def _resolve_now(at: str | None) -> datetime | None:
    """Turn an optional ``HH:MM`` (or full ISO) string into a UTC datetime.

    Powers the frontend's "simulated clock": the demo can ask "what does the
    context look like at 11:00?" without waiting for the real wall clock.
    """
    if not at:
        return None
    try:
        if "T" in at:  # full ISO timestamp
            dt = datetime.fromisoformat(at)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        hour, minute = at.split(":")
        return datetime.now(timezone.utc).replace(
            hour=int(hour), minute=int(minute), second=0, microsecond=0
        )
    except (ValueError, TypeError):
        return None


@router.get("/{household_id}", response_model=ContextObject)
def get_context(
    household_id: str,
    at: str | None = Query(
        None,
        description="Simulated current time as HH:MM (or full ISO). Demo clock.",
        examples=["11:00"],
    ),
) -> ContextObject:
    return context_service.generate_context(household_id, now=_resolve_now(at))


@router.post("/{household_id}/evaluate", response_model=ContextObject)
def evaluate_context(
    household_id: str,
    body: EvaluateStateRequest,
) -> ContextObject:
    """Compare a user-supplied current state + clock against the learned
    patterns and return the resulting anomalies.

    This powers the frontend's "set the state, set the clock, hit Go" flow.
    The supplied state is evaluated in-memory only — nothing is persisted, so
    the demo data is never mutated.
    """
    now = _resolve_now(body.current_time)
    eff_now = now or datetime.now(timezone.utc)

    # Turn synthetic signals into ephemeral recent events, timestamped relative
    # to the demo clock. These never touch the events table.
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

    return context_service.evaluate_context(
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
    )


@router.post("/narrate", response_model=NarrationResponse)
async def narrate_context(context: ContextObject) -> NarrationResponse:
    """Turn a detected context object into a natural, spoken-style Alexa line.

    The frontend calls this right after evaluating a scenario: it passes the
    ContextObject it just received and shows the returned sentence as an
    Alexa-style notification. Uses the configured LLM_PROVIDER (bedrock or groq),
    otherwise a deterministic fallback sentence (so the notification always appears).
    """
    result = await narrator.narrate(context)
    return NarrationResponse(**result)


@router.post("/narrate/each", response_model=NarrationListResponse)
async def narrate_each_context(
    context: ContextObject,
    language: str = Query("en", description="Narration language: en|hi|hinglish|ta|te|bn|mr."),
) -> NarrationListResponse:
    """Narrate EACH detected issue as its own focused Alexa line.

    The frontend calls this instead of ``/narrate`` when it wants to show the
    issues as a *sequence* of floating notifications spoken one-by-one: each
    anomaly gets its own LLM call (so no detail is lost to compression), and the
    list comes back ordered most-severe-first.
    """
    items = await narrator.narrate_each(context, language)
    return NarrationListResponse(
        narrations=[NarrationItem(**item) for item in items]
    )


@router.get("/narrate/debug")
def narrate_debug() -> dict:
    """Diagnostic endpoint — shows which LLM provider is configured and whether
    credentials are available. Never reveals actual secrets."""
    from safety.app.config import get_settings

    settings = get_settings()
    return {
        "llm_provider": settings.llm_provider,
        "groq_api_key_set": bool(settings.groq_api_key),
        "groq_api_key_prefix": settings.groq_api_key[:8] + "..." if settings.groq_api_key else "",
        "groq_model": settings.groq_model,
        "bedrock_model_id": settings.bedrock_model_id,
        "aws_region": settings.aws_region,
        "narrator_timeout_seconds": settings.narrator_timeout_seconds,
    }
