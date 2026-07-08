"""Tests for the Indian-context event kinds and care detectors (H003).

Covers the appliance/care event streams (elderly activity, medicine, morning
geyser, evening dining/TV lights) end to end: deterministic pattern extraction +
the anomaly detectors (inactivity, missed medicine, duration exceeded, device
left on) and the resulting context classification.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from patterns.context_builder import build_context
from patterns.context_builder.anomaly import ROUTINE_ACTIVATIONS
from patterns.models.context import AnomalyType, ContextType
from patterns.models.events import DeviceAction, DeviceType, Event
from patterns.models.patterns import DurationPattern, SequencePattern, TimePattern
from patterns.models.state import HouseholdState
from patterns.pattern_engine import extract_all
from patterns.tests.sample_data_h003 import HOUSEHOLD, generate


def _materialise(payloads):
    return [Event(**p.model_dump()) for p in payloads]


def _mins(hhmm: str) -> int:
    h, m = map(int, hhmm.split(":"))
    return h * 60 + m


def _assert_near(usual_time: str, target_hhmm: str, tol: int = 25) -> None:
    """Assert a learned ``HH:MM`` is within ``tol`` minutes of a target time.

    The seeds add per-day jitter, so the clustered mean lands close to — but not
    exactly on — the nominal time (e.g. 20:58 for a ~21:00 routine).
    """
    assert abs(_mins(usual_time) - _mins(target_hhmm)) <= tol, (
        f"{usual_time} not within {tol} min of {target_hhmm}"
    )


def _clean_history():
    return _materialise(
        generate(
            days=30,
            include_geyser_anomaly=False,
            include_motor_anomaly=False,
            include_left_on=False,
        )
    )


def _patterns():
    return extract_all(HOUSEHOLD, _clean_history())


def _today_satisfied(patterns, now: datetime, skip: str | None) -> list[Event]:
    """Today's activation events for every routine except ``skip``."""
    out: list[Event] = []
    for p in patterns:
        if not isinstance(p, TimePattern) or p.action not in ROUTINE_ACTIVATIONS:
            continue
        if p.device == skip:
            continue
        h, m = map(int, p.usual_time.split(":"))
        out.append(
            Event(
                household_id=HOUSEHOLD,
                device_id=p.device,
                device_type=DeviceType.OTHER,
                room="x",
                action=DeviceAction(p.action),
                triggered_by="x",
                timestamp=now.replace(hour=h, minute=m, second=0, microsecond=0),
            )
        )
    return out


# ─── Pattern extraction ──────────────────────────────────────────────────────


def test_extracts_activity_time_pattern_for_grandpa():
    patterns = _patterns()
    grandpa = [
        p for p in patterns
        if isinstance(p, TimePattern)
        and p.device == "grandpa_activity"
        and p.action == "ACTIVE"
    ]
    assert grandpa, "expected a time pattern for grandpa_activity ACTIVE"
    _assert_near(grandpa[0].usual_time, "06:45")
    assert grandpa[0].confidence >= 0.6


def test_extracts_geyser_duration_pattern():
    patterns = _patterns()
    geyser = [
        p for p in patterns
        if isinstance(p, DurationPattern) and p.device == "bath_geyser"
    ]
    assert geyser, "expected a duration pattern for the morning geyser"
    assert 16 <= geyser[0].usual_duration_minutes <= 24


def test_extracts_evening_off_time_patterns_for_dining_and_hall():
    patterns = _patterns()
    by_device = {
        p.device: p
        for p in patterns
        if isinstance(p, TimePattern) and p.action == "OFF"
    }
    # The dining light and hall lights/TV are switched off around bedtime, giving
    # clean TimePattern(OFF)s (these power the "left on past bedtime" detector).
    assert "dining_light" in by_device
    _assert_near(by_device["dining_light"].usual_time, "21:50")
    assert "hall_tv" in by_device
    _assert_near(by_device["hall_tv"].usual_time, "22:05")


