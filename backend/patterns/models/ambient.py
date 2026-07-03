"""Request/response models for the ambient sound-understanding API."""
from __future__ import annotations

from pydantic import BaseModel, Field


class AmbientObserveRequest(BaseModel):
    """A sound the on-device (browser) classifier just detected."""

    sound: str | None = Field(
        None, description="Canonical sound key (e.g. 'pressure_cooker'). Provide this or `yamnet_label`."
    )
    yamnet_label: str | None = Field(
        None, description="Raw AudioSet/YAMNet label; mapped to a canonical sound server-side."
    )
    confidence: float = Field(1.0, ge=0.0, le=1.0)
    current_time: str | None = Field(None, description="Simulated HH:MM clock. None = real now.")
    people_home: list[str] = Field(default_factory=list)
    active_devices: list[str] = Field(default_factory=list, examples=[["kitchen_gas_stove"]])
    ingest: bool = Field(True, description="Log this sound as an event so routines keep learning.")
    language: str = Field("en", description="Narration language: en|hi|hinglish|ta|te|bn|mr.")


class AmbientListenRequest(BaseModel):
    """A short recorded mic clip for the audio LLM (Gemini) to identify."""

    audio_base64: str = Field(..., description="Base64 of the recorded clip (WAV preferred).")
    mime_type: str = Field("audio/wav", examples=["audio/wav", "audio/webm"])
    current_time: str | None = Field(None, description="Simulated HH:MM clock. None = real now.")
    people_home: list[str] = Field(default_factory=list)
    active_devices: list[str] = Field(default_factory=list)
    ingest: bool = Field(True, description="Log the detected sound so routines keep learning.")
    language: str = Field("en", description="Narration language: en|hi|hinglish|ta|te|bn|mr.")


class AmbientAction(BaseModel):
    device: str
    action: str
    requires_confirmation: bool = False


class AmbientInterpretation(BaseModel):
    sound: str
    label: str
    emoji: str = "🔊"
    recognised: bool = True
    category: str = "activity"
    severity: str = "info"
    meaning: str = ""
    prompt: str = ""
    suggested_action: AmbientAction | None = None
    requires_confirmation: bool = False
    timing: str = "new"          # expected | unusual | new
    routine_note: str = ""
    confidence: float = 1.0
    logged: bool = False         # was it persisted as an event?
    # --- Populated on the Gemini audio path (open-vocabulary detection) ---
    description: str = ""        # what's happening (LLM)
    likely_activity: str = ""    # the household activity implied (LLM)
    detected_raw: str = ""       # open-vocabulary sound name as heard (LLM)
    llm_powered: bool = False    # True when Gemini identified it
    source: str = "deterministic"  # deterministic | gemini
    # --- Sense-making (deterministic) + narration (LLM) ---
    flagged: bool = False        # deviates from what's normal for this sound
    sense_strategy: str = "none"  # instant | rate | burst | surface | none
    sense_reason: str = ""       # why it was flagged (human)
    evidence: dict = Field(default_factory=dict)  # numbers backing the flag
    narration: str = ""          # caring spoken line (LLM, only when flagged)
    narration_llm: bool = False  # True if the line came from the LLM
    explanation: str = ""        # brief 'why' shown on tap


class AmbientRoutine(BaseModel):
    sound: str
    label: str
    emoji: str = "🔊"
    usual_time: str
    window_minutes: int = 30
    confidence: float = 0.0
    occurrences: int = 0
