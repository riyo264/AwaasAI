"""Pydantic models for the AI-ready Context Object.

This is the final artefact of the MVP. It is the structured payload that, in a
future phase, will be handed to Amazon Bedrock for reasoning. Today we stop
once this object is built and validated.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class ContextType(str, Enum):
    DEPARTURE_ANOMALY = "departure_anomaly"
    DURATION_ANOMALY = "duration_anomaly"
    ROUTINE_SUGGESTION = "routine_suggestion"
    # --- Indian-context, people-centric situations ---
    CARE_ALERT = "care_alert"          # elderly inactivity / missed medicine / missed return
    SECURITY_ALERT = "security_alert"  # someone active outside the usual schedule
    NORMAL = "normal"


class AnomalyType(str, Enum):
    DEVICE_LEFT_ON = "device_left_on"
    DURATION_EXCEEDED = "duration_exceeded"
    MISSED_ROUTINE = "missed_routine"
    DEVICE_ACTIVE_TOO_LONG = "device_active_too_long"
    # --- People-centric (care / safety / security) ---
    INACTIVITY = "inactivity"                # elderly person's usual activity not seen
    MISSED_ARRIVAL = "missed_arrival"        # person hasn't returned as usual (e.g. child)
    MISSED_MEDICINE = "missed_medicine"      # medicine routine not confirmed
    UNEXPECTED_ACTIVITY = "unexpected_activity"  # entry/activity outside the learned schedule


class Anomaly(BaseModel):
    type: AnomalyType
    device: str | None = None
    detail: str | None = None
    related_pattern_id: str | None = None
    severity: str = Field(default="medium", examples=["low", "medium", "high"])


class RelevantPattern(BaseModel):
    pattern_id: str
    pattern_type: str
    description: str
    confidence: float
    time: str | None = None   # "HH:MM" the routine is anchored to, when known


class PausedRoutine(BaseModel):
    """A learned routine the day-aware filter paused for today (e.g. a weekday
    school run that doesn't apply on a Sunday)."""

    pattern_id: str
    description: str
    reason: str


class DayAdaptation(BaseModel):
    """Records how the learned routines were adapted for the current day.

    On weekends and festival days a subset of strictly-weekday routines is
    *paused* so they don't produce false 'missed routine' anomalies. On an
    ordinary weekday this is inactive and no routine is touched.
    """

    active: bool = False              # was any pausing applied today
    day_type: str = "weekday"         # "weekday" | "weekend"
    festival: str | None = None       # festival name, when the day is one
    llm_powered: bool = False         # True if the LLM decided, False if fallback
    kept_count: int = 0               # routines still expected today
    paused: list[PausedRoutine] = Field(default_factory=list)


class ContextObject(BaseModel):
    """The structured context ready to be sent to Bedrock (future phase)."""

    context_type: ContextType
    household_id: str
    current_time: str  # "HH:MM" local clock for human-readable reasoning
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    people_home: dict[str, bool] = Field(default_factory=dict)
    active_devices: list[str] = Field(default_factory=list)

    relevant_patterns: list[RelevantPattern] = Field(default_factory=list)
    anomalies: list[Anomaly] = Field(default_factory=list)

    # How routines were adapted for today (weekend / festival pausing).
    day_adaptation: DayAdaptation | None = None

    # Compact recent-event tail to give the LLM short-term memory.
    recent_events: list[dict] = Field(default_factory=list)
