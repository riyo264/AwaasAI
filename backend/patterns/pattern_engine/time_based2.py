"""Time-based pattern extraction — v2 (multi-cluster, circular-time).

Drop-in replacement for time_based.py with the same public interface:

    extract_time_patterns(household_id, events) -> list[TimePattern]

Fixes and improvements over v1
================================
1. **Multi-cluster discovery**
   v1 picks only the single dominant time bucket per (device, action) pair.
   A light that turns ON at 04:00 every morning AND at 18:00 every evening
   produced one pattern in v1.  v2 discovers all significant routine clusters
   independently, so both patterns are emitted.

2. **Circular mean and circular stddev**
   v1 uses ``statistics.mean`` on raw minutes-of-day, which makes a routine
   split across midnight (23:58 and 00:02) average to 12:00.  v2 uses
   unit-circle projection for both mean and stddev, so midnight-crossing
   clusters are computed correctly.

3. **Midnight-aware, boundary-safe clustering**
   v1's sliding-window cluster (``abs(m - center) <= bucket``) is linear and
   breaks at midnight.  v2 clusters greedily: it anchors on the densest bin
   and absorbs events within one bucket-width using CIRCULAR distance, so a
   routine spanning 23:50–00:10 becomes one cluster, and a routine whose
   events straddle a bin boundary (18:58 / 19:02) is captured whole instead
   of being split and dropped.

4. **Relative dominance filter**
   Every candidate cluster must have at least ``RELATIVE_DOMINANCE_THRESHOLD``
   (40%) of the strongest cluster's support.  This prevents low-count
   accidental clusters from producing spurious patterns while still allowing
   legitimate secondary routines to survive.

5. **Sample stddev for small N**
   ``statistics.stdev`` (Bessel-corrected) is used instead of ``pstdev``,
   matching the correction applied in duration2.py.

Pattern IDs in v2 include the cluster time (e.g. ``TIME#fan#ON@18:00``) so
multiple routines for the same (device, action) pair have distinct, stable IDs.

Algorithm summary
=================
1. Group events by (device_id, action) → list of minute-of-day values.
2. Greedily anchor on the densest ``time_bucket_minutes``-wide bin and absorb
   all unassigned events within one bucket-width (circular distance); repeat
   until no remaining bin reaches ``min_pattern_occurrences``.
3. For each cluster, compute circular mean and circular stddev.
4. Discard clusters below ``RELATIVE_DOMINANCE_THRESHOLD × dominant_support``.
5. Score each surviving cluster; emit a ``TimePattern`` when confidence clears
   ``min_confidence``.
"""
from __future__ import annotations

import logging
import math
import statistics
from collections import defaultdict
from datetime import datetime

from patterns.app.config import get_settings
from patterns.models.events import Event
from patterns.models.patterns import TimePattern
from patterns.pattern_engine import confidence as conf

logger = logging.getLogger(__name__)

# A candidate cluster must have at least this fraction of the strongest
# cluster's support to be promoted to a pattern.  Prevents low-frequency
# accidental clusters (e.g. one-off events that happen to land in the same
# bucket twice) from becoming spurious routines.
RELATIVE_DOMINANCE_THRESHOLD: float = 0.40


# ─── Circular-time helpers ────────────────────────────────────────────────────


def _minutes_of_day(ts: datetime) -> int:
    return ts.hour * 60 + ts.minute


def _fmt_hhmm(total_minutes: float) -> str:
    m = int(round(total_minutes)) % (24 * 60)
    return f"{m // 60:02d}:{m % 60:02d}"


def _circular_mean(mins: list[int]) -> float:
    """Circular mean of minute-of-day values (0–1439).

    Projects each value onto a unit circle, averages the vectors, and converts
    back.  Correctly handles samples that straddle midnight — e.g. [1438, 2]
    returns 0 (midnight) rather than 720 (noon).
    """
    scale = 2 * math.pi / (24 * 60)
    n = len(mins)
    sin_mean = sum(math.sin(m * scale) for m in mins) / n
    cos_mean = sum(math.cos(m * scale) for m in mins) / n
    angle = math.atan2(sin_mean, cos_mean)
    return (angle / scale) % (24 * 60)


def _circular_dist(a: float, b: float) -> float:
    """Shortest arc between two times on a 24-hour clock (0–720 min)."""
    diff = abs(a - b)
    return min(diff, 24 * 60 - diff)


def _circular_stddev(mins: list[int], center: float) -> float:
    """Stddev of circular distances from the circular mean.

    Uses sample stddev (Bessel-corrected) since the events are a sample of all
    possible observations, not the full population.
    """
    distances = [_circular_dist(m, center) for m in mins]
    return statistics.stdev(distances) if len(distances) > 1 else 0.0


