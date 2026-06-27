"""
Production-grade sequence pattern extraction.

Pipeline
========
1. Sort events chronologically.
2. Build coarse temporal sessions.
3. Refine sessions.
4. Compress duplicate sensor events.
5. Convert sessions to canonical representations.
6. Compute pairwise sequence similarity.
7. Cluster similar sessions.
8. Extract representative routines.
9. Compute confidence.
10. Emit SequencePattern objects.

The algorithm is deterministic and explainable.
"""

from __future__ import annotations

import math
import statistics

from collections import Counter
from collections import defaultdict

from dataclasses import dataclass
from dataclasses import field

from datetime import datetime
from datetime import timedelta

from itertools import combinations

from patterns.app.config import get_settings

from patterns.models.events import Event

from patterns.models.patterns import SequencePattern

from patterns.pattern_engine import confidence as conf


# ============================================================================
# Configuration
# ============================================================================

# Maximum gap allowed while building an initial temporal session.
MAX_GAP_MINUTES = 10

# Maximum duration of one behavioural session.
MAX_SESSION_DURATION = 20

# Ignore sessions shorter than this.
MIN_SEQUENCE_LENGTH = 2

# Prevent very long sessions dominating similarity.
MAX_SEQUENCE_LENGTH = 8

# Consecutive duplicate sensor updates are ignored.
COMPRESS_DUPLICATES = True

# Similarity threshold for graph construction.
SIMILARITY_THRESHOLD = 0.75


# ============================================================================
# Internal Session Representation
# ============================================================================

@dataclass(slots=True)
class _Session:
    """
    Internal behavioural session.

    Sessions never leave this module.
    They simply provide richer metadata during mining.
    """

    start: datetime

    end: datetime

    events: list[Event] = field(default_factory=list)

    devices: set[str] = field(default_factory=set)

    rooms: set[str] = field(default_factory=set)

    triggers: set[str] = field(default_factory=set)


@dataclass(slots=True)
class _Cluster:
    """
    Internal routine cluster.
    """

    sessions: list[_Session] = field(default_factory=list)


# ============================================================================
# Utility Functions
# ============================================================================

def _minutes_of_day(ts: datetime) -> int:
    """
    Minutes since midnight.
    """

    return ts.hour * 60 + ts.minute


def _fmt_hhmm(minutes: float) -> str:
    """
    Convert minutes-of-day into HH:MM.
    """

    minutes = int(round(minutes)) % (24 * 60)

    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _time_gap_minutes(a: datetime, b: datetime) -> float:
    """
    Difference between two timestamps in minutes.
    """

    return abs((a - b).total_seconds()) / 60.0


# ============================================================================
# Session Helpers
# ============================================================================

def _new_session(event: Event) -> _Session:
    """
    Create a new behavioural session.
    """

    return _Session(
        start=event.timestamp,
        end=event.timestamp,
        events=[event],
        devices={event.device_id},
        rooms={event.room},
        triggers={event.triggered_by},
    )


def _append_event(session: _Session, event: Event) -> None:
    """
    Add an event into an existing session.
    """

    session.events.append(event)

    session.end = event.timestamp

    session.devices.add(event.device_id)

    session.rooms.add(event.room)

    session.triggers.add(event.triggered_by)


# ============================================================================
# Duplicate Compression
# ============================================================================

def _compress_duplicates(events: list[Event]) -> list[Event]:
    """
    Remove consecutive duplicate sensor events.

    Example

    Fan OFF
    Fan OFF
    Fan OFF

    becomes

    Fan OFF
    """

    if not COMPRESS_DUPLICATES:

        return events

    if not events:

        return events

    compressed = [events[0]]

    for event in events[1:]:

        previous = compressed[-1]

        if (
            previous.device_id == event.device_id
            and previous.action == event.action
        ):
            continue

        compressed.append(event)

    return compressed


# ============================================================================
# Canonical Representation
# ============================================================================

# def _canonical(session: _Session) -> tuple[str, ...]:
#     """
#     Convert one session into its canonical sequence.

#     Duplicate events have already been removed.
#     """

#     steps = []

#     for event in _compress_duplicates(session.events):

