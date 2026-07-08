"""Guardian models — elderly-alone protective layer on the safety engine.

The deterministic engine raises concerns (pattern deviations + safety detectors),
already vulnerability-escalated. The Guardian *triages* them like a caring adult
in the house: it flags the single most dangerous + relevant one, and decides
whether to raise an alarm immediately (extreme) or gently CHECK IN with the
person first (less serious) before escalating.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from safety.models.safety import LayeredAssessment


class GuardianConcern(BaseModel):
    type: str                       # anomaly type value (e.g. "missed_medicine")
    device: str | None = None
    severity: str = "medium"        # low | medium | high | critical (vuln-escalated)
    detail: str = ""
    base_severity: str | None = None
    vulnerability_factor: float | None = None


class GuardianDecision(BaseModel):
    household_id: str
    situation: str = "occupied"     # elderly_alone | child_alone | ... | occupied | empty
    vigilance: bool = False         # heightened watch (a vulnerable person is alone)
    person: str = "your family member"  # who is being watched
    posture: str = "safe"           # safe | watchful | concern | emergency
    mode: str = "all_clear"         # all_clear | check_in | auto_alarm
    flagged: GuardianConcern | None = None   # THE concern surfaced now
    spoken: str = ""                # the alarm line OR the check-in question
    explanation: str = ""           # the LLM's "why I think this" reasoning
    checkin_prompt: str | None = None
    notify_family: bool = False
    family_message: str | None = None
    reason: str = ""                # why this concern was chosen
    danger_rank: list[str] = Field(default_factory=list)   # types, most→least dangerous
    all_concerns: list[GuardianConcern] = Field(default_factory=list)
    # Defense-in-depth: the three-layer view + cross-layer corroboration.
    layers: LayeredAssessment | None = None
    safety_status: str = "safe"
    safety_score: float = 100.0
    llm_powered: bool = False


class CheckinVerdict(BaseModel):
    verdict: str = "escalate"       # stand_down | escalate
    spoken: str = ""                # the Guardian's reply to the person
    explanation: str = ""           # the LLM's "why I decided this" reasoning
    notify_family: bool = False
    family_message: str | None = None
    reason: str = ""
    transcript: str = ""            # what the person said (if audio)
    llm_powered: bool = False
