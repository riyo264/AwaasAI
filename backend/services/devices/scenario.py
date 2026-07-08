"""
H003 demo scenario data — the FIXED "Indian-context care home" used by the
Devices (Ambient Intelligence) section.

This module is pure data + tiny pure helpers. It defines, for the H003 house:

  • PATTERN routines — what the home does on its own at a given time of day
    (proactive, learned schedule). Driven by the demo clock.
  • MOOD signals — reactive comfort adjustments for how a person feels.
  • SAFETY signals — protective overrides when something is wrong.

Nothing here is persisted. Everything is deterministic: the same inputs always
produce the same room directives, so the demo is fully explainable end-to-end.

Device ids and room keys MUST match frontend/src/config/houseLayout.js (H003).
"""
from __future__ import annotations

# ── Source identifiers + priority ladder ─────────────────────────────────────
# Higher number wins when two sources both want the same room.
SOURCE_DEFAULT = "default"
SOURCE_PATTERN = "pattern"
SOURCE_MOOD = "mood"
SOURCE_SAFETY = "safety"
SOURCE_MANUAL = "manual"

PRIORITY: dict[str, int] = {
    SOURCE_MANUAL: 4,   # a human took control — beats everything (auto-expires)
    SOURCE_SAFETY: 3,   # danger beats comfort
    SOURCE_MOOD: 2,     # respond to the person present
    SOURCE_PATTERN: 1,  # the learned routine for this time
    SOURCE_DEFAULT: 0,  # nothing to say
}

# Accent colours per source — the frontend tints each room by who is in control.
SOURCE_META = {
    SOURCE_MANUAL: {"label": "Manual", "color": "#f59e0b", "icon": "✋"},
    SOURCE_SAFETY: {"label": "Safety", "color": "#ef4444", "icon": "🛡️"},
    SOURCE_MOOD: {"label": "Mood", "color": "#a855f7", "icon": "🧠"},
    SOURCE_PATTERN: {"label": "Pattern", "color": "#38bdf8", "icon": "📅"},
    SOURCE_DEFAULT: {"label": "Idle", "color": "#64748b", "icon": "·"},
}

HOUSEHOLD_ID = "H003"


def _mins(hhmm: str) -> int:
    """'HH:MM' → minutes since midnight."""
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


# ── PATTERN routines (proactive, time-driven) ────────────────────────────────
# Each routine owns one or more rooms for a window of the day. A directive says
# which devices that routine turns ON and the ambient feel of the room.
# `start`/`end` are inclusive-start, exclusive-end minutes of the day.
PATTERN_ROUTINES = [
    {
        "id": "morning_bath",
        "label": "Morning Geyser",
        "start": _mins("05:45"),
        "end": _mins("06:45"),
        "rooms": {
            "bath": {
                "devices_on": ["bath_geyser", "bath_light"],
                "ambient": {"light_color": "#fde047", "brightness": 75,
                            "music": None, "notification_mode": "normal"},
                "reason": "Morning geyser heats water for baths, then switches "
                          "itself off (learned daily, ~20 min).",
            },
        },
    },
    {
        "id": "morning_pooja",
        "label": "Morning Pooja",
        "start": _mins("05:30"),
        "end": _mins("07:30"),
        "rooms": {
            "pooja_room": {
                "devices_on": ["pooja_lamp", "bhajan_speaker"],
                "ambient": {"light_color": "#fbbf24", "brightness": 70,
                            "music": "bhajan", "notification_mode": "normal"},
                "reason": "Morning pooja routine — lamp lit & bhajan playing "
                          "(learned daily, 28 days).",
            },
        },
    },
    {
        "id": "morning_chai",
        "label": "Morning Chai",
        "start": _mins("06:30"),
        "end": _mins("08:00"),
        "rooms": {
            "kitchen": {
                "devices_on": ["chai_kettle", "kitchen_light"],
                "ambient": {"light_color": "#fde047", "brightness": 80,
                            "music": None, "notification_mode": "normal"},
                "reason": "Morning chai — kettle & kitchen light on "
                          "(learned weekday mornings).",
            },
        },
    },
    {
        "id": "son_departure",
        "label": "Son's Departure",
        "start": _mins("08:00"),
        "end": _mins("09:30"),
        "rooms": {
            "son_room": {
                "devices_on": [],  # everything OFF — he has left for work
                "ambient": {"light_color": "#1e293b", "brightness": 0,
                            "music": None, "notification_mode": "normal"},
                "reason": "Son leaves for work — fan & light auto-off "
                          "(learned weekdays, saves power).",
            },
        },
    },
    {
        "id": "evening_hall",
        "label": "Evening TV",
        "start": _mins("18:00"),
        "end": _mins("22:15"),
        "rooms": {
            "hall": {
                "devices_on": ["hall_tv", "hall_light"],
                "ambient": {"light_color": "#fca5a5", "brightness": 55,
                            "music": None, "notification_mode": "normal"},
                "reason": "Evening in the hall — the family light and TV come on "
                          "(learned weekday evenings).",
            },
        },
    },
    {
        "id": "dinner",
        "label": "Dinner",
        "start": _mins("19:30"),
        "end": _mins("22:00"),
        "rooms": {
            "dining": {
                "devices_on": ["dining_light"],
                "ambient": {"light_color": "#fde047", "brightness": 80,
                            "music": None, "notification_mode": "normal"},
                "reason": "Dinner time — the dining light is on (learned nightly, "
                          "switched off by bedtime).",
            },
        },
    },
    {
        "id": "evening_security",
        "label": "Dusk Security",
        "start": _mins("18:30"),
        "end": _mins("23:59"),
        "rooms": {
            "porch": {
                "devices_on": ["porch_light"],
                "ambient": {"light_color": "#fde047", "brightness": 60,
                            "music": None, "notification_mode": "normal"},
                "reason": "Dusk — porch security light on automatically "
                          "(learned at sunset).",
            },
        },
    },
    {
        "id": "bedtime",
        "label": "Bedtime Wind-down",
        "start": _mins("21:30"),
        "end": _mins("23:59"),
        "rooms": {
            "grandpa_room": {
                "devices_on": [],
                "ambient": {"light_color": "#7c3aed", "brightness": 12,
                            "music": None, "notification_mode": "dnd"},
                "reason": "Bedtime routine — Grandpa's room dimmed, "
                          "Do-Not-Disturb on (learned ~9:45 PM nightly).",
            },
            "son_room": {
                "devices_on": [],
                "ambient": {"light_color": "#1e293b", "brightness": 0,
                            "music": None, "notification_mode": "dnd"},
                "reason": "Bedtime routine — Son's room lights off.",
            },
        },
    },
]


