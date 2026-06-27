"""Context service: orchestrate state + patterns + recent events -> context.

Thin coordination layer the API/Lambda call to produce the final
:class:`ContextObject` that will be sent to Bedrock in a future phase.
"""
from __future__ import annotations

from datetime import datetime

from safety.context_builder import build_context
from safety.models.context import ContextObject
from safety.models.events import Event
from safety.models.safety import PersonProfile
from safety.models.state import HouseholdState
from safety.logic import event_service, pattern_service, profile_service, state_service

# Recent-event tail window (days) for short-term memory in the context.
RECENT_WINDOW_DAYS = 1


def generate_context(household_id: str, *, now: datetime | None = None) -> ContextObject:
    state = state_service.get_state(household_id)
    patterns = pattern_service.get_patterns(household_id)
    recent = event_service.get_recent_events(household_id, RECENT_WINDOW_DAYS)
    profiles = profile_service.get_profiles(household_id)
    return build_context(state, patterns, recent, now=now, profiles=profiles)


def evaluate_context(
    household_id: str,
    *,
    active_devices: list[str],
    people_home: dict[str, bool] | None = None,
    device_on_since: dict[str, str] | None = None,
    now: datetime | None = None,
    profiles: list[PersonProfile] | None = None,
    extra_recent: list[Event] | None = None,
    ignore_stored_events: bool = False,
) -> ContextObject:
    """Evaluate a *user-supplied* what-if state against the learned patterns.

    This is the "set the state + clock, then hit Go" flow: instead of reading
    the persisted (and possibly stale) household snapshot, the caller passes the
    exact current state — which devices are ON and (optionally) who is home — and
    we compare it against the patterns mined from history to surface anomalies.

    The state is **ephemeral**: nothing is written back to the events table or
    the state table, so repeated evaluations never pollute the demo data.

    Ephemeral cast & signals (powers the live "dollhouse" dashboard):

    * ``profiles`` — when supplied, the vulnerability lens is driven entirely by
      this in-memory cast (who is placed in the home right now) instead of the
      persisted profile table. This lets the UI add/remove people live and watch
      every concern re-escalate, with nothing written to DynamoDB.
    * ``extra_recent`` — synthetic momentary signals (an SOS press, a wearable
      ALERT, a "last seen" ping) appended to the recent-event tail so the
      event-reading detectors (health / SOS / global-inactivity) can fire
      without persisting anything.
    * ``ignore_stored_events`` — drop the stored event tail entirely and judge
      only against ``extra_recent``. Used for a clean "quiet house" inactivity
      demo where seeded routine events would otherwise count as signs of life.
    """
    patterns = pattern_service.get_patterns(household_id)
    state = HouseholdState(
        household_id=household_id,
        active_devices=list(active_devices),
        people_home=people_home or {},
        device_on_since=device_on_since or {},
    )
    # An explicit cast (even an empty list) overrides the persisted profiles so
    # the UI fully owns "who is home"; ``None`` falls back to the stored table.
    if profiles is not None:
        prof = {p.person_id: p for p in profiles}
    else:
        prof = profile_service.get_profiles(household_id)

    # Recent events feed the detectors that read history (global-inactivity,
    # health, SOS, missed-routine). The painted active_devices remain the source
    # of truth for "what is on right now".
    recent = (
        [] if ignore_stored_events
        else event_service.get_recent_events(household_id, RECENT_WINDOW_DAYS)
    )
    if extra_recent:
        recent = list(recent) + list(extra_recent)
    return build_context(state, patterns, recent, now=now, profiles=prof)