#         steps.append(
#             f"{event.device_id}:{event.action.value}"
#         )

#     return tuple(steps[:MAX_SEQUENCE_LENGTH])


# ============================================================================
# Session Statistics
# ============================================================================

def _session_start(session: _Session) -> int:

    return _minutes_of_day(session.start)


def _session_duration(session: _Session) -> float:

    return (
        session.end - session.start
    ).total_seconds() / 60.0
    
    
# ============================================================================
# Coarse Temporal Sessionization
# ============================================================================

def _coarse_sessionize(events: list[Event]) -> list[_Session]:
    """
    Build coarse behavioural sessions using only temporal proximity.

    This stage intentionally over-groups events.
    Refinement happens later.
    """

    if not events:
        return []

    ordered = sorted(events, key=lambda e: e.timestamp)

    sessions: list[_Session] = []

    current = _new_session(ordered[0])

    for event in ordered[1:]:

        gap = (
            event.timestamp - current.end
        ).total_seconds() / 60.0

        duration = (
            event.timestamp - current.start
        ).total_seconds() / 60.0

        if (
            gap <= MAX_GAP_MINUTES
            and
            duration <= MAX_SESSION_DURATION
        ):
            _append_event(current, event)

        else:
            sessions.append(current)
            current = _new_session(event)

    sessions.append(current)

    return sessions


# ============================================================================
# Device Continuity
# ============================================================================

def _device_continuation(
    previous: Event,
    current: Event,
) -> bool:
    """
    Returns True if the current event is a continuation
    of the previous event.

    Example

    water_motor ON

        ↓

    water_motor OFF
    """

    if previous.device_id != current.device_id:
        return False

    # Pairs that represent a single device's open→close lifecycle. These must
    # match the real DeviceAction enum (events.py); the previous ENTER/START
    # /STOP entries never existed in the enum and so never matched anything.
    transitions = {

        ("ON", "OFF"),

        ("OPEN", "CLOSE"),

        ("ARRIVE", "LEAVE"),
    }

    return (
        previous.action.value,
        current.action.value,
    ) in transitions


# ============================================================================
# Session Refinement
# ============================================================================

def _refine_session(
    session: _Session,
) -> list[_Session]:
    """
    Split unrelated activities inside a coarse session.

    Device continuations remain together.
    """

    if len(session.events) <= MIN_SEQUENCE_LENGTH:
        return [session]

    refined: list[_Session] = []

    current = _new_session(session.events[0])

    previous = session.events[0]

    for event in session.events[1:]:

        same_trigger = (
            event.triggered_by in current.triggers
        )

        same_room = (
            event.room in current.rooms
        )

        continuation = _device_continuation(
            previous,
            event,
        )

        if (
            continuation
            or same_trigger
            or same_room
        ):

            _append_event(current, event)

        else:

            refined.append(current)

            current = _new_session(event)

        previous = event

    refined.append(current)

    return refined


# ============================================================================
# Session Merge
# ============================================================================

def _should_merge(
    left: _Session,
    right: _Session,
) -> bool:
    """
    Decide whether two neighbouring sessions
    actually belong to one behavioural routine.
    """

    gap = (
        right.start - left.end
    ).total_seconds() / 60.0

    if gap > MAX_GAP_MINUTES:
        return False

    if left.devices & right.devices:
        return True

    if left.rooms & right.rooms:
        return True

    if left.triggers & right.triggers:
        return True

    return False


def _merge_sessions(
    sessions: list[_Session],
) -> list[_Session]:
    """
    Merge neighbouring sessions created during refinement.
    """

    if not sessions:
        return sessions

    merged = [sessions[0]]

    for session in sessions[1:]:

        previous = merged[-1]

        if _should_merge(previous, session):

            previous.events.extend(session.events)

            previous.end = session.end

            previous.devices.update(session.devices)

            previous.rooms.update(session.rooms)

            previous.triggers.update(session.triggers)

        else:

            merged.append(session)

    return merged


# ============================================================================
# Session Builder
# ============================================================================

