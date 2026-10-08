"""Configuration settings for Lakshya application using Pydantic Settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or defaults."""

    google_client_id: str = ""
    google_client_secret: str = ""
    gemini_api_key: str = ""
    database_url: str = "sqlite:///./lakshya.db"
    max_syllabus_chars: int = 50_000
    max_daily_study_minutes: int = 240

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
