"""Shared configuration for all services."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # AWS
    aws_region: str = "us-east-1"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""

    # LLM Provider Toggle: "bedrock" or "groq"
    llm_provider: str = "bedrock"

    # Bedrock (Nvidia Nemotron)
    bedrock_model_id: str = "nvidia.nemotron-super-3-120b"

    # Groq API (LLM + Whisper — backup)
    groq_api_key: str = ""
    groq_llm_model: str = "llama-3.3-70b-versatile"

    # DynamoDB
    dynamodb_endpoint_url: str | None = None
    events_table: str = "SmartHome_Events"
    state_table: str = "SmartHome_HouseholdState"
    patterns_table: str = "SmartHome_Patterns"
    mood_history_table: str = "SmartHome_MoodHistory"

    # Pattern engine tuning
    analysis_window_days: int = 30
    time_bucket_minutes: int = 30
    min_pattern_occurrences: int = 3
    min_confidence: float = 0.6

    # Anomaly detection
    departure_grace_minutes: int = 60
    duration_anomaly_factor: float = 2.0

    # Service URLs (for inter-service communication)
    mood_service_url: str = "http://localhost:8001"
    behavior_service_url: str = "http://localhost:8002"
    patterns_service_url: str = "http://localhost:8003"
    devices_service_url: str = "http://localhost:8004"
    orchestrator_service_url: str = "http://localhost:8005"

    # App
    app_name: str = "MoodSense AI"
    debug: bool = True

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