def _build_sessions(
    events: list[Event],
) -> list[_Session]:
    """
    Complete behavioural session construction pipeline.

    Pipeline

        Events
            ↓
    Coarse Temporal Sessions
            ↓
    Context Refinement
            ↓
    Session Merge
            ↓
    Behavioural Sessions
    """

    coarse = _coarse_sessionize(events)

    refined: list[_Session] = []

    for session in coarse:

        refined.extend(
            _refine_session(session)
        )

    refined = _merge_sessions(refined)

    refined = [
        s
        for s in refined
        if len(s.events) >= MIN_SEQUENCE_LENGTH
    ]

    return refined

# ============================================================================
# Canonical Session Representation
# ============================================================================

@dataclass(slots=True)
class _CanonicalSession:
    """
    Immutable representation of a behavioural session.

    All similarity calculations operate on this object rather
    than directly on Event lists.
    """

    session: _Session

    signature: tuple[str, ...]

    start_minute: int

    duration: float

    length: int

    devices: frozenset[str]

    rooms: frozenset[str]

    triggers: frozenset[str]


def _canonical(session: _Session) -> _CanonicalSession:
    """
    Convert a behavioural session into its canonical representation.
    """

    signature = tuple(
        f"{event.device_id}:{event.action.value}"
        for event in _compress_duplicates(session.events)
    )[:MAX_SEQUENCE_LENGTH]

    return _CanonicalSession(
        session=session,
        signature=signature,
        start_minute=_minutes_of_day(session.start),
        duration=_session_duration(session),
        length=len(signature),
        devices=frozenset(session.devices),
        rooms=frozenset(session.rooms),
        triggers=frozenset(session.triggers),
    )


# ============================================================================
# Longest Common Subsequence
# ============================================================================

def _lcs_length(
    a: tuple[str, ...],
    b: tuple[str, ...],
) -> int:
    """
    Dynamic-programming implementation of Longest Common Subsequence.
    """

    rows = len(a) + 1
    cols = len(b) + 1

    dp = [[0] * cols for _ in range(rows)]

    for i in range(1, rows):
        for j in range(1, cols):

            if a[i - 1] == b[j - 1]:

                dp[i][j] = dp[i - 1][j - 1] + 1

            else:

                dp[i][j] = max(
                    dp[i - 1][j],
                    dp[i][j - 1],
                )

    return dp[-1][-1]


# ============================================================================
# Dice-LCS Similarity
# ============================================================================

def _sequence_similarity(
    left: _CanonicalSession,
    right: _CanonicalSession,
) -> float:
    """
    Dice coefficient computed using LCS.

    score = 2 * LCS / (len(A) + len(B))
    """

    if left.length == 0 or right.length == 0:
        return 0.0

    lcs = _lcs_length(
        left.signature,
        right.signature,
    )

    return (
        2.0 * lcs
    ) / (
        left.length + right.length
    )


# ============================================================================
# Time Similarity
# ============================================================================

def _circular_distance(
    a: int,
    b: int,
) -> int:
    """
    Circular distance on a 24-hour clock.

    Correctly handles midnight.

    Example

    23:58

    00:02

    distance = 4 minutes
    """

    diff = abs(a - b)

    return min(diff, 1440 - diff)


def _time_similarity(
    left: _CanonicalSession,
    right: _CanonicalSession,
) -> float:

    distance = _circular_distance(
        left.start_minute,
        right.start_minute,
    )

    return max(
        0.0,
        1.0 - distance / 180.0,
    )


# ============================================================================
# Length Similarity
# ============================================================================

def _length_similarity(
    left: _CanonicalSession,
    right: _CanonicalSession,
) -> float:

    return min(
        left.length,
        right.length,
    ) / max(
        left.length,
        right.length,
    )


# ============================================================================
# Context Similarity
# ============================================================================

def _jaccard(
    a: frozenset[str],
    b: frozenset[str],
) -> float:

    if not a and not b:
        return 1.0

    return len(a & b) / len(a | b)


def _context_similarity(
    left: _CanonicalSession,
    right: _CanonicalSession,
) -> float:
    """
    Similarity of contextual metadata.
    """

    room = _jaccard(
        left.rooms,
        right.rooms,
    )

    trigger = _jaccard(
        left.triggers,
        right.triggers,
    )

    device = _jaccard(
        left.devices,
        right.devices,
    )

    return (
        room +
        trigger +
        device
    ) / 3.0


