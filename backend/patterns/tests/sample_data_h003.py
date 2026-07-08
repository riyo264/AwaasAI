"""Third synthetic scenario (household H003) — full Indian-context intelligence.

This household exercises the Indian-context features on the brief, each modelled
as a deterministic, learnable **event stream** the existing extractors already
understand — NO new algorithm is required. Ordinary appliances (fans, lights,
TV, geyser, doors) are mixed in so the engine learns the whole home together.

Everything here is an ACTUATOR/APPLIANCE event (a switch flipping, a smart plug
toggling, a pill box confirming) — i.e. things a real smart home can log without
a special sensor. We deliberately avoid "who walked in" presence guesses (a maid
arriving, a delivery showing up, a child returning) that a home cannot actually
observe; the appliances below stand in for those routines far more defensibly.

╔══════════════════════════════════════════════════════════════════════════════
║  FEATURE → EVENT MODEL → LEARNED PATTERN → ANOMALY IT ENABLES
╠══════════════════════════════════════════════════════════════════════════════
║  1. Water motor / overhead tank
║       water_motor · MOTOR · ON→OFF ~15 min, ~09:30   → DurationPattern
║       → DURATION_EXCEEDED when run > 2× usual ("tank may already be full").
║  2. Elderly parent care
║       grandpa_activity · ACTIVITY · ACTIVE ~06:45     → TimePattern(ACTIVE)
║       → INACTIVITY when the morning activity ping is absent.
║  3. Morning geyser / water heater
║       bath_geyser · plug ON→OFF ~20 min, ~06:00       → DurationPattern
║       → DURATION_EXCEEDED when left running (power waste / scald risk). Paired
║       with bath_light as a short "morning bath" SequencePattern.
║  4. Morning pooja
║       pooja_lamp:ON → temple_bell:ON → bhajan_speaker:ON ~07:00
║                                                       → SequencePattern (+ a
║       pooja_lamp ON TimePattern) → MISSED_ROUTINE reminder if pooja not begun.
║  5. Dining light / dinner
║       dining_light · LIGHT · OFF ~22:00 (consistent bedtime-off; the ON time
║       varies with when dinner starts)                 → TimePattern(OFF)
║       → DEVICE_LEFT_ON when the dining light is still on well past bedtime.
║  6. Elderly medicine adherence
║       grandma_medicine · MEDICINE · TAKEN ~21:00      → TimePattern(TAKEN)
║       → MISSED_MEDICINE when the dose isn't confirmed.
║  7. Power-cut / inverter
║       inverter · OTHER · ON→OFF ~45 min, ~20:00       → DurationPattern
║       → DURATION_EXCEEDED when it runs far longer ("inverter battery is low").
║  8. Rain / clothesline
║       terrace_clothesline · OTHER · OFF ~17:30 (clothes brought in daily)
║                                                       → TimePattern(OFF)
║       → DEVICE_LEFT_ON when clothes are still out well past the usual time.
║  9. Gas-stove monitoring
║       kitchen_gas_stove · OTHER · ON→OFF ~30 min, ~18:30 → DurationPattern
║       → DURATION_EXCEEDED when the stove is left running (unattended).
║ 10. Evening chai routine
║       chai_kettle:ON → kitchen_light:ON ~17:00        → SequencePattern (+ a
║       chai_kettle ON TimePattern) → MISSED_ROUTINE reminder ("time for chai").
║ 11. Evening TV / hall
║       hall_tv · TV · ON ~18:45, OFF ~22:05; hall_light ~18:05→22:20
║                                                       → Time/DurationPattern
║       → DEVICE_LEFT_ON / DURATION_EXCEEDED when the TV is left on late.
║ 12. Household chore coordination (drinking-water can refill)
║       water_can_refill · OTHER · ON→OFF (momentary) ~21:35 → TimePattern(ON)
║       → MISSED_ROUTINE when today's chore hasn't been done (assign to whoever
║         is home via ``people_home`` at the orchestrator).
║
║  Plus ordinary appliances so the home is realistic:
║       son departure  : main_door:OPEN → son_room_fan:OFF → son_room_light:OFF
║       porch security : porch_light ON ~19:20, OFF ~22:30
╚══════════════════════════════════════════════════════════════════════════════

Times are spaced > MAX_GAP_MINUTES (10) apart except inside the intended
sequences (morning bath, pooja, chai, son departure) so unrelated events never
merge into a spurious, repeating session signature.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from patterns.models.events import DeviceAction, DeviceType, EventCreate

HOUSEHOLD = "H003"
_rng = random.Random(13)  # deterministic, independent of H001/H002 RNGs


def _at(day: datetime, hour: int, minute: int, jitter: int = 0) -> datetime:
    minute += _rng.randint(-jitter, jitter) if jitter else 0
    base = day.replace(hour=hour, minute=0, second=0, microsecond=0)
    return base + timedelta(minutes=minute)


def generate(
    days: int = 30,
    *,
    include_geyser_anomaly: bool = True,
    include_motor_anomaly: bool = True,
    include_left_on: bool = True,
) -> list[EventCreate]:
    events: list[EventCreate] = []
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    def add(device_id, device_type, room, action, ts, triggered_by="system"):
        events.append(
            EventCreate(
                household_id=HOUSEHOLD,
                device_id=device_id,
                device_type=device_type,
                room=room,
                action=action,
                triggered_by=triggered_by,
                timestamp=ts,
            )
        )

    for d in range(days, 0, -1):
        day = today - timedelta(days=d)

        # 3) Morning geyser ~06:00 (~20 min heat-up) + bath light. The geyser ON
        #    and bath light ON fire within a minute → a short "morning bath"
        #    SequencePattern; the geyser ON→OFF gives a DurationPattern.
        b_on = _at(day, 6, 0, jitter=5)
        add("bath_geyser", DeviceType.OTHER, "bath", DeviceAction.ON, b_on,
            triggered_by="father")
        add("bath_light", DeviceType.LIGHT, "bath", DeviceAction.ON,
            b_on + timedelta(minutes=2), triggered_by="father")
        add("bath_geyser", DeviceType.OTHER, "bath", DeviceAction.OFF,
            b_on + timedelta(minutes=20 + _rng.randint(-2, 2)), triggered_by="father")
        add("bath_light", DeviceType.LIGHT, "bath", DeviceAction.OFF,
            b_on + timedelta(minutes=22 + _rng.randint(-2, 2)), triggered_by="father")

        # 2) Elderly morning activity ~06:45 (grandpa moves around / wakes).
        add("grandpa_activity", DeviceType.ACTIVITY, "grandpa_room",
            DeviceAction.ACTIVE, _at(day, 6, 45, jitter=8), triggered_by="grandpa")

        # 4) Morning pooja burst ~07:00 (lamp → bell → bhajan within minutes);
        #    lamp switched off ~07:30 (well after the burst, so it is not part
        #    of the pooja session signature).
        p_on = _at(day, 7, 0, jitter=5)
        add("pooja_lamp", DeviceType.LIGHT, "pooja_room", DeviceAction.ON, p_on,
            triggered_by="mother")
        add("temple_bell", DeviceType.OTHER, "pooja_room", DeviceAction.ON,
            p_on + timedelta(minutes=1), triggered_by="mother")
        add("bhajan_speaker", DeviceType.OTHER, "pooja_room", DeviceAction.ON,
            p_on + timedelta(minutes=2), triggered_by="mother")
        add("pooja_lamp", DeviceType.LIGHT, "pooja_room", DeviceAction.OFF,
            p_on + timedelta(minutes=30 + _rng.randint(-3, 3)), triggered_by="mother")
        # Bell & bhajan are switched off when the pooja ends (~07:30) so they do
        # not linger as 'active' devices for the rest of the day.
        add("temple_bell", DeviceType.OTHER, "pooja_room", DeviceAction.OFF,
            p_on + timedelta(minutes=31 + _rng.randint(-3, 3)), triggered_by="mother")
        add("bhajan_speaker", DeviceType.OTHER, "pooja_room", DeviceAction.OFF,
            p_on + timedelta(minutes=32 + _rng.randint(-3, 3)), triggered_by="mother")

        # (ordinary) Son departure ~08:00 (door + fan + light). Tight, stable
        # spacing keeps the OPEN → fan OFF → light OFF order for the sequence.
        add("main_door", DeviceType.DOOR, "entrance", DeviceAction.OPEN,
            _at(day, 8, 0, jitter=2), triggered_by="son")
        add("son_room_fan", DeviceType.FAN, "son_room", DeviceAction.OFF,
            _at(day, 8, 4, jitter=1), triggered_by="son")
        add("son_room_light", DeviceType.LIGHT, "son_room", DeviceAction.OFF,
            _at(day, 8, 7, jitter=1), triggered_by="son")
        # Door is pulled shut a little after the departure burst (separate
        # session, so the 3-step departure sequence stays intact) so it does not
        # linger 'open' all day.
        add("main_door", DeviceType.DOOR, "entrance", DeviceAction.CLOSE,
            _at(day, 8, 20, jitter=3), triggered_by="son")

        # 1) Overhead-tank water motor ~15 min run ~09:30.
        m_on = _at(day, 9, 30, jitter=8)
        add("water_motor", DeviceType.MOTOR, "utility", DeviceAction.ON, m_on)
        add("water_motor", DeviceType.MOTOR, "utility", DeviceAction.OFF,
            m_on + timedelta(minutes=15 + _rng.randint(-2, 2)))

        # 10) Evening chai routine ~17:00 (kettle → kitchen light). The kettle
        #     also has a short ~5 min duration; kitchen light is switched off
        #     late evening so it does not pair across days.
        c_on = _at(day, 17, 0, jitter=6)
        add("chai_kettle", DeviceType.OTHER, "kitchen", DeviceAction.ON, c_on,
            triggered_by="mother")
        add("kitchen_light", DeviceType.LIGHT, "kitchen", DeviceAction.ON,
            c_on + timedelta(minutes=2), triggered_by="mother")
        add("chai_kettle", DeviceType.OTHER, "kitchen", DeviceAction.OFF,
            c_on + timedelta(minutes=5 + _rng.randint(-1, 1)), triggered_by="mother")

        # 8) Clothesline: clothes are brought in (OFF) ~17:30 every day. Tracking
        #    only the bring-in gives a TimePattern(OFF) with NO duration pattern,
        #    so "clothes still out past 17:30" surfaces as DEVICE_LEFT_ON.
        add("terrace_clothesline", DeviceType.OTHER, "terrace", DeviceAction.OFF,
            _at(day, 17, 30, jitter=6), triggered_by="mother")

        # 11) Evening hall — the family light comes on early evening and the TV
        #     goes on for the evening; both are switched off around bedtime. The
        #     TV's ON time varies a lot with the evening (wide jitter → no stable
        #     duration), but it is always switched off ~22:05 → a clean
        #     TimePattern(OFF) that powers the "TV left on late" DEVICE_LEFT_ON.
        add("hall_light", DeviceType.LIGHT, "hall", DeviceAction.ON,
            _at(day, 18, 5, jitter=6), triggered_by="mother")
        add("hall_tv", DeviceType.TV, "hall", DeviceAction.ON,
            _at(day, 18, 30, jitter=90), triggered_by="son")

        # 9) Gas stove dinner cooking ~18:30, ~30 min → DurationPattern.
        g_on = _at(day, 18, 30, jitter=6)
        add("kitchen_gas_stove", DeviceType.OTHER, "kitchen", DeviceAction.ON, g_on,
            triggered_by="mother")
        add("kitchen_gas_stove", DeviceType.OTHER, "kitchen", DeviceAction.OFF,
            g_on + timedelta(minutes=30 + _rng.randint(-4, 4)), triggered_by="mother")

        # (ordinary) Evening security / porch light ON ~19:20.
        add("porch_light", DeviceType.LIGHT, "porch", DeviceAction.ON,
            _at(day, 19, 20, jitter=5))

        # 5) Dining light for dinner. The ON time varies a lot with when dinner
        #    starts (wide jitter → no stable duration), but it is always switched
        #    off around bedtime → a clean TimePattern(OFF) ~22:00 that powers the
        #    "dining light left on past bedtime" DEVICE_LEFT_ON.
        add("dining_light", DeviceType.LIGHT, "dining", DeviceAction.ON,
            _at(day, 20, 0, jitter=45), triggered_by="mother")

        # 7) Power-cut / inverter: evening outage ~20:00, runs ~45 min →
        #    DurationPattern. Running far longer ⇒ battery draining.
        i_on = _at(day, 20, 0, jitter=6)
        add("inverter", DeviceType.OTHER, "utility", DeviceAction.ON, i_on)
        add("inverter", DeviceType.OTHER, "utility", DeviceAction.OFF,
            i_on + timedelta(minutes=45 + _rng.randint(-5, 5)))

        # 6) Elderly evening medicine ~21:00.
        add("grandma_medicine", DeviceType.MEDICINE, "grandma_room",
            DeviceAction.TAKEN, _at(day, 21, 0, jitter=8), triggered_by="grandma")

        # 12) Household chore — refill the 20 L drinking-water can ~21:35
        #     (momentary ON→OFF so it never lingers as an active device).
        w_on = _at(day, 21, 35, jitter=6)
        add("water_can_refill", DeviceType.OTHER, "kitchen", DeviceAction.ON, w_on,
            triggered_by="mother")
        add("water_can_refill", DeviceType.OTHER, "kitchen", DeviceAction.OFF,
            w_on + timedelta(minutes=1), triggered_by="mother")

        # (ordinary + 5/11) Bedtime shutdown — the evening lights and the TV are
        # switched off around bedtime (~21:50–22:40, spaced so they read as
        # individual TimePattern(OFF)s, not one merged session).
        add("dining_light", DeviceType.LIGHT, "dining", DeviceAction.OFF,
            _at(day, 21, 50, jitter=6), triggered_by="mother")
        add("hall_tv", DeviceType.TV, "hall", DeviceAction.OFF,
            _at(day, 22, 5, jitter=6), triggered_by="son")
        add("hall_light", DeviceType.LIGHT, "hall", DeviceAction.OFF,
            _at(day, 22, 20, jitter=6), triggered_by="mother")
        add("porch_light", DeviceType.LIGHT, "porch", DeviceAction.OFF,
            _at(day, 22, 35, jitter=6))
        add("kitchen_light", DeviceType.LIGHT, "kitchen", DeviceAction.OFF,
            _at(day, 22, 40, jitter=6), triggered_by="mother")

    # ───────────── TODAY: inject concrete current-state anomalies ─────────────
    # (These power the LIVE /context/H003 endpoint. The demo script instead
    #  builds explicit per-feature states so every detector can be shown.)
    if include_geyser_anomaly:
        # Geyser switched ON 40 min ago and never stopped (usual ~20 min) →
        # likely forgotten / water heater wasting power (and a scald risk).
        forty_ago = datetime.now(timezone.utc) - timedelta(minutes=40)
        add("bath_geyser", DeviceType.OTHER, "bath", DeviceAction.ON, forty_ago,
            triggered_by="father")

    if include_motor_anomaly:
        # Water motor switched ON 40 min ago and never stopped (usual ~15 min) →
        # likely forgotten / overhead tank may be overflowing.
        forty_ago = datetime.now(timezone.utc) - timedelta(minutes=40)
        add("water_motor", DeviceType.MOTOR, "utility", DeviceAction.ON, forty_ago)

    if include_left_on:
        # Son switched the fan/light ON at 07:30 and left without turning them
        # off → they should be off by ~08:00 (learned departure OFF time).
        morning = today.replace(hour=7, minute=30, tzinfo=timezone.utc)
        add("son_room_fan", DeviceType.FAN, "son_room", DeviceAction.ON, morning,
            triggered_by="son")
        add("son_room_light", DeviceType.LIGHT, "son_room", DeviceAction.ON, morning,
            triggered_by="son")

    return events
