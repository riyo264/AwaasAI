"""Defense-in-depth — group anomalies into three independent safety layers and
measure how strongly they corroborate each other.

The safety engine watches three layers, each catching a class of emergency the
others miss:

  1. Wellbeing (behavioral)  — the person stopped using the home normally
                               (silent collapse; needs no extra hardware).
  2. Hazard (environmental)  — a dangerous *state* that could cause an emergency
                               (gas on, unsafe door/window, appliance overrun).
  3. Vitals (direct signal)  — acute medical ground truth from a wearable
                               (abnormal vitals, SOS/fall).

The crux is **corroboration**: one weak signal shouldn't cry wolf, but weak
signals from independent layers that *agree* are almost certainly real. When two
or more layers light up we raise confidence — and a wellbeing + hazard combo
(e.g. no movement AND gas left on) is treated as an emergency even though
neither alone would be. All deterministic, all explainable, no ML.
"""
from __future__ import annotations

from safety.models.context import Anomaly, AnomalyType
from safety.models.safety import LayeredAssessment, SafetyLayer

# Which layer each anomaly type belongs to.
_LAYER_OF = {
    # 1 · Wellbeing — behavioral / routine deviation
    AnomalyType.INACTIVITY: 1,
    AnomalyType.GLOBAL_INACTIVITY: 1,
    AnomalyType.MISSED_ROUTINE: 1,
    AnomalyType.MISSED_MEDICINE: 1,
    AnomalyType.MISSED_ARRIVAL: 1,
    # 2 · Hazard — dangerous environmental state
    AnomalyType.DEVICE_LEFT_ON: 2,
    AnomalyType.DURATION_EXCEEDED: 2,
    AnomalyType.DEVICE_ACTIVE_TOO_LONG: 2,
    AnomalyType.UNSAFE_AT_NIGHT: 2,
    AnomalyType.UNEXPECTED_ACTIVITY: 2,
    # 3 · Vitals — acute medical ground truth
    AnomalyType.HEALTH_ALERT: 3,
    AnomalyType.SOS: 3,
}

_LAYER_META = {
    1: ("wellbeing", "Wellbeing", "🚶", "Are they up and moving as usual?"),
    2: ("hazard", "Home Hazards", "🔥", "Is the home itself safe right now?"),
    3: ("vitals", "Vital Signs", "❤️", "Is the person physically okay?"),
}

_SEV_RANK = {"clear": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
_RANK_SEV = ["clear", "low", "medium", "high", "critical"]


def _worst(a: str, b: str) -> str:
    return a if _SEV_RANK.get(a, 0) >= _SEV_RANK.get(b, 0) else b


def layer_of(anomaly_type: str) -> int | None:
    """The layer (1/2/3) an anomaly type belongs to, or None if unmapped."""
    try:
        return _LAYER_OF.get(AnomalyType(anomaly_type))
    except ValueError:
        return None


def build_layers(anomalies: list[Anomaly]) -> LayeredAssessment:
    """Group anomalies into the three layers and score cross-layer corroboration."""
    buckets: dict[int, list[Anomaly]] = {1: [], 2: [], 3: []}
    for a in anomalies:
        layer = _LAYER_OF.get(a.type)
        if layer:
            buckets[layer].append(a)

    layers: list[SafetyLayer] = []
    for lid in (1, 2, 3):
        key, name, icon, tagline = _LAYER_META[lid]
        items = buckets[lid]
        severity = "clear"
        detail = None
        for a in items:
            severity = _worst(severity, a.severity)
        if items:
            worst = max(items, key=lambda x: _SEV_RANK.get(x.severity, 0))
            detail = worst.detail
        layers.append(
            SafetyLayer(
                layer=lid,
                key=key,
                name=name,
                icon=icon,
                tagline=tagline,
                active=bool(items),
                severity=severity,
                concern_count=len(items),
                concern_types=[a.type.value for a in items],
                detail=detail,
            )
        )

    active = [l for l in layers if l.active]
    active_layers = len(active)

    wellbeing_on = layers[0].active
    hazard_on = layers[1].active
    vitals_on = layers[2].active

    # Corroboration score: rises with the number of *independent* layers that
    # agree, nudged up by the worst severity seen. One layer alone tops out low.
    worst_rank = max((_SEV_RANK.get(l.severity, 0) for l in active), default=0)
    corroboration = round(min(1.0, 0.34 * active_layers + 0.08 * worst_rank), 2)
    corroborated = active_layers >= 2

    # The multi-layer payoff: a silent-collapse signal (wellbeing) next to a live
    # danger (hazard), or vitals alongside either, is an emergency even if no
    # single concern is individually "extreme".
    corroborated_emergency = (wellbeing_on and hazard_on) or (
        vitals_on and (wellbeing_on or hazard_on)
    )

    headline = _headline(active_layers, active, corroborated_emergency)

    return LayeredAssessment(
        layers=layers,
        active_layers=active_layers,
        corroboration=corroboration,
        corroborated=corroborated,
        corroborated_emergency=corroborated_emergency,
        headline=headline,
    )


def _headline(active_layers: int, active: list[SafetyLayer], emergency: bool) -> str:
    if active_layers == 0:
        return "All three safety layers are clear."
    if active_layers == 1:
        return f"{active[0].name} flagged — one layer watching."
    names = " + ".join(l.name for l in active)
    if emergency:
        return f"{active_layers} independent layers agree ({names}) — corroborated emergency."
    return f"{active_layers} independent layers agree ({names}) — corroborated concern."