# ============================================================================
# Overall Similarity
# ============================================================================

def _overall_similarity(
    left: _CanonicalSession,
    right: _CanonicalSession,
) -> float:
    """
    Final similarity score.

    The weights sum to 1.
    """

    sequence = _sequence_similarity(
        left,
        right,
    )

    time = _time_similarity(
        left,
        right,
    )

    length = _length_similarity(
        left,
        right,
    )

    context = _context_similarity(
        left,
        right,
    )

    return (
        0.50 * sequence +
        0.20 * context +
        0.20 * time +
        0.10 * length
    )


# ============================================================================
# Canonical Builder
# ============================================================================

def _canonicalize(
    sessions: list[_Session],
) -> list[_CanonicalSession]:
    """
    Convert every behavioural session into its canonical form.
    """

    return [
        _canonical(session)
        for session in sessions
    ]
    
    
# ============================================================================
# Candidate Index
# ============================================================================

def _hour_bucket(
    session: _CanonicalSession,
) -> int:
    """
    Group sessions into 2-hour windows.

    Example

    08:15 -> bucket 4
    09:40 -> bucket 4
    """

    return session.start_minute // 120


def _length_bucket(
    session: _CanonicalSession,
) -> int:
    """
    Bucket sequence lengths.

    Prevents very short and very long sessions
    from being compared unnecessarily.
    """

    return session.length


def _trigger_bucket(
    session: _CanonicalSession,
) -> str:
    """
    Primary trigger bucket.

    If multiple triggers exist,
    choose one deterministically.
    """

    if not session.triggers:
        return "__NONE__"

    return sorted(session.triggers)[0]


# ============================================================================
# Candidate Generation
# ============================================================================

def _candidate_pairs(
    sessions: list[_CanonicalSession],
):
    """
    Produce only plausible session pairs.

    Two sessions become candidates if they
    share at least one indexing bucket.
    """

    hour_index = defaultdict(set)

    length_index = defaultdict(set)

    trigger_index = defaultdict(set)

    for idx, session in enumerate(sessions):

        hour_index[
            _hour_bucket(session)
        ].add(idx)

        length_index[
            _length_bucket(session)
        ].add(idx)

        trigger_index[
            _trigger_bucket(session)
        ].add(idx)

    pairs = set()

    for index in (
        hour_index,
        length_index,
        trigger_index,
    ):

        for bucket in index.values():

            bucket = sorted(bucket)

            for i in range(len(bucket)):

                for j in range(i + 1, len(bucket)):

                    pairs.add(
                        (
                            bucket[i],
                            bucket[j],
                        )
                    )

    return sorted(pairs)


# ============================================================================
# Similarity Matrix
# ============================================================================

def _similarity_matrix(
    sessions: list[_CanonicalSession],
):
    """
    Compute similarities only for
    candidate pairs.
    """

    similarities = {}

    for left_idx, right_idx in _candidate_pairs(
        sessions
    ):

        left = sessions[left_idx]

        right = sessions[right_idx]

        score = _overall_similarity(
            left,
            right,
        )

        if score >= SIMILARITY_THRESHOLD:

            similarities[
                (
                    left_idx,
                    right_idx,
                )
            ] = score

    return similarities


# ============================================================================
# Similarity Graph
# ============================================================================

@dataclass(slots=True)
class _Edge:
    """
    One similarity edge.
    """

    left: int

    right: int

    score: float


def _build_edges(
    sessions: list[_CanonicalSession],
) -> list[_Edge]:
    """
    Compute similarity edges.

    Only sufficiently similar pairs become graph edges.
    """

    edges: list[_Edge] = []

    similarities = _similarity_matrix(
        sessions
    )

    for (left, right), score in similarities.items():

        edges.append(

            _Edge(

                left=left,

                right=right,

                score=score,

            )

        )

    return edges


# ============================================================================
# Graph Construction
# ============================================================================

