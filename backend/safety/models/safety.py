"""Safety / vulnerability models for Adaptive Safety Intelligence.

This is the ONE genuinely new concept the safety engine adds on top of the
duplicated pattern pipeline: a notion of *who* is home and *how vulnerable*
they are, plus the deterministic safety roll-up produced by the safety overlay.

Design mirrors the rest of the codebase: plain Pydantic, no ML, every number
explainable.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class Vulnerability(str, Enum):
    """How much extra protection a person needs when something goes wrong."""

    NORMAL = "normal"      # working-age, capable adult
    CHILD = "child"        # minor at home
    PREGNANT = "pregnant"  # expecting mother, home alone
    UNWELL = "unwell"      # temporarily recovering / fragile
    ELDERLY = "elderly"    # senior living independently


class PersonProfile(BaseModel):
    """A household member the safety engine reasons about."""

    person_id: str = Field(..., examples=["grandpa"])
    display_name: str = Field(..., examples=["Grandpa"])
    vulnerability: Vulnerability = Vulnerability.NORMAL
    # Who to notify when an emergency-level concern fires (children in other
    # cities, a neighbour, a doctor). Free-form ids/phone labels for the demo.
    emergency_contacts: list[str] = Field(default_factory=list)
    # Optional wearable that streams vitals as ALERT events.
    wearable_id: str | None = None
    # Relationship label shown on the dashboard ("father", "mother", ...).
    relation: str | None = None

    def to_item(self, household_id: str) -> dict:
        return {
            "household_id": household_id,
            "person_id": self.person_id,
            "display_name": self.display_name,
            "vulnerability": self.vulnerability.value,
            "emergency_contacts": self.emergency_contacts,
            "wearable_id": self.wearable_id,
            "relation": self.relation,
        }

    @classmethod
    def from_item(cls, item: dict) -> "PersonProfile":
        return cls(
            person_id=item["person_id"],
            display_name=item.get("display_name", item["person_id"].title()),
            vulnerability=item.get("vulnerability", "normal"),
            emergency_contacts=item.get("emergency_contacts", []),
            wearable_id=item.get("wearable_id"),
            relation=item.get("relation"),
        )


class SafetyStatus(str, Enum):
    """Headline status shown on the Adaptive Safety Dashboard."""

    SAFE = "safe"
    INACTIVE = "inactive"
    NEEDS_ATTENTION = "needs_attention"
    EMERGENCY = "emergency"


class SafetyLayer(BaseModel):
    """One tier of the defense-in-depth safety model.

    The engine watches three INDEPENDENT layers, each catching a different class
    of emergency the others would miss:

      1. Wellbeing (behavioral) — silent collapse: the person stopped using the
         home the way they normally do (no hardware needed).
      2. Hazard (environmental) — a dangerous *state* that could cause an
         emergency (gas on, door/window unsafe, appliance overrunning).
      3. Vitals (direct signal) — acute medical ground truth from a wearable
         (abnormal heart rate, SOS/fall).
    """

    layer: int                       # 1 | 2 | 3
    key: str                         # "wellbeing" | "hazard" | "vitals"
    name: str
    icon: str
    tagline: str
    active: bool = False             # any concern in this layer right now
    severity: str = "clear"          # clear | low | medium | high | critical
    concern_count: int = 0
    concern_types: list[str] = Field(default_factory=list)
    detail: str | None = None        # the worst concern's human line


class LayeredAssessment(BaseModel):
    """The three-layer view + cross-layer corroboration.

    Corroboration is the crux: a single weak signal shouldn't cry wolf, but weak
    signals from INDEPENDENT layers that agree are almost certainly real — so we
    raise confidence (and urgency) when more than one layer lights up.
    """

    layers: list[SafetyLayer] = Field(default_factory=list)
    active_layers: int = 0
    corroboration: float = 0.0       # 0..1 — how strongly the layers agree
    corroborated: bool = False       # >= 2 independent layers active
    # A corroborated wellbeing + hazard combo (e.g. no movement + gas on) is an
    # emergency even though neither alone would be — the multi-layer payoff.
    corroborated_emergency: bool = False
    headline: str = "All three safety layers are clear."


class SafetyAssessment(BaseModel):
    """Deterministic safety roll-up attached to every context object.

    ``safety_score`` is 0..100 where higher = safer. Every deduction is
    explainable and surfaced in ``rationale`` so judges (and the LLM) can see
    exactly *why* the home is at a given status.
    """

    status: SafetyStatus = SafetyStatus.SAFE
    safety_score: float = Field(100.0, ge=0.0, le=100.0)
    # True when a vulnerable person is home with no capable adult present.
    vulnerable_alone: bool = False
    occupants: list[str] = Field(default_factory=list)
    # person_id -> short display name (for the narrator to speak naturally).
    occupant_labels: dict[str, str] = Field(default_factory=dict)
    most_vulnerable: str | None = None
    most_vulnerable_kind: str | None = None
    vulnerability_factor: float = 1.0
    rationale: str = ""
    # Defense-in-depth: the three-layer view + corroboration across them.
    layers: LayeredAssessment | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