def active_pattern_directives(minute_of_day: int) -> dict[str, dict]:
    """Return {room_key: directive} for every PATTERN routine active at `minute`.

    If two routines touch the same room, the later-starting one wins (the more
    specific, more recent routine). Each directive is tagged with its routine.
    """
    chosen: dict[str, dict] = {}
    chosen_start: dict[str, int] = {}
    for routine in PATTERN_ROUTINES:
        if not (routine["start"] <= minute_of_day < routine["end"]):
            continue
        for room, directive in routine["rooms"].items():
            if room not in chosen or routine["start"] >= chosen_start[room]:
                chosen[room] = {
                    **directive,
                    "source": SOURCE_PATTERN,
                    "routine_id": routine["id"],
                    "routine_label": routine["label"],
                }
                chosen_start[room] = routine["start"]
    return chosen


# ── MOOD signals (reactive comfort) ──────────────────────────────────────────
# Toggled by the presenter. Each maps to a single room directive.
MOOD_SIGNALS = {
    "son_stressed": {
        "label": "Son home · stressed",
        "person": "Son",
        "room": "son_room",
        "directive": {
            "devices_on": ["son_room_fan", "son_room_light"],
            "ambient": {"light_color": "#818cf8", "brightness": 35,
                        "music": "lo-fi", "notification_mode": "reduced"},
            "reason": "Mood engine heard stress in the Son's voice — his room "
                      "softened to a cool dim glow with calming lo-fi, "
                      "notifications reduced.",
            "spoken": "You sound a bit tense. I've dimmed your room and put on "
                      "something calm.",
        },
    },
    "son_tired": {
        "label": "Son home · tired",
        "person": "Son",
        "room": "son_room",
        "directive": {
            "devices_on": ["son_room_fan"],
            "ambient": {"light_color": "#fb923c", "brightness": 18,
                        "music": "sleep", "notification_mode": "dnd"},
            "reason": "Mood engine detected tiredness — very warm dim light, "
                      "sleep sounds, Do-Not-Disturb on.",
            "spoken": "You seem tired. Winding the room down for rest.",
        },
    },
}


def mood_directive(signal_id: str | None) -> dict[str, dict]:
    """Return {room_key: directive} for the active mood signal (0 or 1)."""
    if not signal_id or signal_id not in MOOD_SIGNALS:
        return {}
    sig = MOOD_SIGNALS[signal_id]
    return {
        sig["room"]: {
            **sig["directive"],
            "source": SOURCE_MOOD,
            "signal_id": signal_id,
            "signal_label": sig["label"],
        }
    }