def _build_graph(
    edges: list[_Edge],
):
    """
    Build an undirected graph from similarity edges.
    """

    graph = defaultdict(set)

    for edge in edges:

        graph[edge.left].add(edge.right)

        graph[edge.right].add(edge.left)

    return graph


# ============================================================================
# Connected Components
# ============================================================================

def _connected_components(
    graph,
    total_nodes,
):
    """
    Discover routine clusters using DFS.
    """

    visited = set()

    components = []

    for start in range(total_nodes):

        if start in visited:
            continue

        stack = [start]

        component = []

        while stack:

            node = stack.pop()

            if node in visited:
                continue

            visited.add(node)

            component.append(node)

            stack.extend(
                graph[node] - visited
            )

        components.append(component)

    return components


# ============================================================================
# Cluster Cohesion
# ============================================================================

def _cluster_cohesion(
    component: list[int],
    edges: list[_Edge],
) -> float:
    """
    Average internal similarity of one cluster.
    """

    if len(component) <= 1:

        return 1.0

    lookup = {}

    for edge in edges:

        lookup[(edge.left, edge.right)] = edge.score

        lookup[(edge.right, edge.left)] = edge.score

    scores = []

    for left, right in combinations(component, 2):

        scores.append(

            lookup.get(

                (left, right),

                0.0,

            )

        )

    if not scores:

        return 0.0

    return statistics.mean(scores)


# ============================================================================
# Cohesion-Aware Cluster Splitting
# ============================================================================

MIN_CLUSTER_COHESION = 0.70


def _score_lookup(edges: list[_Edge]) -> dict[tuple[int, int], float]:
    """Symmetric (left, right) -> score map for O(1) similarity lookups."""

    lookup: dict[tuple[int, int], float] = {}

    for edge in edges:

        lookup[(edge.left, edge.right)] = edge.score
        lookup[(edge.right, edge.left)] = edge.score

    return lookup


def _split_component(
    nodes: list[int],
    lookup: dict[tuple[int, int], float],
) -> list[list[int]]:
    """
    Break one *low-cohesion* connected component into dense sub-clusters.

    Single-linkage connected components chain transitively: A~B and B~C put
    A, B, C together even when A and C are dissimilar. The old behaviour
    averaged that whole component and, finding it below the cohesion bar,
    dropped it — losing the genuinely similar A~B and B~C pairs entirely.

    Instead we grow clusters greedily: seed on the strongest remaining edge,
    then repeatedly add the node that keeps the cluster's *average pairwise
    cohesion* highest while staying at or above ``MIN_CLUSTER_COHESION``. Every
    emitted multi-node cluster therefore provably meets the cohesion bar, and
    nodes that fit no dense core fall out as singletons (dropped later by the
    support threshold). Deterministic: ties break on lowest index.
    """

    remaining = set(nodes)

    clusters: list[list[int]] = []

    while remaining:

        ordered = sorted(remaining)

        # Strongest edge fully inside the remaining node set seeds a cluster.
        seed = None
        for i, a in enumerate(ordered):
            for b in ordered[i + 1:]:
                score = lookup.get((a, b))
                if score is None:
                    continue
                if seed is None or score > seed[0]:
                    seed = (score, a, b)

        if seed is None:
            # No edges left among the remaining nodes → all singletons.
            clusters.extend([n] for n in ordered)
            break

        cluster = [seed[1], seed[2]]
        cluster_set = {seed[1], seed[2]}
        pair_sum = seed[0]
        pair_cnt = 1

        while True:
            best_add = None  # (cohesion, node, add_sum)
            for n in sorted(remaining - cluster_set):
                add_sum = sum(lookup.get((n, c), 0.0) for c in cluster)
                cohesion = (pair_sum + add_sum) / (pair_cnt + len(cluster))
                if cohesion >= MIN_CLUSTER_COHESION:
                    if best_add is None or cohesion > best_add[0]:
                        best_add = (cohesion, n, add_sum)
            if best_add is None:
                break
            _, node, add_sum = best_add
            pair_sum += add_sum
            pair_cnt += len(cluster)
            cluster.append(node)
            cluster_set.add(node)

        clusters.append(sorted(cluster_set))
        remaining -= cluster_set

    return clusters


