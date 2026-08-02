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
    telegram_oidc_proxy_url: SecretStr | None = None
    web_frontend_url: str = "http://localhost:5173"
    web_session_secret: SecretStr | None = None
    web_session_ttl_seconds: int = Field(default=2_592_000, ge=3_600, le=31_536_000)
    web_oauth_state_ttl_seconds: int = Field(default=600, ge=300, le=1_800)
    s3_bucket: str = "mentoring-platform"
    s3_region: str = "us-east-1"
    s3_endpoint_url: str | None = "http://localhost:9000"
    s3_public_endpoint_url: str | None = "http://localhost:9000"
    s3_access_key_id: str = "mentoring-minio"
    s3_secret_access_key: SecretStr = SecretStr("mentoring-minio-secret")
    s3_presign_ttl_seconds: int = Field(default=900, ge=60, le=3_600)
    interview_stream_ticket_ttl_seconds: int = Field(default=600, ge=60, le=3_600)
    interview_video_max_bytes: int = Field(default=2_147_483_648, ge=1_048_576, le=5_368_709_120)
    interview_audio_max_bytes: int = Field(default=524_288_000, ge=1_048_576, le=2_147_483_648)
    interview_offer_max_bytes: int = Field(default=20_971_520, ge=1_048_576, le=104_857_600)
    interview_attachment_max_bytes: int = Field(default=52_428_800, ge=1_048_576, le=524_288_000)
    interview_max_upload_mb: int = Field(default=2_048, ge=1, le=5_120)
    redis_url: str = "redis://localhost:6379/0"
    transcription_provider: str = "fake"
    transcription_max_concurrency: int = Field(default=4, ge=1, le=32)
    nexara_api_key: SecretStr | None = None
    nexara_base_url: str = "https://api.nexara.ru/v1"
    nexara_model: str = "whisper-1"
    nexara_timeout_seconds: float = Field(default=600, ge=10, le=1_800)
    nexara_max_retries: int = Field(default=2, ge=0, le=5)
    interview_ai_provider: str = "fake"
    openai_api_key: SecretStr | None = None
    openai_analysis_model: str | None = None
    openai_extraction_model: str | None = None
    openai_light_review_model: str | None = None
    openai_proxy_url: SecretStr | None = None
    openai_timeout_seconds: float = Field(default=120, ge=10, le=600)
    # ARQ owns observable retries and persists every attempt; avoid nested SDK retries.
    openai_max_retries: int = Field(default=0, ge=0, le=5)
    openai_max_concurrency: int = Field(default=4, ge=1, le=32)
    interview_ai_extraction_confidence_threshold: float = Field(default=0.65, ge=0, le=1)

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
        "telegram_oidc_proxy_url",
        "web_session_secret",
        "nexara_api_key",
        "openai_api_key",
        "openai_proxy_url",
        mode="before",
    )
    @classmethod
    def empty_secret_is_none(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("s3_endpoint_url", "s3_public_endpoint_url", mode="before")
    @classmethod
    def empty_s3_endpoint_is_none(cls, value: object) -> object:
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

    @field_validator(
        "telegram_web_client_id",
        "telegram_web_redirect_uri",
        "nexara_model",
        "openai_analysis_model",
        "openai_extraction_model",
        "openai_light_review_model",
        mode="before",
    )
    @classmethod
    def empty_string_is_none(cls, value: object) -> object:
        return None if value == "" else value


@lru_cache
def get_settings() -> Settings:
    return Settings()