# ── SAFETY signals (protective override) ──────────────────────────────────────
SAFETY_SIGNALS = {
    "gas_stove": {
        "label": "Gas stove left on · kitchen empty",
        "room": "kitchen",
        "directive": {
            "devices_on": ["kitchen_light", "kitchen_gas_stove"],
            "flag_devices": ["kitchen_gas_stove"],
            "ambient": {"light_color": "#ffffff", "brightness": 100,
                        "music": None, "notification_mode": "normal"},
            "severity": "alert",
            "reason": "Gas stove has been on with no one in the kitchen — "
                      "lights raised to full and the family is being alerted.",
            "spoken": "Careful — the gas stove is still on and the kitchen is "
                      "empty. I've turned the lights up and alerted the family.",
        },
    },
    "grandpa_inactive": {
        "label": "Grandpa inactive too long",
        "room": "grandpa_room",
        "directive": {
            "devices_on": [],
            "flag_devices": ["grandpa_activity"],
            "ambient": {"light_color": "#ffffff", "brightness": 90,
                        "music": None, "notification_mode": "normal"},
            "severity": "alert",
            "reason": "No movement detected from Grandpa for an unusually long "
                      "time — raising the lights and checking in.",
            "spoken": "I haven't sensed Grandpa moving for a while. Raising the "
                      "lights and checking in on him.",
        },
    },
}


def safety_directive(signal_id: str | None) -> dict[str, dict]:
    """Return {room_key: directive} for the active safety signal (0 or 1)."""
    if not signal_id or signal_id not in SAFETY_SIGNALS:
        return {}
    sig = SAFETY_SIGNALS[signal_id]
    return {
        sig["room"]: {
            **sig["directive"],
            "source": SOURCE_SAFETY,
            "signal_id": signal_id,
            "signal_label": sig["label"],
        }
    }


# ── The guided demo script ───────────────────────────────────────────────────
# A hands-free walkthrough the frontend steps through. Each beat sets the clock
# and which signals are firing, with a caption explaining what to watch.
DEMO_BEATS = [
    {
        "id": "calm_evening",
        "title": "Dusk · the home runs itself",
        "time": "18:45",
        "mood": None,
        "safety": None,
        "caption": "Evening sets in. With nobody asking for anything, the home "
                   "just follows its learned routine — the porch security light "
                   "comes on by itself. Every room is calm and PATTERN-driven.",
    },
    {
        "id": "son_stressed",
        "title": "Son comes home stressed",
        "time": "20:00",
        "mood": "son_stressed",
        "safety": None,
        "caption": "The Son arrives home stressed. The Mood engine hears it and "
                   "ONLY his room responds — cool dim light, calming lo-fi, "
                   "notifications reduced. Notice nothing else in the house "
                   "changed: mood is targeted, not house-wide.",
    },
    {
        "id": "three_way",
        "title": "Bedtime — and danger in the kitchen",
        "time": "21:45",
        "mood": "son_stressed",
        "safety": "gas_stove",
        "caption": "Now three decision-makers act at once. PATTERN dims "
                   "Grandpa's room for bedtime. MOOD still keeps the Son's room "
                   "calm. But the gas stove was left on in an empty kitchen — "
                   "SAFETY overrides that room, throws the lights to full, and "
                   "alerts the family. Three rooms, three sources, one home.",
    },
    {
        "id": "manual",
        "title": "You step in",
        "time": "21:46",
        "mood": "son_stressed",
        "safety": "gas_stove",
        "caption": "You decide to handle the kitchen yourself — tap the gas "
                   "stove to turn it off. That room switches to MANUAL and the "
                   "AI stands back. After the override timer runs out, control "
                   "hands back to the AI automatically.",
        "hint_manual": True,
    },
]


def scenario_payload() -> dict:
    """Everything the frontend needs to drive the H003 demo."""
    return {
        "household_id": HOUSEHOLD_ID,
        "sources": SOURCE_META,
        "priority": PRIORITY,
        "mood_signals": {k: {"label": v["label"], "person": v["person"],
                             "room": v["room"]}
                         for k, v in MOOD_SIGNALS.items()},
        "safety_signals": {k: {"label": v["label"], "room": v["room"],
                               "severity": v["directive"].get("severity", "alert")}
                           for k, v in SAFETY_SIGNALS.items()},
        "routines": [{"id": r["id"], "label": r["label"]}
                     for r in PATTERN_ROUTINES],
        "beats": DEMO_BEATS,
        "manual_override_seconds": 20,
    }
