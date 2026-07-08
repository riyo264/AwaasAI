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

    # Load the safety service's own .env first, then fall back to a shared
    # backend/.env or repo-root .env — so the Groq key (and other secrets) set
    # once for the patterns/ambient services are picked up here too, instead of
    # the narrator silently falling back to templated text.
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env", "../../.env", "backend/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- AWS ---
    aws_region: str = "us-east-1"

    # When set (e.g. http://localhost:8000) boto3 talks to DynamoDB Local.
    # Leave empty in AWS so boto3 uses the real regional endpoint.
    dynamodb_endpoint_url: str | None = None

    # --- Table names (overridable per environment) ---
    # The Safety engine is an INDEPENDENT twin of the Patterns engine: it uses
    # its OWN DynamoDB tables so its data never touches the patterns feature.
    events_table: str = "Safety_Events"
    state_table: str = "Safety_HouseholdState"
    patterns_table: str = "Safety_Patterns"
    profiles_table: str = "Safety_Profiles"

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

    # --- Adaptive Safety Intelligence (elderly-alone) tuning ---
    # No activity of ANY kind for this many minutes while a vulnerable person is
    # home alone escalates to a concern (then emergency). 240 min = 4 h.
    global_inactivity_warn_minutes: int = 240
    global_inactivity_emergency_minutes: int = 480
    # Night window (24h clock) during which an open door/window is unsafe.
    night_start_hour: int = 22
    night_end_hour: int = 6
    # Vulnerability multipliers used to escalate anomaly severity by occupant.
    vuln_weight_normal: float = 1.0
    vuln_weight_child: float = 1.7
    vuln_weight_pregnant: float = 1.8
    vuln_weight_unwell: float = 1.8
    vuln_weight_elderly: float = 2.0
    # A capable adult at home mitigates risk for a vulnerable person.
    supervised_mitigation: float = 0.6


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


@lru_cache
def get_settings() -> Settings:
    """Cached singleton so settings are parsed only once per process."""
    return Settings()
