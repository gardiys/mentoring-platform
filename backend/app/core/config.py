import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, field_validator, model_validator
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
    interview_media_max_duration_seconds: int = Field(default=14_400, ge=60, le=43_200)
    interview_staging_directory: str = "/tmp/interview-staging"
    interview_staging_max_concurrency: int = Field(default=2, ge=1, le=8)
    interview_staging_min_free_bytes: int = Field(default=2_147_483_648, ge=0, le=21_474_836_480)
    interview_staging_max_reserved_bytes: int = Field(
        default=4_294_967_296, ge=1_048_576, le=53_687_091_200
    )
    interview_staging_cleanup_age_seconds: int = Field(default=86_400, ge=3_600, le=604_800)
    interview_media_probe_timeout_seconds: float = Field(default=20, ge=1, le=120)
    interview_legacy_transcode_directory: str = "/tmp/interview-legacy-transcode"
    interview_legacy_transcode_max_concurrency: int = Field(default=1, ge=1, le=4)
    interview_legacy_transcode_min_free_bytes: int = Field(
        default=2_147_483_648, ge=0, le=21_474_836_480
    )
    interview_legacy_transcode_max_reserved_bytes: int = Field(
        default=1_073_741_824, ge=1_048_576, le=10_737_418_240
    )
    interview_legacy_transcode_cleanup_age_seconds: int = Field(
        default=86_400, ge=3_600, le=604_800
    )
    interview_legacy_transcode_timeout_seconds: int = Field(default=600, ge=30, le=1_800)
    interview_max_upload_mb: int = Field(default=2_048, ge=1, le=5_120)
    redis_url: str = "redis://localhost:6379/0"
    intelligence_job_expires_seconds: int = Field(default=604_800, ge=3_600, le=2_592_000)
    transcription_provider: str = "fake"
    transcription_max_concurrency: int = Field(default=4, ge=1, le=32)
    transcription_job_timeout_seconds: int = Field(default=3_600, ge=60, le=7_200)
    transcription_poll_deadline_seconds: int = Field(default=21_600, ge=300, le=604_800)
    nexara_api_key: SecretStr | None = None
    nexara_base_url: str = "https://api.nexara.ru/v1"
    nexara_model: str = "whisper-1"
    nexara_timeout_seconds: float = Field(default=600, ge=10, le=1_800)
    # ARQ persists and jitters retries; keep provider SDK retries disabled.
    nexara_max_retries: int = Field(default=0, ge=0, le=5)
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
    openai_job_timeout_seconds: int = Field(default=3_600, ge=60, le=14_400)
    openai_extraction_max_output_tokens: int = Field(default=8_000, ge=256, le=32_000)
    openai_review_max_output_tokens: int = Field(default=4_000, ge=256, le=16_000)
    openai_summary_max_output_tokens: int = Field(default=4_000, ge=256, le=16_000)
    interview_ai_extraction_confidence_threshold: float = Field(default=0.65, ge=0, le=1)
    interview_ai_enabled: bool = True
    interview_ai_daily_limit: int = Field(default=3, ge=1, le=100)
    interview_ai_max_active_per_user: int = Field(default=1, ge=1, le=10)
    interview_ai_global_active_limit: int = Field(default=50, ge=1, le=10_000)
    interview_ai_quota_timezone: str = "Europe/Moscow"

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

    @field_validator("interview_ai_quota_timezone")
    @classmethod
    def validate_interview_ai_quota_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise ValueError("INTERVIEW_AI_QUOTA_TIMEZONE must be a valid IANA timezone") from error
        return value

    @field_validator("interview_legacy_transcode_directory")
    @classmethod
    def validate_legacy_transcode_directory(cls, value: str) -> str:
        if not value.strip() or not Path(value).is_absolute():
            raise ValueError("INTERVIEW_LEGACY_TRANSCODE_DIRECTORY must be an absolute path")
        return value

    @model_validator(mode="after")
    def validate_intelligence_job_lifetimes(self) -> "Settings":
        if self.transcription_poll_deadline_seconds > self.intelligence_job_expires_seconds:
            raise ValueError(
                "TRANSCRIPTION_POLL_DEADLINE_SECONDS must not exceed "
                "INTELLIGENCE_JOB_EXPIRES_SECONDS"
            )
        if (
            self.interview_legacy_transcode_cleanup_age_seconds
            <= self.interview_legacy_transcode_timeout_seconds
        ):
            raise ValueError(
                "INTERVIEW_LEGACY_TRANSCODE_CLEANUP_AGE_SECONDS must exceed "
                "INTERVIEW_LEGACY_TRANSCODE_TIMEOUT_SECONDS"
            )
        if (
            self.interview_legacy_transcode_max_reserved_bytes
            < self.interview_audio_max_bytes * 2
        ):
            raise ValueError(
                "INTERVIEW_LEGACY_TRANSCODE_MAX_RESERVED_BYTES must be at least twice "
                "INTERVIEW_AUDIO_MAX_BYTES"
            )
        return self

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
