"""Ambient sound understanding — the household "ear".

The browser classifies raw microphone audio LOCALLY (Google MediaPipe YAMNet —
free, unlimited, nothing leaves the device) into AudioSet labels. This module is
the *interpretation brain*: it maps those labels to a household-meaningful sound,
reads the live house context (time, who's home, which devices are on) and any
learned ambient routine, and returns a deterministic interpretation + prompt +
optional action.

Design (consistent with the platform philosophy):
  * Detection is on-device and free — no paid/rate-limited model.
  * Interpretation is DETERMINISTIC and explainable (a rules table). An LLM is
    NOT required; it may later only *rephrase* the prompt.
  * Ambient sounds are also logged as events (device id ``ambient_<key>``) so the
    SAME deterministic pattern engine learns routines from them over time
    ("the pressure cooker whistles ~13:00 daily") — which then lets us tell an
    EXPECTED sound from an UNUSUAL one ("a baby crying at 02:00, not the usual 20:00").

Privacy: only NON-lexical sound *events* are handled here — never speech content.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Severity ladder for an ambient interpretation.
#   info    → ambient awareness, no action needed
#   suggest → a helpful optional action (asks before doing it)
#   warn    → a care/attention concern worth surfacing
#   alert   → a safety/security emergency
SEVERITIES = ("info", "suggest", "warn", "alert")

NIGHT_START, NIGHT_END = 22, 6  # 22:00–06:00 counts as night


@dataclass(frozen=True)
class Sense:
    """How a sound becomes *meaningful* — its anomaly strategy.

    A single sound is data; the insight is whether it deviates from what's normal
    FOR THAT SOUND. Each sound picks one strategy:

      * ``instant``  — intrinsically significant; flag on any occurrence
                       (smoke alarm, glass break).
      * ``rate``     — a learned COUNT per time-window; flag when today's count in
                       the window exceeds the baseline (a cooker whistling far more
                       than usual → maybe forgotten on the flame).
      * ``burst``    — quiet is normal; flag ``burst_count`` occurrences within
                       ``burst_minutes`` (repeated coughing → someone unwell).
      * ``surface``  — no schedule; surface EVERY occurrence to the LLM, which
                       judges severity from recent frequency + time + context
                       (a baby crying).
    """
    strategy: str                       # instant | rate | burst | surface
    windows: tuple = ()                 # ((start_hour, end_hour), ...) for `rate`
    burst_minutes: int = 15
    burst_count: int = 4
    baseline_extra: int = 2             # today > mean + this (and > mean+2σ) → flag
    min_days: int = 3                   # need this many past days for a baseline


@dataclass(frozen=True)
class Sound:
    key: str
    label: str
    emoji: str
    category: str          # cooking | safety | care | security | comfort | activity
    yamnet: list[str]      # AudioSet display names that map to this sound
    meaning: str
    severity: str = "info"
    device: str | None = None            # real device an action can target
    action: str | None = None            # ON / OFF / OPEN / CLOSE
    requires_confirmation: bool = False
    prompt: str = ""                     # default spoken/shown line
    field_note: str = field(default="")  # short "why it matters" for the UI
    sense: "Sense | None" = None         # how it becomes meaningful (anomaly logic)


# ── The household sound taxonomy ─────────────────────────────────────────────
# Ordered roughly by how strongly it drives an action. `yamnet` lists the raw
# AudioSet labels the browser classifier may emit for this sound (several map to
# one household meaning — a pressure-cooker whistle reads as Whistle/Steam/Hiss).
SOUNDS: list[Sound] = [
    Sound("smoke_alarm", "Smoke / fire alarm", "🚨", "safety",
          ["Smoke detector, smoke alarm", "Fire alarm", "Alarm", "Buzzer"],
          "A smoke or fire alarm is sounding.", "alert",
          device="kitchen_gas_stove", action="OFF", requires_confirmation=False,
          prompt="Smoke alarm detected — cutting the gas and alerting the family now.",
          field_note="Immediate safety emergency.",
          sense=Sense("instant")),
    Sound("glass_break", "Glass breaking", "🔨", "security",
          ["Glass", "Shatter", "Breaking"],
          "Glass shattered — a possible break-in or accident.", "alert",
          prompt="I heard glass shatter — checking for a break-in and alerting the family.",
          field_note="Security / injury risk.",
          sense=Sense("instant")),
    Sound("person_crying", "Someone crying", "😢", "care",
          ["Crying, sobbing", "Wail, moan", "Whimper"],
          "An adult sounds distressed.", "warn",
          prompt="Someone sounds upset — would you like me to check in on them?",
          field_note="Emotional / wellbeing signal."),
    Sound("baby_cry", "Baby crying", "👶", "care",
          ["Baby cry, infant cry", "Crying, sobbing"],
          "A baby is crying and may need attention.", "suggest",
          device="nursery_light", action="ON", requires_confirmation=True,
          prompt="The baby's crying — shall I softly light the nursery and notify a parent?",
          field_note="Infant care.",
          sense=Sense("surface", burst_minutes=20, burst_count=3)),
    Sound("pressure_cooker", "Pressure cooker whistle", "🔔", "cooking",
          ["Whistle", "Steam", "Hiss", "Boiling", "Sizzle"],
          "The pressure cooker is whistling — cooking is likely finishing.", "suggest",
          device="kitchen_gas_stove", action="OFF", requires_confirmation=True,
          prompt="The pressure cooker's whistling — cooking's likely done. Turn off the gas?",
          field_note="Prevents over-cooking / gas left on.",
          sense=Sense("rate", windows=((11, 15), (18, 22)), baseline_extra=2)),
    Sound("cough", "Coughing / sneezing", "🤧", "care",
          ["Cough", "Sneeze", "Throat clearing"],
          "Repeated coughing or sneezing — someone may be unwell.", "info",
          prompt="I heard some coughing — I'll note it in case someone's coming down with something.",
          field_note="Early wellbeing hint.",
          sense=Sense("burst", burst_minutes=10, burst_count=4)),
    Sound("doorbell", "Doorbell / knock", "🔔", "security",
          ["Doorbell", "Ding-dong", "Knock"],
          "Someone is at the door.", "info",
          device="main_door", action=None,
          prompt="Someone's at the door.",
          field_note="Visitor / delivery."),
    Sound("alarm_clock", "Alarm clock", "⏰", "activity",
          ["Alarm clock", "Beep, bleep"],
          "A wake-up alarm is ringing.", "info",
          prompt="Morning alarm — I can start the wake-up routine (curtains, lights).",
          field_note="Start-of-day trigger."),
    Sound("kettle_boil", "Kettle / chai boiling", "🫖", "cooking",
          ["Boiling", "Steam"],
          "Water or chai is boiling.", "info",
          device="chai_kettle", action=None,
          prompt="Sounds like the chai's ready.",
          field_note="Cooking activity."),
    Sound("water_running", "Tap / water running", "🚰", "activity",
          ["Water tap, faucet", "Sink (filling or washing)", "Water"],
          "A tap or water flow is running.", "info",
          prompt="A tap's been running — I'll flag it if it keeps going.",
          field_note="Water-waste awareness."),
    Sound("dog_bark", "Dog barking", "🐶", "security",
          ["Dog", "Bark", "Howl"],
          "A dog is barking.", "info",
          prompt="The dog's barking — keeping an ear out.",
          field_note="Possible visitor / disturbance."),
    Sound("telephone", "Phone ringing", "📞", "activity",
          ["Telephone bell ringing", "Ringtone", "Telephone"],
          "A phone is ringing.", "info",
          prompt="The phone's ringing.",
          field_note="Communication."),
    Sound("snoring", "Snoring", "😴", "comfort",
          ["Snoring", "Breathing"],
          "Someone is asleep.", "info",
          prompt="Someone's asleep — switching to a quiet, dim mode.",
          field_note="Sleep detected."),
    Sound("vacuum", "Vacuum cleaner", "🧹", "activity",
          ["Vacuum cleaner"],
          "A vacuum cleaner is running — housekeeping.", "info",
          prompt="Vacuuming underway — housekeeping time.",
          field_note="Chore activity."),
    Sound("dishes", "Dishes / cooking clatter", "🍽️", "activity",
          ["Dishes, pots, and pans", "Cutlery, silverware", "Chopping (food)"],
          "Kitchen clatter — cooking or washing up.", "info",
          prompt="Kitchen sounds busy — meal prep or clean-up.",
          field_note="Kitchen activity."),
    Sound("temple_bell", "Temple bell / aarti", "🛕", "comfort",
          ["Bell", "Church bell", "Chime", "Change ringing (campanology)", "Bicycle bell"],
          "A prayer bell or aarti — a daily devotional routine.", "info",
          prompt="Sounds like aarti time — keeping the home calm and warm.",
          field_note="Daily prayer routine."),
    Sound("mixer_grinder", "Mixer-grinder", "🌀", "cooking",
          ["Blender", "Food processor", "Mechanical fan"],
          "The mixer-grinder is running — breakfast or masala prep.", "info",
          prompt="Mixer's running — morning cooking underway.",
          field_note="Kitchen prep activity."),
    Sound("washing_machine", "Washing machine", "🧺", "activity",
          ["Washing machine", "Mechanisms", "Sewing machine"],
          "The washing machine is running.", "info",
          prompt="Laundry's on — I'll let you know when it's likely done.",
          field_note="Chore activity."),
    Sound("tv_on", "Television", "📺", "comfort",
          ["Television", "Radio"],
          "The TV is on — likely evening viewing.", "info",
          prompt="TV's on — settling in for the evening.",
          field_note="Leisure / evening routine."),
    Sound("music", "Music playing", "🎵", "comfort",
          ["Music", "Musical instrument", "Singing", "Musical ensemble"],
          "Music is playing.", "info",
          prompt="Music's playing — I'll set a nice mood.",
          field_note="Leisure / mood."),
    Sound("exhaust_fan", "Exhaust / chimney fan", "💨", "cooking",
          ["Mechanical fan", "Air conditioning", "Whir"],
          "The kitchen exhaust or chimney fan is running.", "info",
          prompt="Chimney's on — clearing cooking fumes.",
          field_note="Kitchen ventilation."),
]

_BY_KEY = {s.key: s for s in SOUNDS}

# Reverse index: AudioSet label (lowercased) -> canonical key. Earlier entries in
# SOUNDS win a tie so higher-priority sounds (alarm, glass) take an ambiguous
# label (e.g. "Alarm") over a lower one.
_LABEL_TO_KEY: dict[str, str] = {}
for _s in SOUNDS:
    for _lbl in _s.yamnet:
        _LABEL_TO_KEY.setdefault(_lbl.lower(), _s.key)


def get_sound(key: str) -> Sound | None:
    return _BY_KEY.get(key)


def map_yamnet_label(label: str) -> str | None:
    """Map a raw AudioSet/YAMNet label to a canonical household sound key."""
    if not label:
        return None
    return _LABEL_TO_KEY.get(label.strip().lower())


def taxonomy() -> list[dict]:
    """Serialise the taxonomy for the frontend (classifier mapping + buttons)."""
    return [
        {
            "key": s.key, "label": s.label, "emoji": s.emoji, "category": s.category,
            "yamnet": s.yamnet, "meaning": s.meaning, "severity": s.severity,
            "device": s.device, "action": s.action,
            "requires_confirmation": s.requires_confirmation, "field_note": s.field_note,
        }
        for s in SOUNDS
    ]


def _is_night(hour: int) -> bool:
    return hour >= NIGHT_START or hour < NIGHT_END


def _hhmm_to_min(hhmm: str) -> int | None:
    try:
        h, m = hhmm.split(":")
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return None


def ambient_device_id(key: str) -> str:
    """The synthetic device id an ambient sound is logged under, so the pattern
    engine learns a routine for it (e.g. ``ambient_pressure_cooker``)."""
    return f"ambient_{key}"


def interpret(
    key: str,
    *,
    hour: int,
    now_min: int | None = None,
    people_home: list[str] | None = None,
    active_devices: list[str] | None = None,
    learned: dict | None = None,
) -> dict:
    """Interpret a detected sound against live context + any learned routine.

    ``learned`` (optional): ``{"usual_time": "HH:MM", "window_minutes": int,
    "confidence": float}`` for this sound's learned routine, used to judge
    EXPECTED vs UNUSUAL timing.
    """
    s = _BY_KEY.get(key)
    if s is None:
        return {
            "sound": key, "label": key, "recognised": False,
            "category": "activity", "severity": "info", "meaning": "Unrecognised sound.",
            "prompt": "I heard something I don't recognise yet.",
            "suggested_action": None, "requires_confirmation": False,
            "timing": "new", "routine_note": "",
        }

    people = people_home or []
    active = set(active_devices or [])
    night = _is_night(hour)
    severity = s.severity
    prompt = s.prompt
    action = None
    suppress_default_action = False
    routine_note = ""

    # ── Context adjustments ──────────────────────────────────────────────────
    if s.key == "pressure_cooker":
        if "kitchen_gas_stove" in active:
            action = {"device": "kitchen_gas_stove", "action": "OFF",
                      "requires_confirmation": True}
        else:
            severity = "info"
            suppress_default_action = True  # nothing to turn off
            prompt = "Pressure cooker whistling — the gas is already off, so all good."
    elif s.key == "smoke_alarm":
        # Always an emergency; only add the gas-off action if the stove is on.
        if "kitchen_gas_stove" in active:
            action = {"device": "kitchen_gas_stove", "action": "OFF",
                      "requires_confirmation": False}
    elif s.key == "baby_cry":
        if night:
            action = {"device": "nursery_light", "action": "ON",
                      "requires_confirmation": True}
            prompt = "The baby's crying at night — shall I softly light the nursery and notify a parent?"
    elif s.key == "glass_break":
        if not people:
            prompt = "Glass shattered while the house is empty — this looks like a break-in. Alerting the family."
        elif night:
            prompt = "Glass shattered in the night — checking for a break-in and alerting the family."
    elif s.key == "person_crying":
        if any(p in ("grandma", "grandpa") for p in people):
            prompt = "An elderly family member sounds distressed — I'd check in and, if needed, call family."
            severity = "warn"
    elif s.key == "snoring" and not night:
        prompt = "Someone's napping — I'll keep things quiet."

    if action is None and not suppress_default_action and s.device and s.action:
        action = {"device": s.device, "action": s.action,
                  "requires_confirmation": s.requires_confirmation}

    # ── Expected vs unusual timing (needs a learned routine) ─────────────────
    # Skip for "surface" sounds (e.g. a baby cry) — they have no schedule, so an
    # "unusual timing" escalation would be meaningless; frequency alone judges them.
    timing = "new"
    _use_timing = not (s.sense and s.sense.strategy == "surface")
    if _use_timing and learned and learned.get("usual_time"):
        usual = _hhmm_to_min(learned["usual_time"])
        win = int(learned.get("window_minutes", 30)) + 45  # grace
        cur = now_min if now_min is not None else hour * 60
        if usual is not None:
            # circular distance on a 24h clock
            diff = abs(cur - usual)
            diff = min(diff, 1440 - diff)
            if diff <= win:
                timing = "expected"
                routine_note = f"On schedule — usually around {learned['usual_time']}."
            else:
                timing = "unusual"
                routine_note = (
                    f"Unusual timing — this normally happens around "
                    f"{learned['usual_time']}, not now."
                )
                # An unusual care/security sound is more concerning.
                if s.category in ("care", "security") and severity in ("info", "suggest"):
                    severity = "warn"

    return {
        "sound": s.key,
        "label": s.label,
        "emoji": s.emoji,
        "recognised": True,
        "category": s.category,
        "severity": severity,
        "meaning": s.meaning,
        "prompt": prompt,
        "suggested_action": action,
        "requires_confirmation": bool(action and action.get("requires_confirmation")),
        "timing": timing,
        "routine_note": routine_note,
    }
