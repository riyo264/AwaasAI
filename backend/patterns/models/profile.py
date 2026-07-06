"""User-defined home profile routines.

Users can declare their own recurring schedules (e.g. "fan ON at 07:00 every
weekday") rather than waiting for the pattern engine to learn them from events.
These are stored in the HomeProfiles DynamoDB table and merged into the pattern
pipeline as synthetic TimePattern / DurationPattern objects with confidence=1.0,
so the anomaly engine treats them identically to learned patterns.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field

from patterns.models.events import DeviceAction, DeviceType

ALL_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


class UserRoutineCreate(BaseModel):
    label: str                                    # e.g. "Morning fan"
    device_id: str                                # e.g. "son_room_fan"
    device_type: DeviceType                       # fan / light / ac / tv / ...
    room: str                                     # e.g. "son_room"
    action: DeviceAction                          # ON / OFF / OPEN / CLOSE / ...
    usual_time: str                               # "HH:MM"
    window_minutes: int = 20                      # ± tolerance around usual_time
    days: list[str] = Field(default_factory=lambda: ["all"])  # ["all"] or ["mon","fri",...]
    duration_minutes: float | None = None         # how long the device typically runs


class UserRoutine(UserRoutineCreate):
    routine_id: str = Field(default_factory=lambda: str(uuid4()))
    household_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