def test_extracts_medicine_time_pattern():
    patterns = _patterns()
    med = [
        p for p in patterns
        if isinstance(p, TimePattern)
        and p.device == "grandma_medicine"
        and p.action == "TAKEN"
    ]
    assert med, "expected a time pattern for grandma_medicine TAKEN"
    _assert_near(med[0].usual_time, "21:00")


def test_extracts_pooja_sequence_and_motor_duration():
    patterns = _patterns()
    sequences = [p for p in patterns if isinstance(p, SequencePattern)]
    assert any(
        any("pooja_lamp:ON" in step for step in s.steps) for s in sequences
    ), "expected the morning pooja sequence"

    motor = [
        p for p in patterns
        if isinstance(p, DurationPattern) and p.device == "water_motor"
    ]
    assert motor and 12 <= motor[0].usual_duration_minutes <= 18


# ─── Care / safety detectors ─────────────────────────────────────────────────


def _now(hour: int, minute: int = 0) -> datetime:
    return datetime.now(timezone.utc).replace(
        hour=hour, minute=minute, second=0, microsecond=0
    )


def test_inactivity_anomaly_when_grandpa_inactive():
    patterns = _patterns()
    now = _now(10, 0)
    state = HouseholdState(household_id=HOUSEHOLD, people_home={"grandpa": True})
    ctx = build_context(
        state, patterns, _today_satisfied(patterns, now, skip="grandpa_activity"), now=now
    )
    assert ctx.context_type == ContextType.CARE_ALERT
    assert any(a.type == AnomalyType.INACTIVITY for a in ctx.anomalies)


def test_device_left_on_when_dining_light_past_bedtime():
    patterns = _patterns()
    now = _now(23, 30)
    # Dining light still on well past its learned ~22:00 bedtime OFF, with the
    # other routines satisfied so only the "left on" flags.
    state = HouseholdState(household_id=HOUSEHOLD, active_devices=["dining_light"])
    ctx = build_context(
        state, patterns, _today_satisfied(patterns, now, skip=None), now=now
    )
    assert any(a.type == AnomalyType.DEVICE_LEFT_ON for a in ctx.anomalies)


def test_duration_exceeded_when_geyser_runs_too_long():
    patterns = _patterns()
    now = _now(7, 0)
    geyser_on = (now - timedelta(minutes=70)).isoformat()  # usual ~20 min
    state = HouseholdState(
        household_id=HOUSEHOLD,
        active_devices=["bath_geyser"],
        device_on_since={"bath_geyser": geyser_on},
    )
    ctx = build_context(
        state, patterns, _today_satisfied(patterns, now, skip=None), now=now
    )
    assert any(a.type == AnomalyType.DURATION_EXCEEDED for a in ctx.anomalies)


def test_missed_medicine_anomaly():
    patterns = _patterns()
    now = _now(22, 45)
    state = HouseholdState(household_id=HOUSEHOLD, people_home={"grandma": True})
    ctx = build_context(
        state, patterns, _today_satisfied(patterns, now, skip="grandma_medicine"), now=now
    )
    assert ctx.context_type == ContextType.CARE_ALERT
    assert any(a.type == AnomalyType.MISSED_MEDICINE for a in ctx.anomalies)


def test_geyser_within_usual_duration_is_not_flagged():
    patterns = _patterns()
    now = _now(6, 15)
    geyser_on = (now - timedelta(minutes=12)).isoformat()  # within usual ~20 min
    state = HouseholdState(
        household_id=HOUSEHOLD,
        active_devices=["bath_geyser"],
        device_on_since={"bath_geyser": geyser_on},
    )
    ctx = build_context(
        state, patterns, _today_satisfied(patterns, now, skip=None), now=now
    )
    assert not any(a.type == AnomalyType.DURATION_EXCEEDED for a in ctx.anomalies)