def _cohesive_clusters(
    components: list[list[int]],
    edges: list[_Edge],
) -> list[list[int]]:
    """
    Turn raw connected components into cohesive behavioural clusters.

    A component that already meets ``MIN_CLUSTER_COHESION`` is kept whole —
    identical to the previous behaviour for valid clusters. A component below
    the bar is *split* into its dense cores rather than discarded, so a
    transitively-chained group no longer takes its genuinely-similar pairs
    down with it.
    """

    lookup = _score_lookup(edges)

    clusters: list[list[int]] = []

    for component in components:

        if _cluster_cohesion(component, edges) >= MIN_CLUSTER_COHESION:

            clusters.append(component)

        else:

            clusters.extend(_split_component(component, lookup))

    return clusters


# ============================================================================
# Complete Graph Clustering
# ============================================================================

def _cluster_sessions(
    sessions: list[_CanonicalSession],
):
    """
    Complete clustering pipeline.

    Canonical Sessions
            ↓
    Similarity Matrix
            ↓
    Similarity Graph
            ↓
    Connected Components
            ↓
    Cohesion-Aware Splitting
            ↓
    Routine Clusters
    """

    edges = _build_edges(
        sessions
    )

    graph = _build_graph(
        edges
    )

    components = _connected_components(

        graph,

        len(sessions),

    )

    clusters = _cohesive_clusters(

        components,

        edges,

    )

    return clusters, edges

# ============================================================================
# Representative Pattern Extraction
# ============================================================================

MIN_STEP_SUPPORT = 0.60


def _representative_sequence(
    cluster: list[int],
    sessions: list[_CanonicalSession],
) -> list[str]:
    """
    Compute the representative behavioural routine
    for one routine cluster.
    """

    total_sessions = len(cluster)

    occurrences = defaultdict(list)

    for session_index in cluster:

        signature = sessions[
            session_index
        ].signature

        for position, step in enumerate(signature):

            occurrences[step].append(position)

    representative = []

    for step, positions in occurrences.items():

        support = (
            len(positions)
            / total_sessions
        )

        if support < MIN_STEP_SUPPORT:

            continue

        representative.append(

            (
                statistics.mean(positions),

                step,
            )

        )

    representative.sort()

    return [

        step

        for _, step in representative

    ]
    
# ============================================================================
# Circular Time Statistics
# ============================================================================

def _circular_mean(
    minutes: list[int],
) -> float:
    """
    Mean time-of-day.

    Correctly handles midnight.
    """

    angles = [

        2 * math.pi * m / 1440

        for m in minutes

    ]

    x = statistics.mean(
        math.cos(a)
        for a in angles
    )

    y = statistics.mean(
        math.sin(a)
        for a in angles
    )

    angle = math.atan2(
        y,
        x,
    )

    if angle < 0:

        angle += 2 * math.pi

    return (
        angle * 1440
    ) / (
        2 * math.pi
    )


def _circular_std(
    minutes,
):
    """
    Circular standard deviation.
    """

    angles = [

        2 * math.pi * m / 1440

        for m in minutes

    ]

    x = statistics.mean(
        math.cos(a)
        for a in angles
    )

    y = statistics.mean(
        math.sin(a)
        for a in angles
    )

    r = math.sqrt(
        x * x +
        y * y
    )

    if r == 0:

        return 720

    return math.sqrt(
        -2 * math.log(r)
    ) * (
        1440
        /
        (2 * math.pi)
    )
    
# ============================================================================
# Pattern Statistics
# ============================================================================