# ─── Public API — identical signature to time_based.py ───────────────────────


def extract_time_patterns(
    household_id: str, events: list[Event]
) -> list[TimePattern]:
    """Extract time-of-day patterns from a window of events.

    Emits one ``TimePattern`` per significant routine cluster found for each
    (device, action) pair — multiple patterns per device are supported.
    """
    s = get_settings()
    bucket_size = s.time_bucket_minutes

    # (device_id, action) -> [minutes_of_day, ...]
    groups: dict[tuple[str, str], list[int]] = defaultdict(list)
    for ev in events:
        groups[(ev.device_id, ev.action.value)].append(
            _minutes_of_day(ev.timestamp)
        )

    patterns: list[TimePattern] = []

    for (device_id, action), minutes in groups.items():
        if len(minutes) < s.min_pattern_occurrences:
            logger.debug(
                "(%s, %s): %d event(s) — need %d, skipping",
                device_id, action, len(minutes), s.min_pattern_occurrences,
            )
            continue

        # ── Steps 1–4: build routine clusters (anchor + circular window) ──
        # Repeatedly take the densest ``bucket_size``-wide bin as an anchor and
        # absorb every still-unassigned event within one bucket-width of that
        # anchor's centre, measured by CIRCULAR distance so midnight wraps
        # correctly. This reproduces the proven single-routine window logic of
        # time_based.py (v1) but yields *all* daily routines, not just the
        # dominant one. Because the window straddles bucket boundaries, a
        # routine whose events split across a boundary (e.g. 18:58 / 19:02) is
        # captured as one cluster instead of being dropped — and because every
        # cluster is bounded to ±bucket_size around its anchor it can never
        # "chain" across the whole day.
        unassigned = list(minutes)
        time_clusters: list[list[int]] = []
        while len(unassigned) >= s.min_pattern_occurrences:
            counts: dict[int, int] = defaultdict(int)
            for m in unassigned:
                counts[m // bucket_size] += 1
            anchor = max(counts, key=lambda b: counts[b])
            if counts[anchor] < s.min_pattern_occurrences:
                break  # densest remaining bin is just scatter → stop
            center = anchor * bucket_size + bucket_size / 2
            cluster = [m for m in unassigned if _circular_dist(m, center) <= bucket_size]
            time_clusters.append(cluster)
            unassigned = [m for m in unassigned if _circular_dist(m, center) > bucket_size]

        if not time_clusters:
            logger.debug(
                "(%s, %s): no bin reached %d occurrences, skipping",
                device_id, action, s.min_pattern_occurrences,
            )
            continue

        # ── Step 5: compute circular statistics per cluster ───────────────
        cluster_stats = []
        for vals in time_clusters:
            mean_min = _circular_mean(vals)
            stddev = _circular_stddev(vals, mean_min)
            cluster_stats.append(
                {
                    "mean": mean_min,
                    "stddev": stddev,
                    "occurrences": len(vals),
                }
            )

        # ── Step 6: relative dominance filter ────────────────────────────
        # A secondary routine (morning prayer at 04:00, evening prayer at
        # 18:00) is only kept if it happens often enough relative to the
        # strongest routine so we don't promote random noise.
        dominant_support = max(c["occurrences"] for c in cluster_stats)
        significant = [
            c for c in cluster_stats
            if c["occurrences"] >= dominant_support * RELATIVE_DOMINANCE_THRESHOLD
        ]

        # ── Step 7: confidence scoring + emit ────────────────────────────
        for cluster in significant:
            support = conf.support_score(
                cluster["occurrences"], s.analysis_window_days
            )
            consistency = conf.consistency_score(
                cluster["stddev"], tolerance=bucket_size
            )
            score = conf.combine(support, consistency)

            if score < s.min_confidence:
                logger.debug(
                    "(%s, %s) cluster @%s: confidence %.3f "
                    "(support=%.3f consistency=%.3f) below min_confidence=%.2f",
                    device_id, action,
                    _fmt_hhmm(cluster["mean"]),
                    score, support, consistency, s.min_confidence,
                )
                continue

            usual_time = _fmt_hhmm(cluster["mean"])
            # window_minutes: at minimum one full bucket, expanded when the
            # cluster is naturally wider (high circular stddev).
            window = max(bucket_size, math.ceil(cluster["stddev"]))

            # Pattern IDs include the cluster time so multiple routines for
            # the same (device, action) pair have distinct, stable IDs.
            patterns.append(
                TimePattern(
                    pattern_id=f"TIME#{device_id}#{action}@{usual_time}",
                    household_id=household_id,
                    device=device_id,
                    action=action,
                    usual_time=usual_time,
                    window_minutes=window,
                    occurrences=cluster["occurrences"],
                    confidence=score,
                )
            )

    return patterns
