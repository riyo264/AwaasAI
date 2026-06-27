"""Duration-based pattern extraction — v2.

Drop-in replacement for duration.py with the same public interface:

    extract_duration_patterns(household_id, events) -> list[DurationPattern]

Fixes over v1
=============
1. **Circular mean for ``usual_start_time``**
   Plain ``statistics.mean`` treats minute-of-day as a linear number, so a
   device that runs at 23:55 on some days and 00:05 on others produces an
   average of 12:00 (noon) instead of ~00:00.  Unit-circle averaging (convert
   to sin/cos vectors, average, convert back) fixes the midnight-wrap silently.

2. **Spurious-runtime guard**
   A single missed OFF event creates an ON→OFF gap of hours or days that
   dominates the mean and destroys the confidence score.  Any runtime above
   ``MAX_SINGLE_RUNTIME_MINUTES`` (8 h) is discarded before statistics are
   computed.  8 h covers legitimately long devices (overnight AC, continuous
   fan) while rejecting "ON Monday, OFF Friday" pairs.

3. **First-ON latch (sensor bounce / duplicate delivery)**
   In v1 a second consecutive ON event silently overwrites ``on_ts``, making
   the measured runtime start from the *last* ON rather than the *first*.  v2
   ignores every ON while ``on_ts`` is already set, so a bounced sensor cannot
   shorten the measured runtime.

4. **Sample stddev instead of population stddev**
   ``statistics.stdev`` (Bessel-corrected) is statistically correct when the
   samples are a subset of all possible observations.  With 3–10 events,
   ``pstdev`` underestimates spread by up to ~18 %, making the consistency
   score — and therefore confidence — look artificially higher than it is.

5. **Debug logging for filtered patterns**
   Patterns that are silently dropped (too few samples, low confidence) now
   emit ``logging.DEBUG`` lines so the cause is visible without adding any
   production noise.
"""
from __future__ import annotations

import logging
import math
import statistics
from collections import defaultdict

from patterns.app.config import get_settings
from patterns.models.events import Event
from patterns.models.patterns import DurationPattern
from patterns.pattern_engine import confidence as conf

logger = logging.getLogger(__name__)

ON_ACTIONS = {"ON", "OPEN"}
OFF_ACTIONS = {"OFF", "CLOSE"}

# Runtimes beyond this threshold are treated as corrupted data (missed OFF
# event) and discarded before statistics are computed.
# 8 hours covers the longest realistic continuous device usage while reliably
# rejecting multi-day gaps from network / sensor failures.
MAX_SINGLE_RUNTIME_MINUTES: int = 8 * 60  # 480 min


# ─── Internal helpers ─────────────────────────────────────────────────────────


def _circular_mean_minutes(mins: list[int]) -> float:
    """Circular mean of minute-of-day values (0–1439).

    Unlike ``statistics.mean``, this correctly averages values that straddle
    midnight.  For example [1435, 5] (23:55 and 00:05) returns 0 (midnight)
    rather than 720 (noon).

    Algorithm: project each value onto the unit circle as a (sin, cos) vector,
    average the vectors, then convert the resulting angle back to minutes.
    """
    scale = 2 * math.pi / (24 * 60)
    n = len(mins)
    sin_mean = sum(math.sin(m * scale) for m in mins) / n
    cos_mean = sum(math.cos(m * scale) for m in mins) / n
    angle = math.atan2(sin_mean, cos_mean)
    return (angle / scale) % (24 * 60)


def _fmt_hhmm(total_minutes: float) -> str:
    m = int(round(total_minutes)) % (24 * 60)
    return f"{m // 60:02d}:{m % 60:02d}"


# ─── Core pairing logic ───────────────────────────────────────────────────────


