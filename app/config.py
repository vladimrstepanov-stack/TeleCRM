"""Конфигурация приложения; реальные секреты читаются только из .env."""

from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Проверяемая конфигурация, одинаковая для локальной и серверной среды."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    telegram_bot_token: SecretStr = Field(alias="TELEGRAM_BOT_TOKEN")
    allowed_telegram_ids: set[int] = Field(alias="ALLOWED_TELEGRAM_IDS")
    admin_telegram_ids: set[int] = Field(default_factory=set, alias="ADMIN_TELEGRAM_IDS")
    database_url: SecretStr = Field(alias="DATABASE_URL")
    aitunnel_base_url: str = Field(alias="AITUNNEL_BASE_URL")
    aitunnel_api_key: SecretStr = Field(alias="AITUNNEL_API_KEY")
    stt_model: str = Field(default="qwen3-asr-flash-2026-02-10", alias="STT_MODEL")
    deepseek_model: str = Field(default="deepseek-chat", alias="DEEPSEEK_MODEL")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @field_validator("allowed_telegram_ids", "admin_telegram_ids", mode="before")
    @classmethod
    def split_ids(cls, value: str | int | set[int]) -> set[int]:
        if isinstance(value, set):
            return value
        if isinstance(value, int):
            return {value}
        return {int(part.strip()) for part in str(value).split(",") if part.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
