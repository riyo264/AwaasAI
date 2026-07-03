"""Context API: produce the AI-ready context object (Bedrock hand-off).

This endpoint is the MVP's final deliverable. It returns the structured
:class:`ContextObject`. In a future phase this payload is forwarded to Amazon
Bedrock for reasoning — that step is intentionally NOT implemented here.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from patterns.models.context import ContextObject
from patterns.logic import context_service, narrator

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
    return context_service.evaluate_context(
        household_id,
        active_devices=body.active_devices,
        people_home=body.people_home,
        device_on_since=body.device_on_since,
        now=_resolve_now(body.current_time),
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
    from patterns.app.config import get_settings

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
