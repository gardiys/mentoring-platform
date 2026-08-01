import json
from functools import lru_cache
from typing import Annotated

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    app_env: str = "development"
    app_debug: bool = True
    database_url: str = "postgresql+asyncpg://mentoring:mentoring@localhost:5432/mentoring"
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]
    log_level: str = "INFO"
    telegram_bot_token: SecretStr | None = None
    bot_integration_token: SecretStr | None = None
    telegram_init_data_ttl_seconds: int = Field(default=86_400, gt=0, le=604_800)
    telegram_web_client_id: str | None = None
    telegram_web_client_secret: SecretStr | None = None
    telegram_web_redirect_uri: str | None = None
    web_frontend_url: str = "http://localhost:5173"
    web_session_secret: SecretStr | None = None
    web_session_ttl_seconds: int = Field(default=2_592_000, ge=3_600, le=31_536_000)
    web_oauth_state_ttl_seconds: int = Field(default=600, ge=300, le=1_800)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            if value.startswith("["):
                return json.loads(value)
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator(
        "telegram_bot_token",
        "bot_integration_token",
        "telegram_web_client_secret",
        "web_session_secret",
        mode="before",
    )
    @classmethod
    def empty_secret_is_none(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("bot_integration_token")
    @classmethod
    def validate_bot_integration_token(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and len(value.get_secret_value()) < 32:
            raise ValueError("BOT_INTEGRATION_TOKEN must contain at least 32 characters")
        return value

    @field_validator("web_session_secret")
    @classmethod
    def validate_web_session_secret(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and len(value.get_secret_value()) < 32:
            raise ValueError("WEB_SESSION_SECRET must contain at least 32 characters")
        return value

    @field_validator("telegram_web_client_id", "telegram_web_redirect_uri", mode="before")
    @classmethod
    def empty_string_is_none(cls, value: object) -> object:
        return None if value == "" else value


@lru_cache
def get_settings() -> Settings:
    return Settings()
