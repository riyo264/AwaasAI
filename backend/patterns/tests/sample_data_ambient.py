"""Synthetic 30-day AMBIENT-SOUND history for household AMB1.

Ambient sounds are logged as events under ``ambient_<key>`` (action ``ACTIVE``).
Feeding a month through the SAME deterministic pattern engine makes it learn
*sound routines* AND *count baselines*, which power the sense-making layer
(:mod:`patterns.logic.ambient_sense`):

  * pressure_cooker → ~3 whistles per meal (lunch + dinner) EVERY day, so the
    rate baseline is "~3 per window"; more than that today → flagged.
  * baby_cry        → a few SCATTERED cries per day at no fixed time (surface
    strategy — the LLM judges each).
  * cough           → occasional/quiet, so a live burst stands out.
  * kettle / doorbell / dishes / vacuum → one clean daily routine each.

No floats in event metadata (DynamoDB rejects them) — confidence is an int %.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from patterns.models.events import DeviceAction, DeviceType, EventCreate

HOUSEHOLD = "AMB1"
_rng = random.Random(11)


def _mk(day: datetime, key: str, hour: int, minute: int, jitter: int = 0) -> EventCreate:
    minute += _rng.randint(-jitter, jitter) if jitter else 0
    ts = day.replace(hour=hour, minute=0, second=0, microsecond=0) + timedelta(minutes=minute)
    return EventCreate(
        household_id=HOUSEHOLD, device_id=f"ambient_{key}", device_type=DeviceType.OTHER,
        room="home", action=DeviceAction.ACTIVE, triggered_by="ambient", timestamp=ts,
        metadata={"sound": key, "source": "ambient_seed", "confidence_pct": 90},
    )


def generate(days: int = 30) -> list[EventCreate]:
    events: list[EventCreate] = []
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    for d in range(days, 0, -1):
        day = today - timedelta(days=d)
        is_weekend = day.weekday() >= 5

        # Single clean daily routines (learn usual TIME). A full day of household
        # rhythm — the more routines the engine learns, the more it can tell an
        # EXPECTED sound from an UNUSUAL one.
        events.append(_mk(day, "alarm_clock", 6, 45, 8))      # wake-up
        events.append(_mk(day, "temple_bell", 6, 30, 12))     # morning aarti
        events.append(_mk(day, "kettle_boil", 7, 30, 12))     # morning chai
        events.append(_mk(day, "mixer_grinder", 8, 15, 15))   # breakfast prep
        events.append(_mk(day, "doorbell", 9, 0, 15))         # milk / paper
        events.append(_mk(day, "washing_machine", 10, 15, 20))  # laundry
        events.append(_mk(day, "exhaust_fan", 12, 40, 20))    # lunch cooking
        events.append(_mk(day, "tv_on", 21, 30, 25))          # evening viewing
        events.append(_mk(day, "dishes", 21, 45, 20))         # after-dinner wash
        if not is_weekend:
            events.append(_mk(day, "vacuum", 11, 0, 20))      # weekday cleaning

        # Pressure cooker: ~3 whistles per meal window → count baseline ≈ 3.
        for i in range(3):
            events.append(_mk(day, "pressure_cooker", 12, 50 + i * 10, 3))  # lunch
        for i in range(3):
            events.append(_mk(day, "pressure_cooker", 19, 50 + i * 10, 3))  # dinner

        # Baby: a few scattered cries/day, no fixed schedule (day + occasional night).
        for _ in range(_rng.choice([2, 3, 4])):
            hour = _rng.choice([9, 11, 14, 16, 18, 20, 20, 2])  # weighted toward evening
            events.append(_mk(day, "baby_cry", hour, _rng.randint(0, 59)))

        # Cough: quiet — most days none, sometimes 1–2 (so a live burst is unusual).
        for _ in range(_rng.choice([0, 0, 1, 2])):
            events.append(_mk(day, "cough", _rng.randint(8, 22), _rng.randint(0, 59)))

    return events