def _cluster_statistics(
    cluster: list[int],
    sessions: list[_CanonicalSession],
    edges: list[_Edge],
):
    """
    Compute all statistics required for pattern generation.
    """

    # --------------------------------------------------
    # Support
    # --------------------------------------------------

    support = len(cluster)

    # --------------------------------------------------
    # Typical Time
    # --------------------------------------------------

    start_times = [

        sessions[idx].start_minute

        for idx in cluster

    ]

    mean_time = _circular_mean(
        start_times
    )

    std_time = _circular_std(
        start_times
    )

    # --------------------------------------------------
    # Cohesion
    # --------------------------------------------------

    cohesion = _cluster_cohesion(
        cluster,
        edges,
    )

    # --------------------------------------------------
    # Representative Routine
    # --------------------------------------------------

    steps = _representative_sequence(
        cluster,
        sessions,
    )

    # --------------------------------------------------
    # Completeness
    # --------------------------------------------------

    lengths = [

        sessions[idx].length

        for idx in cluster

    ]

    completeness = (
        statistics.mean(lengths)
        /
        max(lengths)
    )

    return {

        "support": support,

        "usual_time": mean_time,

        "stddev": std_time,

        "cohesion": cohesion,

        "completeness": completeness,

        "steps": steps,

    }


# ============================================================================
# Pattern Confidence
# ============================================================================

def _pattern_confidence(
    stats,
    settings,
):
    """
    Compute the final confidence score.
    """

    support = conf.support_score(

        stats["support"],

        settings.analysis_window_days,

    )

    consistency = conf.consistency_score(

        stats["stddev"],

        tolerance=settings.time_bucket_minutes,

    )

    confidence = (

        0.35 * support +

        0.30 * consistency +

        0.20 * stats["cohesion"] +

        0.15 * stats["completeness"]

    )

    return min(
        confidence,
        1.0,
    )


# ============================================================================
# Human-readable Description
# ============================================================================

def _describe_sequence(
    steps: list[str],
) -> str:
    """
    Generate a readable routine description.
    """

    joined = " -> ".join(
        steps
    )

    has_leave = any(
        step.endswith(":LEAVE")
        for step in steps
    )

    all_off = all(
        step.endswith(":OFF")
        for step in steps[1:]
    )

    if has_leave and all_off:

        return (
            "Departure routine: "
            "home secured / devices switched off"
        )

    return joined


# ============================================================================
# Pattern Generation
# ============================================================================

def _generate_patterns(
    household_id: str,
    clusters: list[list[int]],
    sessions: list[_CanonicalSession],
    edges: list[_Edge],
    settings,
) -> list[SequencePattern]:
    """
    Convert routine clusters into SequencePattern objects.
    """

    patterns = []

    pattern_id = 1

    for cluster in clusters:
        
        if(len(cluster)<settings.min_pattern_occurrences):
            continue

        stats = _cluster_statistics(

            cluster,

            sessions,

            edges,

        )

        # Guard: if no step cleared MIN_STEP_SUPPORT the representative routine
        # is empty — emitting it would produce a meaningless pattern with no
        # steps and a blank description, so skip the cluster entirely.
        if not stats["steps"]:
            continue

        confidence = _pattern_confidence(

            stats,

            settings,

        )

        if confidence < settings.min_confidence:

            continue

        patterns.append(

            SequencePattern(

                pattern_id=f"SEQ#{pattern_id:03d}",

                household_id=household_id,

                description=_describe_sequence(

                    stats["steps"]

                ),

                steps=stats["steps"],

                usual_time=_fmt_hhmm(

                    stats["usual_time"]

                ),

                occurrences=stats["support"],

                confidence=confidence,

            )

        )

        pattern_id += 1

    return patterns


# ============================================================================
# Public API
# ============================================================================

def extract_sequence_patterns(
    household_id: str,
    events: list[Event],
) -> list[SequencePattern]:
    """
    Production sequence mining pipeline.
    """

    settings = get_settings()

    # Stage 1
    behavioural_sessions = _build_sessions(
        events
    )

    # Stage 2
    canonical_sessions = _canonicalize(
        behavioural_sessions
    )

    # # Stage 3
    # edges = _build_edges(
    #     canonical_sessions
    # )

    # # Stage 4
    # graph = _build_graph(
    #     edges
    # )

    # components = _connected_components(
    #     graph,
    #     len(canonical_sessions),
    # )

    # clusters = _valid_clusters(
    #     components,
    #     edges,
    # )
    
     # Stage 3 + 4 — use the helper instead of repeating the steps
    clusters, edges = _cluster_sessions(canonical_sessions)

    # Stage 5
    return _generate_patterns(

        household_id,

        clusters,

        canonical_sessions,

        edges,

        settings,

    )