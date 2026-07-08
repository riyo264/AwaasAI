"""
Deterministic arbiter for the Devices (Ambient Intelligence) section.

Given the three observation sources for H003 — PATTERN (time-driven routine),
MOOD (reactive comfort) and SAFETY (protective override) — plus any MANUAL
human overrides, this resolves a single coherent directive PER ROOM using a
fixed priority ladder:

    MANUAL  >  SAFETY  >  MOOD  >  PATTERN  >  DEFAULT

The decision is per room, so the kitchen can be in a SAFETY alert while the
bedroom quietly follows its PATTERN routine — all at the same time.

Pure functions, no I/O, no persistence. Same inputs → same output, always.
"""
from __future__ import annotations

from services.devices import scenario as sc

# Which device ids live in which H003 room — mirrors houseLayout.js (H003).
ROOM_DEVICES: dict[str, list[str]] = {
    "grandpa_room": ["grandpa_activity"],
    "grandma_room": ["grandma_medicine"],
    "pooja_room": ["pooja_lamp", "temple_bell", "bhajan_speaker"],
    "son_room": ["son_room_fan", "son_room_light"],
    "bath": ["bath_geyser", "bath_light"],
    "entrance": ["main_door"],
    "kitchen": ["chai_kettle", "kitchen_light", "kitchen_gas_stove",
                "water_can_refill"],
    "hall": ["hall_tv", "hall_light"],
    "dining": ["dining_light"],
    "terrace": ["terrace_clothesline"],
    "porch": ["porch_light"],
    "store_room": ["water_motor", "inverter"],
}

DEVICE_TO_ROOM = {dev: room for room, devs in ROOM_DEVICES.items() for dev in devs}


def _minute_of_day(hhmm: str | None) -> int:
    if not hhmm:
        return 12 * 60
    try:
        h, m = hhmm.split(":")
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return 12 * 60


def _manual_directives(manual: dict[str, bool] | None) -> dict[str, dict]:
    """Group device-level manual overrides into per-room MANUAL directives.

    `manual` is {device_id: bool}. Any room that contains a manually-set device
    is fully handed to the human: that room's on-set becomes exactly the devices
    the human switched on. The AI stands back until the override expires (the
    frontend drops these entries when the timer runs out).
    """
    if not manual:
        return {}
    rooms: dict[str, list[str]] = {}
    for dev, on in manual.items():
        room = DEVICE_TO_ROOM.get(dev)
        if room is None:
            continue
        rooms.setdefault(room, [])
        if on:
            rooms[room].append(dev)
    out: dict[str, dict] = {}
    for room, on_devices in rooms.items():
        out[room] = {
            "source": sc.SOURCE_MANUAL,
            "devices_on": on_devices,
            "ambient": {"light_color": "#f59e0b", "brightness": 70,
                        "music": None, "notification_mode": "normal"},
            "reason": "You took manual control of this room — the AI is "
                      "standing back until the override expires.",
        }
    return out


def arbitrate(
    time: str | None = None,
    mood: str | None = None,
    safety: str | None = None,
    manual: dict[str, bool] | None = None,
) -> dict:
    """Resolve the whole H003 house for one moment in time.

    Returns a payload the frontend can render directly:
      rooms          {room_key: resolved directive + source + reason}
      active_devices [device_id]            — union of every ON device
      anomalies      {device_id: {detail}}  — SAFETY-flagged devices
      notifications  [{id, text, tone, source, room}] — spoken alert lines
      mode           the highest-priority source active anywhere (banner)
      log            [{time, source, room, text}]      — what changed & why
    """
    minute = _minute_of_day(time)

    # Gather candidate directives from each source.
    candidates: dict[str, dict] = {}  # room -> {source: directive}

    def add(directives: dict[str, dict]):
        for room, directive in directives.items():
            candidates.setdefault(room, {})[directive["source"]] = directive

    add(sc.active_pattern_directives(minute))
    add(sc.mood_directive(mood))
    add(sc.safety_directive(safety))
    add(_manual_directives(manual))

    rooms_out: dict[str, dict] = {}
    active_devices: list[str] = []
    anomalies: dict[str, dict] = {}
    notifications: list[dict] = []
    log: list[dict] = []
    top_source = sc.SOURCE_DEFAULT

    # Resolve every room in the house (even ones no source touched → DEFAULT).
    for room in ROOM_DEVICES:
        by_source = candidates.get(room, {})
        if by_source:
            winner = max(by_source.values(),
                         key=lambda d: sc.PRIORITY[d["source"]])
        else:
            winner = {
                "source": sc.SOURCE_DEFAULT,
                "devices_on": [],
                "ambient": {"light_color": "#1e293b", "brightness": 0,
                            "music": None, "notification_mode": "normal"},
                "reason": "No active routine, mood, or alert — room idle.",
            }

        src = winner["source"]
        meta = sc.SOURCE_META[src]
        # Devices the winner turns on are restricted to this room's catalogue.
        on_here = [d for d in winner.get("devices_on", [])
                   if d in ROOM_DEVICES[room]]
        active_devices.extend(on_here)

        # Safety flags → floor-plan anomaly markers.
        for dev in winner.get("flag_devices", []):
            if dev in ROOM_DEVICES[room]:
                anomalies[dev] = {"detail": winner.get("reason", "Safety alert")}

        rooms_out[room] = {
            "source": src,
            "source_label": meta["label"],
            "source_color": meta["color"],
            "source_icon": meta["icon"],
            "devices_on": on_here,
            "ambient": winner.get("ambient", {}),
            "reason": winner.get("reason", ""),
            "severity": winner.get("severity", "info"),
            "routine_label": winner.get("routine_label"),
            "signal_label": winner.get("signal_label"),
            "overridden": [s for s in by_source if s != src],
        }

        # Track the loudest source in the house for the top banner.
        if sc.PRIORITY[src] > sc.PRIORITY[top_source]:
            top_source = src

        # Spoken alert lines (safety + notable mood) feed the Alexa stack.
        spoken = winner.get("spoken")
        if spoken and src in (sc.SOURCE_SAFETY, sc.SOURCE_MOOD):
            notifications.append({
                "id": f"{src}:{room}:{winner.get('signal_id', winner.get('routine_id', ''))}",
                "text": spoken,
                "tone": "alert" if src == sc.SOURCE_SAFETY else "info",
                "source": src,
                "room": room,
            })

        # Only non-idle, non-default rooms are worth logging.
        if src != sc.SOURCE_DEFAULT:
            log.append({
                "time": time or "",
                "source": src,
                "source_label": meta["label"],
                "room": room,
                "text": winner.get("reason", ""),
            })

    # Most-severe notifications first (safety before mood).
    notifications.sort(key=lambda n: 0 if n["tone"] == "alert" else 1)
    # Log: highest-priority source first, for a readable "who decided what".
    log.sort(key=lambda e: -sc.PRIORITY[e["source"]])

    return {
        "household_id": sc.HOUSEHOLD_ID,
        "time": time,
        "mode": top_source,
        "mode_meta": sc.SOURCE_META[top_source],
        "rooms": rooms_out,
        "active_devices": active_devices,
        "anomalies": anomalies,
        "notifications": notifications,
        "log": log,
    }
