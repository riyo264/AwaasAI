"""Safety overlay — vulnerability-aware re-interpretation of a context object.

This is the ONLY genuinely new piece of logic the safety engine adds on top of
the duplicated pattern pipeline. It is a pure, deterministic decorator:

    (ContextObject, occupants, profiles)  ->  enriched ContextObject

It does three things, all explainable and ML-free:

1. Resolve the household's vulnerability from WHO is currently home.
2. Escalate each anomaly's severity by that vulnerability (the same open door is
   "low" with a capable adult home, but "critical" for an elderly person alone).
3. Roll everything up into a SafetyAssessment (0-100 score + Safe/Inactive/
   Needs-Attention/Emergency status) with a human-readable rationale.

Nothing here calls an LLM — Bedrock/Groq still only *phrases* the result.
"""
from __future__ import annotations

from safety.app.config import get_settings
from safety.models.context import (
    Anomaly,
    AnomalyType,
    ContextObject,
    ContextType,
)
from safety.models.safety import (
    PersonProfile,
    SafetyAssessment,
    SafetyStatus,
    Vulnerability,
)

# Base risk rank per anomaly type (before vulnerability escalation).
# 0 = informational, 4 = critical.
_BASE_RANK = {
    AnomalyType.MISSED_ROUTINE: 1,
    AnomalyType.MISSED_MEDICINE: 2,
    AnomalyType.MISSED_ARRIVAL: 2,
    AnomalyType.DEVICE_LEFT_ON: 2,
    AnomalyType.DURATION_EXCEEDED: 2,
    AnomalyType.DEVICE_ACTIVE_TOO_LONG: 2,
    AnomalyType.UNEXPECTED_ACTIVITY: 3,
    AnomalyType.INACTIVITY: 3,
    AnomalyType.UNSAFE_AT_NIGHT: 3,
    AnomalyType.GLOBAL_INACTIVITY: 4,
    AnomalyType.HEALTH_ALERT: 4,
    AnomalyType.SOS: 4,
}

# Rank -> severity label. Index by clamped, escalated rank.
_RANK_TO_SEVERITY = ["low", "low", "medium", "high", "critical"]
# Severity label -> points deducted from the 100-point safety score.
_SEVERITY_PENALTY = {"low": 4, "medium": 12, "high": 28, "critical": 55}


def _vuln_weight(v: Vulnerability) -> float:
    s = get_settings()
    return {
        Vulnerability.NORMAL: s.vuln_weight_normal,
        Vulnerability.CHILD: s.vuln_weight_child,
        Vulnerability.PREGNANT: s.vuln_weight_pregnant,
        Vulnerability.UNWELL: s.vuln_weight_unwell,
        Vulnerability.ELDERLY: s.vuln_weight_elderly,
    }[v]


def resolve_vulnerability(
    occupants: list[str],
    profiles: dict[str, PersonProfile],
) -> tuple[float, str | None, bool]:
    """Return (home_vulnerability_factor, most_vulnerable_person, vulnerable_alone).

    The home's factor is the MAX vulnerability over who is home — but a capable
    NORMAL adult present *mitigates* it (a fit adult can respond to a problem),
    so we multiply by ``supervised_mitigation`` in that case. ``vulnerable_alone``
    is True when a non-normal person is home with no normal adult.
    """
    s = get_settings()
    if not occupants:
        return 1.0, None, False

    present = [
        profiles.get(p, PersonProfile(person_id=p, display_name=p.title()))
        for p in occupants
    ]
    has_capable_adult = any(p.vulnerability == Vulnerability.NORMAL for p in present)

    # Most vulnerable occupant drives the factor.
    most = max(present, key=lambda p: _vuln_weight(p.vulnerability))
    factor = _vuln_weight(most.vulnerability)
    vulnerable_alone = most.vulnerability != Vulnerability.NORMAL and not has_capable_adult

    if has_capable_adult and most.vulnerability != Vulnerability.NORMAL:
        factor = max(1.0, factor * s.supervised_mitigation)

    most_id = most.person_id if most.vulnerability != Vulnerability.NORMAL else None
    return factor, most_id, vulnerable_alone


