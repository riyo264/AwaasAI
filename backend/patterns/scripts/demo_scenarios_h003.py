"""Interactive proof of ALL 12 Indian-context features (household H003).

Runs entirely in-memory (moto) — no AWS, no Docker, no DynamoDB needed. It:
  1. Loads 30 days of H003 history and extracts patterns (the "learning" phase).
  2. Replays a DIFFERENT "current state" + clock for EACH of the 12 features and
     prints the resulting Context Object, so you can verify the right detector
     fires with the right context_type for every scenario.

Feature → detector shown:
   1  Water motor / tank         → DURATION_EXCEEDED   (duration_anomaly)
   2  Elderly parent care        → INACTIVITY          (care_alert)
   3  Morning geyser             → DURATION_EXCEEDED   (duration_anomaly)
   4  Morning pooja              → MISSED_ROUTINE      (routine_suggestion)
   5  Dining light / dinner      → DEVICE_LEFT_ON      (departure_anomaly)
   6  Medicine adherence         → MISSED_MEDICINE     (care_alert)
   7  Power-cut / inverter       → DURATION_EXCEEDED   (duration_anomaly)
   8  Rain / clothesline         → DEVICE_LEFT_ON      (departure_anomaly)
   9  Gas-stove monitoring       → DURATION_EXCEEDED   (duration_anomaly)
  10  Evening chai routine       → MISSED_ROUTINE      (routine_suggestion)
  11  Evening TV / hall          → DEVICE_LEFT_ON      (departure_anomaly)
  12  Household chore (water can)→ MISSED_ROUTINE      (routine_suggestion)
  +   NORMAL                     → no anomalies        (normal)

Usage:
    python patterns/scripts/demo_scenarios_h003.py
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from moto import mock_aws


def _print_context(title: str, ctx) -> None:
    print("\n" + "=" * 74)
    print(f"  {title}")
    print("=" * 74)
    data = ctx.model_dump(mode="json")
    print(f"context_type   : {data['context_type']}")
    print(f"current_time   : {data['current_time']}")
    print(f"active_devices : {data['active_devices']}")
    print("anomalies      :")
    if not data["anomalies"]:
        print("    (none)")
    for a in data["anomalies"]:
        print(f"    - [{a['severity']}] {a['type']}: {a.get('detail')}")


def main() -> None:
    mock = mock_aws()
    mock.start()
    try:
        from patterns.dynamodb import client as dynamo_client

        dynamo_client.get_dynamodb_resource.cache_clear()
        from patterns.dynamodb.tables import create_tables

        create_tables()

        from patterns.context_builder import build_context
        from patterns.context_builder.anomaly import ROUTINE_ACTIVATIONS
        from patterns.models.events import DeviceAction, DeviceType, Event
        from patterns.models.patterns import DurationPattern, SequencePattern, TimePattern
        from patterns.models.state import HouseholdState
        from patterns.logic import event_service, pattern_service
        from patterns.tests.sample_data_h003 import HOUSEHOLD, generate

        # --- LEARNING PHASE: 30 days of history -> patterns ---
        event_service.store_events(
            generate(
                days=30,
                include_geyser_anomaly=False,
                include_motor_anomaly=False,
                include_left_on=False,
            )
        )
        patterns = pattern_service.extract_and_store(HOUSEHOLD)
        print(f"Learned {len(patterns)} patterns from 30 days of H003 events:")
        for p in sorted(patterns, key=lambda x: x.pattern_id):
            if isinstance(p, TimePattern):
                extra = f"{p.device} {p.action} ~{p.usual_time}"
            elif isinstance(p, DurationPattern):
                extra = f"{p.device} ~{p.usual_duration_minutes:.0f} min, start ~{p.usual_start_time}"
            elif isinstance(p, SequencePattern):
                extra = " -> ".join(p.steps)
            else:
                extra = ""
            print(f"  - [{p.pattern_type.value:9}] {p.pattern_id:32} conf={p.confidence}  {extra}")

        def satisfied(now: datetime, skip: str | None = None) -> list[Event]:
            """Synthesise today's activation events for every learned routine
            EXCEPT ``skip`` so only the skipped one reads as 'missed' and nothing
            else is mislabelled."""
            out: list[Event] = []
            for p in patterns:
                if not isinstance(p, TimePattern) or p.action not in ROUTINE_ACTIVATIONS:
                    continue
                if p.device == skip:
                    continue
                h, m = map(int, p.usual_time.split(":"))
                out.append(
                    Event(
                        household_id=HOUSEHOLD, device_id=p.device,
                        device_type=DeviceType.OTHER, room="x",
                        action=DeviceAction(p.action), triggered_by="x",
                        timestamp=now.replace(hour=h, minute=m, second=0, microsecond=0),
                    )
                )
            return out

        def state(active=None, since=None, people=None) -> HouseholdState:
            return HouseholdState(
                household_id=HOUSEHOLD,
                active_devices=active or [],
                device_on_since=since or {},
                people_home=people or {},
            )

        base = datetime.now(timezone.utc)

        # 1) WATER MOTOR / TANK — running 40 min vs usual ~15 (tank may be full).
        now = base.replace(hour=10, minute=10)
        motor_on = (now - timedelta(minutes=40)).isoformat()
        _print_context(
            "1) WATER MOTOR — running 40 min vs ~15 (overhead tank may be full)",
            build_context(state(active=["water_motor"], since={"water_motor": motor_on}),
                          patterns, satisfied(now), now=now),
        )

        # 2) ELDERLY CARE — grandpa's morning activity missing.
        now = base.replace(hour=10, minute=0)
        _print_context(
            "2) ELDERLY CARE — Grandpa's usual morning activity not seen",
            build_context(state(people={"grandpa": True}), patterns,
                          satisfied(now, skip="grandpa_activity"), now=now),
        )

        # 3) MORNING GEYSER — running ~70 min vs usual ~20 (left on / power waste).
        now = base.replace(hour=7, minute=10)
        geyser_on = (now - timedelta(minutes=70)).isoformat()
        _print_context(
            "3) MORNING GEYSER — running ~70 min vs usual ~20 (left on)",
            build_context(state(active=["bath_geyser"], since={"bath_geyser": geyser_on}),
                          patterns, satisfied(now), now=now),
        )

        # 4) MORNING POOJA — pooja routine hasn't started ("time for pooja").
        now = base.replace(hour=9, minute=0)
        _print_context(
            "4) MORNING POOJA — the pooja routine hasn't begun yet today",
            build_context(state(people={"mother": True}), patterns,
                          satisfied(now, skip="pooja_lamp"), now=now),
        )

        # 5) DINING LIGHT — still on well past the usual ~22:00 bedtime OFF.
        now = base.replace(hour=23, minute=30)
        line_since = now.replace(hour=20, minute=0).isoformat()
        _print_context(
            "5) DINING LIGHT — still on well past the usual 22:00 bedtime OFF",
            build_context(state(active=["dining_light"],
                                since={"dining_light": line_since}),
                          patterns, satisfied(now), now=now),
        )

        # 6) MEDICINE — grandma's evening dose not confirmed.
        now = base.replace(hour=22, minute=45)
        _print_context(
            "6) MEDICINE — Grandma's evening medicine not confirmed",
            build_context(state(people={"grandma": True}), patterns,
                          satisfied(now, skip="grandma_medicine"), now=now),
        )

        # 7) POWER-CUT / INVERTER — running ~3 h vs usual ~45 min (battery low).
        now = base.replace(hour=23, minute=0)
        inv_on = now.replace(hour=20, minute=0).isoformat()
        _print_context(
            "7) INVERTER — running ~3 h vs usual ~45 min (battery draining)",
            build_context(state(active=["inverter"], since={"inverter": inv_on}),
                          patterns, satisfied(now), now=now),
        )

        # 8) RAIN / CLOTHESLINE — clothes still out past the usual ~17:30 bring-in.
        now = base.replace(hour=19, minute=30)
        line_since = now.replace(hour=8, minute=0).isoformat()
        _print_context(
            "8) CLOTHESLINE — clothes still out well past the usual 17:30 bring-in",
            build_context(state(active=["terrace_clothesline"],
                                since={"terrace_clothesline": line_since}),
                          patterns, satisfied(now), now=now),
        )

        # 9) GAS STOVE — left running ~75 min vs usual ~30 (unattended).
        now = base.replace(hour=19, minute=30)
        stove_on = now.replace(hour=18, minute=15).isoformat()
        _print_context(
            "9) GAS STOVE — running ~75 min vs usual ~30 (unattended)",
            build_context(state(active=["kitchen_gas_stove"],
                                since={"kitchen_gas_stove": stove_on}),
                          patterns, satisfied(now), now=now),
        )

        # 10) EVENING CHAI — chai routine hasn't started ("time for chai").
        now = base.replace(hour=19, minute=0)
        _print_context(
            "10) EVENING CHAI — the chai routine hasn't started yet today",
            build_context(state(people={"mother": True}), patterns,
                          satisfied(now, skip="chai_kettle"), now=now),
        )

        # 11) EVENING TV — the hall TV is still on well past the usual ~22:05 OFF.
        now = base.replace(hour=23, minute=45)
        tv_since = now.replace(hour=18, minute=45).isoformat()
        _print_context(
            "11) EVENING TV — the hall TV is still on well past the usual 22:05 OFF",
            build_context(state(active=["hall_tv"], since={"hall_tv": tv_since}),
                          patterns, satisfied(now), now=now),
        )

        # 12) HOUSEHOLD CHORE — the drinking-water can wasn't refilled.
        now = base.replace(hour=23, minute=30)
        _print_context(
            "12) HOUSEHOLD CHORE — the drinking-water can refill is still pending",
            build_context(state(people={"father": True, "mother": True}), patterns,
                          satisfied(now, skip="water_can_refill"), now=now),
        )

        # +) NORMAL — everything matches the learned routine.
        now = base.replace(hour=12, minute=0)
        _print_context(
            "+) NORMAL — everything matches the learned routine",
            build_context(state(people={"grandpa": True, "mother": True}), patterns,
                          satisfied(now), now=now),
        )

        print("\n" + "=" * 74)
        print("Done. All 12 Indian-context features demonstrated against learned routines.")
        print("=" * 74)
    finally:
        mock.stop()


if __name__ == "__main__":
    main()
