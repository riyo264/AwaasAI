"""Context service: orchestrate state + patterns + recent events -> context.

Thin coordination layer the API/Lambda call to produce the final
:class:`ContextObject` that will be sent to Bedrock in a future phase.
"""
from __future__ import annotations

from datetime import datetime

from patterns.context_builder import build_context
from patterns.models.context import ContextObject
from patterns.models.state import HouseholdState
from patterns.logic import day_relevance, event_service, pattern_service, state_service

# Recent-event tail window (days) for short-term memory in the context.
RECENT_WINDOW_DAYS = 1


async def generate_context(
    household_id: str,
    *,
    now: datetime | None = None,
    day_override: dict | None = None,
) -> ContextObject:
    state = state_service.get_state(household_id)
    patterns = pattern_service.get_patterns(household_id)
    recent = event_service.get_recent_events(household_id, RECENT_WINDOW_DAYS)
    day = day_relevance.resolve_day(now, day_override)
    patterns, adaptation = await day_relevance.adapt_patterns(household_id, patterns, day)
    return build_context(state, patterns, recent, now=now, day_adaptation=adaptation)


async def evaluate_context(
    household_id: str,
    *,
    active_devices: list[str],
    people_home: dict[str, bool] | None = None,
    device_on_since: dict[str, str] | None = None,
    now: datetime | None = None,
    day_override: dict | None = None,
) -> ContextObject:
    """Evaluate a *user-supplied* what-if state against the learned patterns.

    This is the "set the state + clock, then hit Go" flow: instead of reading
    the persisted (and possibly stale) household snapshot, the caller passes the
    exact current state — which devices are ON and (optionally) who is home — and
    we compare it against the patterns mined from history to surface anomalies.

    The state is **ephemeral**: nothing is written back to the events table or
    the state table, so repeated evaluations never pollute the demo data.

    Recent events are intentionally omitted: the user-provided ``active_devices``
    set is the single source of truth for "what is happening right now", so a
    missed-routine is judged purely against that state, not historical events.
    """
    patterns = pattern_service.get_patterns(household_id)
    day = day_relevance.resolve_day(now, day_override)
    patterns, adaptation = await day_relevance.adapt_patterns(household_id, patterns, day)
    state = HouseholdState(
        household_id=household_id,
        active_devices=list(active_devices),
        people_home=people_home or {},
        device_on_since=device_on_since or {},
    )
    return build_context(state, patterns, [], now=now, day_adaptation=adaptation)
