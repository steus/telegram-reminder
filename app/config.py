"""Конфигурация приложения (pydantic-settings).

Все поля читаются из переменных окружения / .env (см. .env.example, §12 ТЗ).
На этапе 0 обязательны TELEGRAM_BOT_TOKEN, DATABASE_URL, DEFAULT_TIMEZONE.
Остальные поля опциональны, чтобы каркас не падал до их настройки.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Telegram / БД / общее (обязательно на этапе 0) ---
    telegram_bot_token: str = Field(..., alias="TELEGRAM_BOT_TOKEN")
    database_url: str = Field(
        "sqlite+aiosqlite:///./data/app.db", alias="DATABASE_URL"
    )
    default_timezone: str = Field("Europe/Tallinn", alias="DEFAULT_TIMEZONE")

    # --- LLM (появляется на этапе 4) ---
    llm_provider: str | None = Field(None, alias="LLM_PROVIDER")
    llm_model: str | None = Field(None, alias="LLM_MODEL")
    llm_api_key: str | None = Field(None, alias="LLM_API_KEY")
    llm_fallback_provider: str | None = Field(None, alias="LLM_FALLBACK_PROVIDER")
    llm_fallback_model: str | None = Field(None, alias="LLM_FALLBACK_MODEL")
    llm_fallback_api_key: str | None = Field(None, alias="LLM_FALLBACK_API_KEY")

    # --- Plaud (этап 4) ---
    plaud_api_key: str | None = Field(None, alias="PLAUD_API_KEY")
    plaud_api_base_url: str | None = Field(None, alias="PLAUD_API_BASE_URL")

    # --- Голос / whisper (появляется на этапе 5) ---
    whisper_mode: str = Field("local", alias="WHISPER_MODE")
    whisper_cpp_path: str | None = Field(None, alias="WHISPER_CPP_PATH")
    whisper_model_path: str | None = Field(None, alias="WHISPER_MODEL_PATH")
    whisper_max_voice_duration: int = Field(120, alias="WHISPER_MAX_VOICE_DURATION")
    whisper_timeout: float = Field(120.0, alias="WHISPER_TIMEOUT")
    openai_api_key: str | None = Field(None, alias="OPENAI_API_KEY")

    # --- Google Sheets (появляется на этапе 6) ---
    google_service_account_json: str | None = Field(
        None, alias="GOOGLE_SERVICE_ACCOUNT_JSON"
    )


settings = Settings()
