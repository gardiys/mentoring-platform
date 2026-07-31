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

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            if value.startswith("["):
                return json.loads(value)
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("telegram_bot_token", "bot_integration_token", mode="before")
    @classmethod
    def empty_secret_is_none(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("bot_integration_token")
    @classmethod
    def validate_bot_integration_token(
        cls, value: SecretStr | None
    ) -> SecretStr | None:
        if value is not None and len(value.get_secret_value()) < 32:
            raise ValueError("BOT_INTEGRATION_TOKEN must contain at least 32 characters")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