def _escalate(anomaly: Anomaly, factor: float) -> Anomaly:
    """Return a copy of ``anomaly`` with severity escalated by ``factor``."""
    base_rank = _BASE_RANK.get(anomaly.type, 2)
    # Escalation: scale the base rank, round, clamp to [0,4].
    escalated = min(4, max(0, round(base_rank * factor)))
    anomaly.base_severity = _RANK_TO_SEVERITY[min(4, base_rank)]
    anomaly.severity = _RANK_TO_SEVERITY[escalated]
    anomaly.vulnerability_factor = round(factor, 2)
    return anomaly


def _status_from(score: float, anomalies: list[Anomaly]) -> SafetyStatus:
    types = {a.type for a in anomalies}
    if (
        types & {AnomalyType.SOS, AnomalyType.HEALTH_ALERT, AnomalyType.GLOBAL_INACTIVITY}
        or score < 25
    ):
        return SafetyStatus.EMERGENCY
    if AnomalyType.INACTIVITY in types and not (
        types - {AnomalyType.INACTIVITY, AnomalyType.MISSED_ROUTINE}
    ):
        return SafetyStatus.INACTIVE
    if score < 60 or any(a.severity in {"high", "critical"} for a in anomalies):
        return SafetyStatus.NEEDS_ATTENTION
    return SafetyStatus.SAFE


def assess(
    context: ContextObject,
    *,
    occupants: list[str],
    profiles: dict[str, PersonProfile],
) -> ContextObject:
    """Enrich ``context`` in place with escalated severities + a SafetyAssessment.

    ``occupants`` is the list of people currently home (derived from
    ``people_home`` upstream); ``profiles`` maps person_id -> PersonProfile.
    """
    factor, most_vulnerable, vulnerable_alone = resolve_vulnerability(occupants, profiles)

    for a in context.anomalies:
        _escalate(a, factor)

    # Safety score: start at 100, deduct per (escalated) anomaly severity.
    score = 100.0
    for a in context.anomalies:
        score -= _SEVERITY_PENALTY.get(a.severity, 8)
    score = max(0.0, min(100.0, score))

    status = _status_from(score, context.anomalies)

    # Build an explainable rationale.
    who = ", ".join(
        profiles[p].display_name if p in profiles else p.title() for p in occupants
    ) or "no one"
    if not context.anomalies:
        rationale = f"All routines and home-safety checks look normal with {who} home."
    else:
        lead = max(
            context.anomalies,
            key=lambda a: _SEVERITY_PENALTY.get(a.severity, 0),
        )
        vuln_note = (
            f" An at-risk member ({profiles[most_vulnerable].display_name}, "
            f"{profiles[most_vulnerable].vulnerability.value}) is home"
            + (" alone, so concerns are escalated." if vulnerable_alone else " with support.")
            if most_vulnerable and most_vulnerable in profiles
            else ""
        )
        rationale = (
            f"{len(context.anomalies)} concern(s) with {who} home; "
            f"most pressing: {lead.detail or lead.type.value}.{vuln_note}"
        )

    # Defense-in-depth: group the (escalated) anomalies into the three layers
    # and score how strongly they corroborate each other.
    from safety.logic.safety_layers import build_layers

    context.safety = SafetyAssessment(
        status=status,
        safety_score=round(score, 1),
        vulnerable_alone=vulnerable_alone,
        occupants=occupants,
        occupant_labels={
            pid: (profiles[pid].display_name.split(" (")[0] if pid in profiles else pid.title())
            for pid in occupants
        },
        most_vulnerable=most_vulnerable,
        most_vulnerable_kind=(
            profiles[most_vulnerable].vulnerability.value
            if most_vulnerable and most_vulnerable in profiles
            else None
        ),
        vulnerability_factor=round(factor, 2),
        rationale=rationale,
        layers=build_layers(context.anomalies),
    )

    # Promote the headline context type for emergencies / safety alerts so the
    # narrator and dashboard lead with urgency.
    if status == SafetyStatus.EMERGENCY:
        context.context_type = ContextType.EMERGENCY
    elif status == SafetyStatus.NEEDS_ATTENTION and context.context_type in {
        ContextType.NORMAL,
        ContextType.ROUTINE_SUGGESTION,
    }:
        context.context_type = ContextType.SAFETY_ALERT

    return context