def _runtimes_per_device(
    events: list[Event],
) -> dict[str, list[tuple[float, int]]]:
    """Build device → [(runtime_min, start_min_of_day)] from raw events.

    Returns both *how long* the device ran and *when* it started so that the
    caller can emit a pattern saying "runs ~15 min, usually starting ~07:30".

    Behavioural changes vs v1:
    - Fix 3: only the *first* unmatched ON is latched; subsequent ONs before an
      OFF are ignored (prevents sensor bounce from shortening runtimes).
    - Fix 2: pairs whose gap exceeds MAX_SINGLE_RUNTIME_MINUTES are discarded
      and logged at DEBUG rather than corrupting the statistics.
    """
    by_device: dict[str, list[Event]] = defaultdict(list)
    for ev in events:
        by_device[ev.device_id].append(ev)

    runtimes: dict[str, list[tuple[float, int]]] = defaultdict(list)

    for device_id, dev_events in by_device.items():
        dev_events.sort(key=lambda e: e.timestamp)
        on_ts = None
        skipped = 0

        for ev in dev_events:
            if ev.action.value in ON_ACTIONS:
                if on_ts is None:
                    # Fix 3: latch only the first ON; ignore duplicates/bounces.
                    on_ts = ev.timestamp
            elif ev.action.value in OFF_ACTIONS and on_ts is not None:
                minutes = (ev.timestamp - on_ts).total_seconds() / 60.0
                if 0 < minutes <= MAX_SINGLE_RUNTIME_MINUTES:
                    # Fix 2: only accept runtimes within the plausible range.
                    start_min = on_ts.hour * 60 + on_ts.minute
                    runtimes[device_id].append((minutes, start_min))
                else:
                    skipped += 1
                    logger.debug(
                        "device %s: runtime %.1f min outside (0, %d] — "
                        "likely a missed OFF event, discarding",
                        device_id,
                        minutes,
                        MAX_SINGLE_RUNTIME_MINUTES,
                    )
                on_ts = None

        if skipped:
            logger.debug(
                "device %s: %d runtime pair(s) discarded as outliers",
                device_id,
                skipped,
            )

    return runtimes


# ─── Public API — identical signature to duration.py ─────────────────────────


def extract_duration_patterns(
    household_id: str, events: list[Event]
) -> list[DurationPattern]:
    """Extract duration patterns from a window of events.

    For each device that has enough clean ON→OFF samples, emit a
    ``DurationPattern`` describing the device's typical runtime and usual
    start time.  Confidence rewards both frequency (support) and consistency
    (low variance relative to the mean runtime).
    """
    s = get_settings()
    patterns: list[DurationPattern] = []

    for device_id, samples in _runtimes_per_device(events).items():
        if len(samples) < s.min_pattern_occurrences:
            logger.debug(
                "device %s: %d clean sample(s) — need %d, skipping",
                device_id,
                len(samples),
                s.min_pattern_occurrences,
            )
            continue

        runtimes = [r for r, _ in samples]
        start_mins = [st for _, st in samples]

        mean = statistics.mean(runtimes)

        # Fix 4: sample stddev (Bessel-corrected) is more accurate for small N.
        # Guard for the degenerate single-sample case (can only happen if
        # min_pattern_occurrences is set to 1 in config).
        stddev = statistics.stdev(runtimes) if len(runtimes) > 1 else 0.0

        support = conf.support_score(len(runtimes), s.analysis_window_days)
        # Tolerance: allow 25% swing around the mean runtime (floor 1 min).
        consistency = conf.consistency_score(stddev, tolerance=max(mean * 0.25, 1.0))
        score = conf.combine(support, consistency)

        if score < s.min_confidence:
            logger.debug(
                "device %s: confidence %.3f (support=%.3f consistency=%.3f) "
                "below min_confidence=%.2f — skipping",
                device_id,
                score,
                support,
                consistency,
                s.min_confidence,
            )
            continue

        # Fix 1: circular mean correctly averages midnight-crossing start times.
        usual_start = _fmt_hhmm(_circular_mean_minutes(start_mins))

        patterns.append(
            DurationPattern(
                pattern_id=f"DUR#{device_id}",
                household_id=household_id,
                device=device_id,
                usual_duration_minutes=round(mean, 1),
                stddev_minutes=round(stddev, 1),
                usual_start_time=usual_start,
                occurrences=len(runtimes),
                confidence=score,
            )
        )

    return patterns
