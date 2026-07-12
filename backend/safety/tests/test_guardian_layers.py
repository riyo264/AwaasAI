"""Tests for the Guardian's defense-in-depth layers.

Covers the two behaviours the demo leans on:
  * anomalies group into the three independent layers and corroborate, and
  * a wellbeing + hazard combo — neither extreme alone — is PROMOTED to an
    auto-alarm by cross-layer corroboration (with the flag the UI surfaces).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from safety.logic import guardian
from safety.logic.safety_layers import build_layers
from safety.models.context import Anomaly, AnomalyType
from safety.models.safety import SafetyAssessment, SafetyStatus

WELLBEING = Anomaly(
    type=AnomalyType.MISSED_ROUTINE, device="pooja_lamp",
    detail="Morning pooja not seen", severity="high",
    base_severity="medium", vulnerability_factor=2.0,
)
# Deliberately NOT a gas/stove device, so _is_extreme stays False on its own.
HAZARD = Anomaly(
    type=AnomalyType.DEVICE_LEFT_ON, device="water_motor",
    detail="Water motor running 40 minutes", severity="high",
    base_severity="medium", vulnerability_factor=2.0,
)


# ─── Layer grouping + corroboration ──────────────────────────────────────────


def test_layers_group_and_corroborate():
    la = build_layers([WELLBEING, HAZARD])
    assert la.active_layers == 2
    assert la.corroborated is True
    assert la.corroborated_emergency is True  # wellbeing + hazard agree
    assert {l.key for l in la.layers if l.active} == {"wellbeing", "hazard"}


def test_single_layer_is_not_an_emergency():
    la = build_layers([WELLBEING])
    assert la.active_layers == 1
    assert la.corroborated is False
    assert la.corroborated_emergency is False


# ─── Guardian promotion guardrail ────────────────────────────────────────────


def _ctx(anomalies):
    safety = SafetyAssessment(
        status=SafetyStatus.NEEDS_ATTENTION, safety_score=60.0,
        vulnerable_alone=True, occupants=["grandpa"],
        occupant_labels={"grandpa": "Ramesh"}, most_vulnerable="grandpa",
        most_vulnerable_kind="elderly", vulnerability_factor=2.0,
        layers=build_layers(anomalies),
    )
    return SimpleNamespace(anomalies=anomalies, safety=safety)


def _assess(monkeypatch, anomalies):
    monkeypatch.setattr(
        guardian.context_service, "evaluate_context", lambda *a, **k: _ctx(anomalies)
    )

    async def no_llm(*a, **k):  # deterministic fallback path
        return None

    monkeypatch.setattr(guardian, "_triage", no_llm)
    return asyncio.run(
        guardian.assess(
            "E001", active_devices=[], people_home={"grandpa": True},
            device_on_since={}, now=datetime.now(timezone.utc),
        )
    )


def test_corroboration_promotes_to_auto_alarm(monkeypatch):
    # Neither concern is extreme by itself — two independent layers agreeing
    # must promote the worst one to an immediate alarm.
    decision = _assess(monkeypatch, [WELLBEING, HAZARD])
    assert decision.mode == "auto_alarm"
    assert decision.corroboration_promoted is True
    assert decision.notify_family is True


def test_uncorroborated_concern_checks_in_first(monkeypatch):
    decision = _assess(monkeypatch, [WELLBEING])
    assert decision.mode == "check_in"
    assert decision.corroboration_promoted is False
    assert decision.notify_family is False
