"""Assertion-based regression tests for the deterministic pattern engines.

Covers the happy path of each extractor plus one focused regression test per
bug fixed in duration2.py / time_based2.py / sequence_based_2.py:

duration2
    - circular start-time averaging across midnight
    - missed-OFF runtime guard (spurious long pairs discarded)
    - first-ON latch (sensor bounce cannot shorten a runtime)

time_based2
    - multi-cluster discovery (two daily routines per device)
    - circular mean across midnight
    - boundary-split capture (routine straddling a bucket edge kept whole)
    - non-divisor bucket size still merges across midnight

sequence_based_2
    - empty-steps guard (no pattern with empty steps / blank description)
    - single-linkage chaining recovers the dense core instead of dropping it
    - ARRIVE/LEAVE counts as a device continuation

These are pure unit tests: extractors are functions of the event list only, so
no DynamoDB / wall-clock dependence is involved.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from patterns.app.config import get_settings
from patterns.models.events import Event
from patterns.pattern_engine import extract_all
from patterns.pattern_engine.duration2 import extract_duration_patterns
from patterns.pattern_engine.time_based2 import extract_time_patterns
from patterns.pattern_engine.sequence_based_2 import extract_sequence_patterns

HID = "HTEST"
_BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _ev(device_id, action, ts, *, device_type="other", room="r", triggered_by="sys"):
    return Event(
        household_id=HID,
        device_id=device_id,
        device_type=device_type,
        room=room,
        action=action,
        triggered_by=triggered_by,
        timestamp=ts,
    )


def _at(day, hour, minute):
    return _BASE + timedelta(days=day, hours=hour, minutes=minute)


def _hhmm_to_min(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _circular_off(minute):
    """Distance (min) from midnight on the 24h clock."""
    return min(minute, 1440 - minute)


# ════════════════════════════════════════════════════════════════════ duration


def test_duration_happy_path():
    # Motor ON 09:00, OFF 09:15 every day for 30 days → ~15 min runtime.
    events = []
    for d in range(30):
        events.append(_ev("motor", "ON", _at(d, 9, 0), device_type="motor"))
        events.append(_ev("motor", "OFF", _at(d, 9, 15), device_type="motor"))

    pats = extract_duration_patterns(HID, events)
    assert len(pats) == 1
    p = pats[0]
    assert p.device == "motor"
    assert p.usual_duration_minutes == pytest.approx(15.0, abs=0.5)
    assert p.usual_start_time == "09:00"
    assert p.occurrences == 30
    assert p.confidence >= 0.6


def test_duration_circular_start_time_across_midnight():
    # Runs alternate between starting 23:55 and 00:05 — a linear mean would give
    # ~12:00; the circular mean must land near midnight. A short 2-min runtime
    # keeps the alternating runs from overlapping across the day boundary.
    events = []
    for d in range(30):
        h, m = (23, 55) if d % 2 == 0 else (0, 5)
        on = _at(d, h, m)
        events.append(_ev("lamp", "ON", on, device_type="light"))
        events.append(_ev("lamp", "OFF", on + timedelta(minutes=2), device_type="light"))

    pats = extract_duration_patterns(HID, events)
    assert len(pats) == 1
    start = _hhmm_to_min(pats[0].usual_start_time)
    assert _circular_off(start) <= 5, f"start {pats[0].usual_start_time} not near midnight"
    assert pats[0].usual_start_time != "12:00"


def test_duration_missed_off_runtime_is_discarded():
    # 30 clean 15-min runs + one corrupted pair (missed OFF → 10h gap). The bad
    # pair must be dropped so the mean stays ~15, not inflated.
    events = []
    for d in range(30):
        events.append(_ev("motor", "ON", _at(d, 9, 0), device_type="motor"))
        events.append(_ev("motor", "OFF", _at(d, 9, 15), device_type="motor"))
    # Day 30: ON at 09:00, OFF only 10h later (600 min > 480 cap).
    events.append(_ev("motor", "ON", _at(30, 9, 0), device_type="motor"))
    events.append(_ev("motor", "OFF", _at(30, 19, 0), device_type="motor"))

    pats = extract_duration_patterns(HID, events)
    assert len(pats) == 1
    assert pats[0].usual_duration_minutes == pytest.approx(15.0, abs=0.5)
    assert pats[0].occurrences == 30, "corrupted pair was not discarded"


def test_duration_first_on_latch_ignores_sensor_bounce():
    # Each day a duplicate ON arrives 5 min after the first. Runtime must be
    # measured from the FIRST ON (15 min), not the bounce (10 min).
    events = []
    for d in range(30):
        events.append(_ev("motor", "ON", _at(d, 9, 0), device_type="motor"))
        events.append(_ev("motor", "ON", _at(d, 9, 5), device_type="motor"))  # bounce
        events.append(_ev("motor", "OFF", _at(d, 9, 15), device_type="motor"))

    pats = extract_duration_patterns(HID, events)
    assert len(pats) == 1
    assert pats[0].usual_duration_minutes == pytest.approx(15.0, abs=0.5)


def test_duration_below_min_occurrences_emits_nothing():
    events = []
    for d in range(2):  # fewer than min_pattern_occurrences (3)
        events.append(_ev("motor", "ON", _at(d, 9, 0), device_type="motor"))
        events.append(_ev("motor", "OFF", _at(d, 9, 15), device_type="motor"))
    assert extract_duration_patterns(HID, events) == []


# ═══════════════════════════════════════════════════════════════════ time-based


def test_time_happy_path_single_routine():
    events = [_ev("porch", "ON", _at(d, 19, 0), device_type="light") for d in range(30)]
    pats = extract_time_patterns(HID, events)
    assert len(pats) == 1
    assert pats[0].usual_time == "19:00"
    assert pats[0].occurrences == 30
    assert pats[0].confidence >= 0.6


def test_time_multi_cluster_discovers_two_routines():
    # Light ON at 04:00 AND 18:00 daily — v1 would keep only the dominant one.
    events = []
    for d in range(30):
        events.append(_ev("light", "ON", _at(d, 4, 0), device_type="light"))
        events.append(_ev("light", "ON", _at(d, 18, 0), device_type="light"))
    pats = extract_time_patterns(HID, events)
    times = sorted(p.usual_time for p in pats)
    assert times == ["04:00", "18:00"], f"expected two routines, got {times}"


def test_time_circular_mean_across_midnight():
    # Events alternate 23:58 / 00:02 → single cluster near 00:00, not 12:00.
    events = []
    for d in range(30):
        h, m = (23, 58) if d % 2 == 0 else (0, 2)
        events.append(_ev("light", "ON", _at(d, h, m), device_type="light"))
    pats = extract_time_patterns(HID, events)
    assert len(pats) == 1, f"midnight routine split into {len(pats)} clusters"
    assert _circular_off(_hhmm_to_min(pats[0].usual_time)) <= 5
    assert pats[0].usual_time != "12:00"


def test_time_boundary_split_is_captured():
    # A 19:00 routine whose events straddle the 30-min bucket edge (18:58/19:02).
    # Old v2 filtered each half below the threshold and emitted nothing.
    events = []
    for d in range(30):
        h, m = (18, 58) if d % 2 == 0 else (19, 2)
        events.append(_ev("light", "ON", _at(d, h, m), device_type="light"))
    pats = extract_time_patterns(HID, events)
    assert len(pats) == 1, "boundary-split routine was dropped"
    assert abs(_hhmm_to_min(pats[0].usual_time) - 19 * 60) <= 5
    assert pats[0].occurrences == 30


def test_time_non_divisor_bucket_still_merges_midnight(monkeypatch):
    # bucket_size=50 does NOT divide 1440 evenly; the old total_buckets guard
    # mis-fired. With circular distance, the midnight routine still clusters.
    from patterns.pattern_engine import time_based2

    s = get_settings().model_copy(update={"time_bucket_minutes": 50})
    monkeypatch.setattr(time_based2, "get_settings", lambda: s)

    events = []
    for d in range(30):
        h, m = (23, 58) if d % 2 == 0 else (0, 2)
        events.append(_ev("light", "ON", _at(d, h, m), device_type="light"))
    pats = time_based2.extract_time_patterns(HID, events)
    assert len(pats) == 1
    assert _circular_off(_hhmm_to_min(pats[0].usual_time)) <= 5


# ═════════════════════════════════════════════════════════════════════ sequence


def test_sequence_happy_path():
    # a→b→c within a couple of minutes, same room/trigger, daily for 20 days.
    events = []
    for d in range(20):
        events.append(_ev("a", "ON", _at(d, 7, 0), room="lr"))
        events.append(_ev("b", "ON", _at(d, 7, 1), room="lr"))
        events.append(_ev("c", "ON", _at(d, 7, 2), room="lr"))
    pats = extract_sequence_patterns(HID, events)
    assert len(pats) >= 1
    main = max(pats, key=lambda p: p.occurrences)
    assert main.steps == ["a:ON", "b:ON", "c:ON"]
    assert main.steps  # never empty
    assert main.confidence >= 0.6


def test_sequence_no_pattern_has_empty_steps():
    # Whatever the data, an emitted SequencePattern must carry real steps.
    events = []
    for d in range(20):
        events.append(_ev("a", "ON", _at(d, 7, 0), room="lr"))
        events.append(_ev("b", "ON", _at(d, 7, 1), room="lr"))
    pats = extract_sequence_patterns(HID, events)
    for p in pats:
        assert p.steps, "emitted a pattern with empty steps"
        assert p.description, "emitted a pattern with blank description"


def test_sequence_empty_steps_guard_suppresses_pattern():
    # Construct a 4-cycle cluster (AB, BC, CD, DA): every step appears in exactly
    # 2/4 sessions (50% < MIN_STEP_SUPPORT 60%) → empty representative. With high
    # cohesion + zero time-variance the confidence would otherwise clear the bar,
    # so this proves the empty-steps guard (not the confidence filter) suppresses it.
    from patterns.pattern_engine.sequence_based_2 import (
        _CanonicalSession,
        _Edge,
        _generate_patterns,
    )

    def cs(sig):
        return _CanonicalSession(
            session=None,
            signature=tuple(sig),
            start_minute=600,
            duration=5,
            length=len(sig),
            devices=frozenset(x.split(":")[0] for x in sig),
            rooms=frozenset({"r"}),
            triggers=frozenset({"t"}),
        )

    sessions = [
        cs(["a:ON", "b:ON"]),
        cs(["b:ON", "c:ON"]),
        cs(["c:ON", "d:ON"]),
        cs(["d:ON", "a:ON"]),
    ]
    edges = [_Edge(i, j, 0.9) for i in range(4) for j in range(i + 1, 4)]
    pats = _generate_patterns(HID, [[0, 1, 2, 3]], sessions, edges, get_settings())
    assert pats == [], "empty-steps cluster was not suppressed"


def test_sequence_chaining_recovers_dense_core():
    # A~B and B~C strong (0.80) but A~C absent: the connected component {A,B,C}
    # has cohesion 0.53 and was dropped wholesale. It must now yield the {A,B}
    # core instead.
    from patterns.pattern_engine.sequence_based_2 import _Edge, _cohesive_clusters

    edges = [_Edge(0, 1, 0.80), _Edge(1, 2, 0.80)]
    out = _cohesive_clusters([[0, 1, 2]], edges)
    assert [0, 1] in out, f"dense core not recovered: {out}"


def test_sequence_cohesive_component_kept_whole():
    # A genuine clique must be preserved exactly (no regression for valid clusters).
    from patterns.pattern_engine.sequence_based_2 import _Edge, _cohesive_clusters

    edges = [_Edge(0, 1, 0.9), _Edge(1, 2, 0.9), _Edge(0, 2, 0.9)]
    assert _cohesive_clusters([[0, 1, 2]], edges) == [[0, 1, 2]]


def test_device_continuation_recognises_arrive_leave():
    from patterns.pattern_engine.sequence_based_2 import _device_continuation

    t = _at(0, 9, 0)
    arrive = _ev("p", "ARRIVE", t, device_type="presence")
    leave = _ev("p", "LEAVE", t + timedelta(minutes=1), device_type="presence")
    on = _ev("m", "ON", t, device_type="motor")
    off = _ev("m", "OFF", t + timedelta(minutes=1), device_type="motor")

    assert _device_continuation(arrive, leave) is True
    assert _device_continuation(on, off) is True
    # Different devices are never a continuation.
    assert _device_continuation(arrive, off) is False


# ════════════════════════════════════════════════════════════════ integration


def test_extract_all_on_h003_has_no_degenerate_patterns():
    from patterns.tests.sample_data_h003 import generate

    events = [Event(**e.model_dump()) for e in generate()]
    pats = extract_all("H003", events)

    assert pats, "extract_all produced no patterns"
    for p in pats:
        assert 0.0 <= p.confidence <= 1.0
        assert p.occurrences >= 1
        if p.pattern_type.value == "sequence":
            assert p.steps, f"sequence pattern {p.pattern_id} has empty steps"
            assert p.description
