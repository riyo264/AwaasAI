"""Synthetic 30-day scenario for the Adaptive Safety engine: an elderly couple
living alone (household E001) — the primary use case.

Two seniors, Ramesh (Grandpa) and Saroja (Grandma), live independently in their
hometown while their children work in other cities. Alexa learns their daily
rhythm and watches health, home-safety, and security so it can act like a
digital family member.

╔══════════════════════════════════════════════════════════════════════════════
║  ROUTINE / SIGNAL → EVENT MODEL → WHAT THE SAFETY ENGINE DOES
╠══════════════════════════════════════════════════════════════════════════════
║  Wake up        grandpa_activity ACTIVE ~06:30   → TimePattern; absence →
║                                                    INACTIVITY / GLOBAL_INACTIVITY
║  Balcony walk   grandpa_activity ACTIVE ~07:00 (balcony room)
║  Morning pooja  pooja_lamp:ON → temple_bell:ON → bhajan_speaker:ON ~07:30
║                                                  → SequencePattern
║  Breakfast      kitchen_activity ACTIVE ~08:00
║  Morning meds   grandpa_medicine TAKEN ~09:00    → TimePattern; absence →
║                                                    MISSED_MEDICINE
║  Grandma meds   grandma_medicine TAKEN ~09:15 / ~21:15
║  Evening walk   main_door OPEN→CLOSE ~17:00       → leaves the house briefly
║  Night meds     grandpa_medicine TAKEN ~21:00
║  Sleep          activity stops by ~22:00          → night window begins
║
║  HOME-SAFETY devices (watched continuously):
║    main_door, bedroom_window  → UNSAFE_AT_NIGHT if open 22:00–06:00
║    kitchen_gas_stove ~20 min  → DURATION_EXCEEDED if left running
║    water_motor ~15 min        → DURATION_EXCEEDED (tank overflow)
║  HEALTH:
║    grandpa_wearable ALERT/SOS → HEALTH_ALERT / SOS (emergency)
╚══════════════════════════════════════════════════════════════════════════════

"Today" anomalies are toggled by flags so the dashboard demo can show each
safety scenario (inactivity, gas left on, window open at night, SOS, etc).
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from safety.models.events import DeviceAction, DeviceType, EventCreate
from safety.models.safety import PersonProfile, Vulnerability

HOUSEHOLD = "E001"
_rng = random.Random(21)


def profiles() -> list[PersonProfile]:
    """The two seniors who live here, plus children listed as emergency contacts."""
    return [
        PersonProfile(
            person_id="grandpa",
            display_name="Ramesh (Grandpa)",
            vulnerability=Vulnerability.ELDERLY,
            relation="father",
            wearable_id="grandpa_wearable",
            emergency_contacts=["son_bangalore", "daughter_pune"],
        ),
        PersonProfile(
            person_id="grandma",
            display_name="Saroja (Grandma)",
            vulnerability=Vulnerability.ELDERLY,
            relation="mother",
            emergency_contacts=["son_bangalore", "daughter_pune"],
        ),
    ]


def _at(day: datetime, hour: int, minute: int, jitter: int = 0) -> datetime:
    minute += _rng.randint(-jitter, jitter) if jitter else 0
    base = day.replace(hour=hour, minute=0, second=0, microsecond=0)
    return base + timedelta(minutes=minute)


def generate(
    days: int = 30,
    *,
    include_inactivity: bool = False,
    include_gas_left_on: bool = False,
    include_window_night: bool = False,
    include_sos: bool = False,
    include_health_alert: bool = False,
    include_motor_anomaly: bool = False,
) -> list[EventCreate]:
    events: list[EventCreate] = []
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    def add(device_id, device_type, room, action, ts, triggered_by="system", metadata=None):
        events.append(
            EventCreate(
                household_id=HOUSEHOLD, device_id=device_id, device_type=device_type,
                room=room, action=action, triggered_by=triggered_by,
                timestamp=ts, metadata=metadata,
            )
        )

    for d in range(days, 0, -1):
        day = today - timedelta(days=d)

        # Wake up ~06:30 (bedroom)
        add("grandpa_activity", DeviceType.ACTIVITY, "bedroom", DeviceAction.ACTIVE,
            _at(day, 6, 30, jitter=10), triggered_by="grandpa")
        add("grandma_activity", DeviceType.ACTIVITY, "bedroom", DeviceAction.ACTIVE,
            _at(day, 6, 40, jitter=10), triggered_by="grandma")

        # Balcony ~07:00
        add("grandpa_activity", DeviceType.ACTIVITY, "balcony", DeviceAction.ACTIVE,
            _at(day, 7, 0, jitter=10), triggered_by="grandpa")

        # Morning pooja ~07:30 (lamp -> bell -> bhajan)
        p_on = _at(day, 7, 30, jitter=6)
        add("pooja_lamp", DeviceType.LIGHT, "pooja_room", DeviceAction.ON, p_on, "grandma")
        add("temple_bell", DeviceType.OTHER, "pooja_room", DeviceAction.ON,
            p_on + timedelta(minutes=1), "grandma")
        add("bhajan_speaker", DeviceType.OTHER, "pooja_room", DeviceAction.ON,
            p_on + timedelta(minutes=2), "grandma")
        add("pooja_lamp", DeviceType.LIGHT, "pooja_room", DeviceAction.OFF,
            p_on + timedelta(minutes=25 + _rng.randint(-3, 3)), "grandma")
        add("temple_bell", DeviceType.OTHER, "pooja_room", DeviceAction.OFF,
            p_on + timedelta(minutes=26 + _rng.randint(-3, 3)), "grandma")
        add("bhajan_speaker", DeviceType.OTHER, "pooja_room", DeviceAction.OFF,
            p_on + timedelta(minutes=27 + _rng.randint(-3, 3)), "grandma")

        # Breakfast ~08:00 (kitchen)
        add("kitchen_activity", DeviceType.ACTIVITY, "kitchen", DeviceAction.ACTIVE,
            _at(day, 8, 0, jitter=10), triggered_by="grandma")

        # Morning medicine ~09:00 / ~09:15
        add("grandpa_medicine", DeviceType.MEDICINE, "bedroom", DeviceAction.TAKEN,
            _at(day, 9, 0, jitter=8), triggered_by="grandpa")
        add("grandma_medicine", DeviceType.MEDICINE, "bedroom", DeviceAction.TAKEN,
            _at(day, 9, 15, jitter=8), triggered_by="grandma")

        # Water motor ~15 min ~09:30
        m_on = _at(day, 9, 30, jitter=8)
        add("water_motor", DeviceType.MOTOR, "utility", DeviceAction.ON, m_on)
        add("water_motor", DeviceType.MOTOR, "utility", DeviceAction.OFF,
            m_on + timedelta(minutes=15 + _rng.randint(-2, 2)))

        # Midday living-room activity ~13:00
        add("living_activity", DeviceType.ACTIVITY, "living_room", DeviceAction.ACTIVE,
            _at(day, 13, 0, jitter=20), triggered_by="grandpa")

        # Evening walk ~17:00 (door open then closed shortly after)
        d_open = _at(day, 17, 0, jitter=10)
        add("main_door", DeviceType.DOOR, "entrance", DeviceAction.OPEN, d_open, "grandpa")
        add("main_door", DeviceType.DOOR, "entrance", DeviceAction.CLOSE,
            d_open + timedelta(minutes=2), "grandpa")

        # Dinner cooking on the gas stove ~19:30, ~20 min
        g_on = _at(day, 19, 30, jitter=8)
        add("kitchen_gas_stove", DeviceType.GAS, "kitchen", DeviceAction.ON, g_on, "grandma")
        add("kitchen_gas_stove", DeviceType.GAS, "kitchen", DeviceAction.OFF,
            g_on + timedelta(minutes=20 + _rng.randint(-3, 3)), "grandma")

        # Living-room light evening ON ~18:30, OFF ~22:00
        add("living_room_light", DeviceType.LIGHT, "living_room", DeviceAction.ON,
            _at(day, 18, 30, jitter=8))
        add("living_room_light", DeviceType.LIGHT, "living_room", DeviceAction.OFF,
            _at(day, 22, 0, jitter=10))

        # Night medicine ~21:00 / ~21:15
        add("grandpa_medicine", DeviceType.MEDICINE, "bedroom", DeviceAction.TAKEN,
            _at(day, 21, 0, jitter=8), triggered_by="grandpa")
        add("grandma_medicine", DeviceType.MEDICINE, "bedroom", DeviceAction.TAKEN,
            _at(day, 21, 15, jitter=8), triggered_by="grandma")

        # Sleep — last activity ~21:45
        add("grandpa_activity", DeviceType.ACTIVITY, "bedroom", DeviceAction.ACTIVE,
            _at(day, 21, 45, jitter=10), triggered_by="grandpa")

    # ───────────── TODAY: optional injected safety scenarios ─────────────
    now = datetime.now(timezone.utc)

    # Always seed this morning's normal wake so the home isn't trivially "silent"
    # unless we are explicitly demoing inactivity.
    
    def _today_at(hour: int, minute: int) -> datetime:
        return today.replace(hour=hour, minute=minute, second=0, microsecond=0)

    def _seed_past(device_id, device_type, room, action, hour, minute, by="system"):
        """Seed a momentary routine event for TODAY only when its usual time has
        already passed. This is what stops ordinary morning/daytime routines from
        being mis-read as 'missed' (medicine, activity, pooja, …) when the
        dashboard is viewed at the real wall-clock."""
        ts = _today_at(hour, minute)
        if ts <= now:
            add(device_id, device_type, room, action, ts, by)
    
    
    if not include_inactivity:
        _seed_past("grandpa_activity", DeviceType.ACTIVITY, "bedroom", DeviceAction.ACTIVE, 6, 30, "grandpa")
        _seed_past("grandma_activity", DeviceType.ACTIVITY, "bedroom", DeviceAction.ACTIVE, 6, 40, "grandma")
        _seed_past("grandpa_activity", DeviceType.ACTIVITY, "balcony", DeviceAction.ACTIVE, 7, 0, "grandpa")

        # Morning pooja (lamp -> bell -> bhajan) — seeded only if fully past so we
        # never leave the lamp 'on'.
        if _today_at(7, 57) <= now:
            add("pooja_lamp", DeviceType.LIGHT, "pooja_room", DeviceAction.ON, _today_at(7, 30), "grandma")
            add("temple_bell", DeviceType.OTHER, "pooja_room", DeviceAction.ON, _today_at(7, 31), "grandma")
            add("bhajan_speaker", DeviceType.OTHER, "pooja_room", DeviceAction.ON, _today_at(7, 32), "grandma")
            add("pooja_lamp", DeviceType.LIGHT, "pooja_room", DeviceAction.OFF, _today_at(7, 55), "grandma")
            add("temple_bell", DeviceType.OTHER, "pooja_room", DeviceAction.OFF, _today_at(7, 56), "grandma")
            add("bhajan_speaker", DeviceType.OTHER, "pooja_room", DeviceAction.OFF, _today_at(7, 57), "grandma")

        _seed_past("kitchen_activity", DeviceType.ACTIVITY, "kitchen", DeviceAction.ACTIVE, 8, 0, "grandma")
        _seed_past("grandpa_medicine", DeviceType.MEDICINE, "bedroom", DeviceAction.TAKEN, 9, 0, "grandpa")
        _seed_past("grandma_medicine", DeviceType.MEDICINE, "bedroom", DeviceAction.TAKEN, 9, 15, "grandma")

        # Water motor ~15 min (skipped when demoing the motor anomaly).
        if not include_motor_anomaly and _today_at(9, 45) <= now:
            add("water_motor", DeviceType.MOTOR, "utility", DeviceAction.ON, _today_at(9, 30))
            add("water_motor", DeviceType.MOTOR, "utility", DeviceAction.OFF, _today_at(9, 45))

        _seed_past("living_activity", DeviceType.ACTIVITY, "living_room", DeviceAction.ACTIVE, 13, 0, "grandpa")

        # Evening walk (door open -> close).
        if _today_at(17, 2) <= now:
            add("main_door", DeviceType.DOOR, "entrance", DeviceAction.OPEN, _today_at(17, 0), "grandpa")
            add("main_door", DeviceType.DOOR, "entrance", DeviceAction.CLOSE, _today_at(17, 2), "grandpa")

        # Dinner on the gas stove (skipped when demoing gas-left-on).
        if not include_gas_left_on and _today_at(19, 50) <= now:
            add("kitchen_gas_stove", DeviceType.GAS, "kitchen", DeviceAction.ON, _today_at(19, 30), "grandma")
            add("kitchen_gas_stove", DeviceType.GAS, "kitchen", DeviceAction.OFF, _today_at(19, 50), "grandma")

        # Living-room light (ON 18:30 -> OFF 22:00) — seed only once fully past.
        if _today_at(22, 0) <= now:
            add("living_room_light", DeviceType.LIGHT, "living_room", DeviceAction.ON, _today_at(18, 30))
            add("living_room_light", DeviceType.LIGHT, "living_room", DeviceAction.OFF, _today_at(22, 0))

        _seed_past("grandpa_medicine", DeviceType.MEDICINE, "bedroom", DeviceAction.TAKEN, 21, 0, "grandpa")
        _seed_past("grandma_medicine", DeviceType.MEDICINE, "bedroom", DeviceAction.TAKEN, 21, 15, "grandma")

        # A fresh sign of life in the last half hour so a normal home is never
        # trivially flagged as inactive.
        add("grandpa_activity", DeviceType.ACTIVITY, "bedroom", DeviceAction.ACTIVE,
            now - timedelta(minutes=30), triggered_by="grandpa")

    if include_gas_left_on:
        # Gas stove switched on and never turned off (usual ~20 min).
        add("kitchen_gas_stove", DeviceType.GAS, "kitchen", DeviceAction.ON,
            now - timedelta(minutes=70), "grandma")

    if include_motor_anomaly:
        add("water_motor", DeviceType.MOTOR, "utility", DeviceAction.ON,
            now - timedelta(minutes=40))

    if include_window_night:
        # Bedroom window opened and left open (night window check is clock-driven).
        add("bedroom_window", DeviceType.WINDOW, "bedroom", DeviceAction.OPEN,
            now - timedelta(hours=2), "grandpa")

    if include_health_alert:
        add("grandpa_wearable", DeviceType.WEARABLE, "bedroom", DeviceAction.ALERT,
            now - timedelta(minutes=10), "grandpa",
            metadata={"signal": "heart_rate", "value": 44, "threshold": "<50 bpm"})

    if include_sos:
        add("grandpa_wearable", DeviceType.WEARABLE, "living_room", DeviceAction.SOS,
            now - timedelta(minutes=5), "grandpa")

    return events
