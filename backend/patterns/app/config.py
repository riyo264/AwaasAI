"""Centralised application configuration.

All AWS resource names, region, and runtime toggles are read from the
environment so the same code runs identically on a developer laptop
(pointing at DynamoDB Local) and in AWS Lambda.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed settings loaded from environment variables / .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- AWS ---
    aws_region: str = "us-east-1"

    # When set (e.g. http://localhost:8000) boto3 talks to DynamoDB Local.
    # Leave empty in AWS so boto3 uses the real regional endpoint.
    dynamodb_endpoint_url: str | None = None

    # --- Table names (overridable per environment) ---
    events_table: str = "SmartHome_Events"
    state_table: str = "SmartHome_HouseholdState"
    patterns_table: str = "SmartHome_Patterns"
    # Temporary, user-driven pattern adjustments (guests / festivals) overlay.
    adjustments_table: str = "SmartHome_ContextAdjustments"
    # User-declared home profile routines (device + action + time, manually set).
    profiles_table: str = "SmartHome_HomeProfiles"

    # --- Pattern engine tuning ---
    # How many days of history the extraction job analyses.
    analysis_window_days: int = 30
    # Bucket size (minutes) used when clustering event times into routines.
    time_bucket_minutes: int = 30
    # Minimum number of occurrences before a routine is considered a pattern.
    min_pattern_occurrences: int = 3
    # Confidence below which a pattern is discarded.
    min_confidence: float = 0.6

    # --- Anomaly detection tuning ---
    # A device "left on" anomaly fires this many minutes past the usual time.
    departure_grace_minutes: int = 60
    # Duration anomaly multiplier (actual > usual * this factor).
    duration_anomaly_factor: float = 2.0
    # Absolute safety-net: a device continuously active longer than this (and
    # without a learned duration pattern) is flagged regardless of any routine
    # (e.g. a door left open for a full day). 720 min = 12 h.
    max_continuous_active_minutes: int = 720

    # --- Missed-routine detection ---
    # Only high-confidence routines are worth flagging when they don't happen.
    missed_routine_min_confidence: float = 0.7
    # A missed routine is only reported for this many minutes after its window
    # passes (keeps the signal transient instead of firing all day).
    missed_routine_horizon_minutes: int = 180

    # --- Scheduled pattern extraction (ECS-native, in-process) ---
    # Comma-separated households the background scheduler re-learns patterns for.
    # Leave empty to disable the scheduler entirely (e.g. local dev / tests).
    scheduled_household_ids: str = ""
    # How often the background scheduler runs the extraction job, in hours.
    extraction_interval_hours: float = 24.0

    # --- LLM narrator (Alexa-voice notifications) ---
    # Controls which LLM backend generates the natural-language "Alexa says…"
    # line. Set LLM_PROVIDER to "bedrock" for AWS Bedrock or "groq" for Groq.
    # If the chosen provider is unavailable, falls back to the other, then to
    # a deterministic template (no network call). The notification ALWAYS shows.
    llm_provider: str = "groq"  # "groq" or "bedrock"

    # Groq (OpenAI-compatible)
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    groq_chat_url: str = "https://api.groq.com/openai/v1/chat/completions"

    # AWS Bedrock (uses boto3 credentials from environment)
    bedrock_model_id: str = "nvidia.nemotron-super-3-120b"

    # Hard ceiling on the LLM call so a slow/unreachable API never blocks the UI.
    narrator_timeout_seconds: float = 12.0

    # --- Gemini (audio understanding for the ambient "ear") ---
    # An audio-native multimodal model that listens to a short mic clip and
    # identifies ANY household sound in open vocabulary (a text LLM cannot hear).
    # Free Google AI Studio tier — set GEMINI_API_KEY in backend/.env.
    gemini_api_key: str = ""
    # 2.5-flash is audio-capable and has free-tier quota where 2.0-flash may show
    # limit:0 for some projects/regions. Override with GEMINI_MODEL if needed.
    gemini_model: str = "gemini-2.5-flash"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_timeout_seconds: float = 20.0


@lru_cache
def get_settings() -> Settings:
    """Cached singleton so settings are parsed only once per process."""
    return Settings()
