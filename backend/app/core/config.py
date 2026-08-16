import json
import re
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_DEVELOPMENT_FRONTEND_URL = "http://localhost:5173"
_DEVELOPMENT_S3_URL = "http://localhost:9000"
_HOSTNAME_PATTERN = re.compile(
    r"\A(?=.{1,253}\Z)"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*\Z",
    re.IGNORECASE,
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    app_debug: bool = False
    dev_auth_enabled: bool = False
    api_max_request_body_bytes: int = Field(
        default=8_388_608,
        ge=1_024,
        le=67_108_864,
    )
    database_url: str = "postgresql+asyncpg://mentoring:mentoring@localhost:5432/mentoring"
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]
    allowed_hosts: Annotated[list[str], NoDecode] = []
    log_level: str = "INFO"
    telegram_bot_token: SecretStr | None = None
    telegram_bot_proxy_url: SecretStr | None = None
    telegram_interview_chat_id: str | None = None
    telegram_group_topic_id: int | None = Field(default=None, gt=0)
    telegram_interview_python_chat_id: str | None = None
    telegram_interview_python_topic_id: int | None = Field(default=None, gt=0)
    telegram_interview_go_chat_id: str | None = None
    telegram_interview_go_topic_id: int | None = Field(default=None, gt=0)
    notification_reminder_timezone: str = "Europe/Moscow"
    notification_reminder_hour: int = Field(default=10, ge=0, le=23)
    telegram_group_call_reminders_enabled: bool = True
    telegram_group_call_reminder_minutes: int = Field(default=30, ge=5, le=1_440)
    telegram_daily_reminders_enabled: bool = True
    telegram_daily_reminder_hour: int = Field(default=20, ge=0, le=23)
    bot_integration_token: SecretStr | None = None
    telegram_init_data_ttl_seconds: int = Field(default=86_400, gt=0, le=604_800)
    telegram_web_client_id: str | None = None
    telegram_web_client_secret: SecretStr | None = None
    telegram_web_redirect_uri: str | None = None
    telegram_oidc_proxy_url: SecretStr | None = None
    web_frontend_url: str = _DEVELOPMENT_FRONTEND_URL
    web_session_secret: SecretStr | None = None
    web_session_ttl_seconds: int = Field(default=2_592_000, ge=3_600, le=31_536_000)
    web_oauth_state_ttl_seconds: int = Field(default=600, ge=300, le=1_800)
    s3_bucket: str = "mentoring-platform"
    s3_region: str = "us-east-1"
    s3_endpoint_url: str | None = _DEVELOPMENT_S3_URL
    s3_public_endpoint_url: str | None = _DEVELOPMENT_S3_URL
    s3_access_key_id: str = "mentoring-minio"
    s3_secret_access_key: SecretStr = SecretStr("mentoring-minio-secret")
    s3_presign_ttl_seconds: int = Field(default=900, ge=60, le=3_600)
    s3_multipart_part_size_bytes: int = Field(
        default=67_108_864,
        ge=5_242_880,
        le=536_870_912,
    )
    s3_multipart_presign_ttl_seconds: int = Field(default=21_600, ge=300, le=86_400)
    s3_multipart_session_ttl_seconds: int = Field(
        default=86_400,
        ge=3_600,
        le=604_800,
    )
    interview_stream_ticket_ttl_seconds: int = Field(default=600, ge=60, le=3_600)
    media_stream_redirect_ttl_seconds: int = Field(default=900, ge=60, le=3_600)
    content_video_max_bytes: int = Field(
        default=5_368_709_120,
        ge=1_048_576,
        le=10_737_418_240,
    )
    content_media_normalization_directory: str = "/var/lib/mentoring/content-media-normalization"
    content_media_normalization_max_concurrency: int = Field(default=1, ge=1, le=2)
    content_media_normalization_min_free_bytes: int = Field(
        default=2_147_483_648,
        ge=0,
        le=53_687_091_200,
    )
    content_media_normalization_max_reserved_bytes: int = Field(
        default=12_884_901_888,
        ge=1_048_576,
        le=107_374_182_400,
    )
    content_media_normalization_output_overhead_bytes: int = Field(
        default=536_870_912,
        ge=16_777_216,
        le=5_368_709_120,
    )
    content_media_normalization_cleanup_age_seconds: int = Field(
        default=86_400,
        ge=3_600,
        le=604_800,
    )
    content_media_normalization_timeout_seconds: int = Field(
        default=14_400,
        ge=300,
        le=43_200,
    )
    content_media_normalization_stale_seconds: int = Field(
        default=18_000,
        ge=600,
        le=86_400,
    )
    content_media_normalization_job_expires_seconds: int = Field(
        default=604_800,
        ge=3_600,
        le=2_592_000,
    )
    content_media_normalization_source_delete_grace_seconds: int = Field(
        default=86_400,
        ge=900,
        le=604_800,
    )
    content_media_normalization_max_duration_seconds: int = Field(
        default=43_200,
        ge=60,
        le=86_400,
    )
    content_media_normalization_probe_timeout_seconds: float = Field(
        default=120,
        ge=5,
        le=600,
    )
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
    openai_embedding_model: str = "text-embedding-3-small"
    openai_embedding_dimensions: int = Field(default=256, ge=1, le=3_072)
    openai_proxy_url: SecretStr | None = None
    openai_timeout_seconds: float = Field(default=120, ge=10, le=600)
    # ARQ owns observable retries and persists every attempt; avoid nested SDK retries.
    openai_max_retries: int = Field(default=0, ge=0, le=5)
    openai_max_concurrency: int = Field(default=4, ge=1, le=32)
    openai_job_timeout_seconds: int = Field(default=3_600, ge=60, le=14_400)
    openai_extraction_max_output_tokens: int = Field(default=8_000, ge=256, le=32_000)
    openai_review_max_output_tokens: int = Field(default=4_000, ge=256, le=16_000)
    openai_summary_max_output_tokens: int = Field(default=4_000, ge=256, le=16_000)
    openai_light_input_price_per_million_usd: Decimal = Field(default=Decimal("0"), ge=0)
    openai_light_output_price_per_million_usd: Decimal = Field(default=Decimal("0"), ge=0)
    openai_analysis_input_price_per_million_usd: Decimal = Field(default=Decimal("0"), ge=0)
    openai_analysis_output_price_per_million_usd: Decimal = Field(default=Decimal("0"), ge=0)
    interview_ai_extraction_confidence_threshold: float = Field(default=0.65, ge=0, le=1)
    interview_card_frequent_min_occurrences: int = Field(default=3, ge=1, le=10_000)
    interview_ai_enabled: bool = True
    interview_ai_daily_limit: int = Field(default=1, ge=1, le=100)
    interview_ai_max_active_per_user: int = Field(default=1, ge=1, le=10)
    interview_ai_global_active_limit: int = Field(default=50, ge=1, le=10_000)
    interview_ai_quota_timezone: str = "Europe/Moscow"
    tochka_client_id: str | None = None
    tochka_jwt_token: SecretStr | None = None
    tochka_api_base_url: str = "https://enter.tochka.com/uapi"
    tochka_proxy_url: SecretStr | None = None
    tochka_public_key: SecretStr | None = None
    tochka_customer_code: str | None = None
    tochka_redirect_url: str | None = None
    tochka_fail_redirect_url: str | None = None
    tochka_payment_modes_raw: str = Field(
        default="sbp,card",
        validation_alias="TOCHKA_PAYMENT_MODES",
    )
    tochka_payment_purpose: str = "Оплата услуг по программе менторства"
    tochka_receipt_tax_system_code: str = "osn"
    tochka_receipt_vat_type: str = "none"
    tochka_receipt_payment_method: str = "full_payment"
    tochka_receipt_payment_object: str = "service"
    tochka_receipt_item_name: str = "Информационно-консультационные услуги"
    tochka_receipt_measure: str = "шт."
    tochka_supplier_name: str = ""
    tochka_supplier_phone: str = ""
    tochka_supplier_tax_code: str = ""
    tochka_request_timeout_seconds: float = Field(default=20, ge=5, le=120)

    @field_validator("cors_origins", "allowed_hosts", mode="before")
    @classmethod
    def parse_string_list(cls, value: object) -> object:
        if isinstance(value, str):
            if value.startswith("["):
                return json.loads(value)
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, values: list[str]) -> list[str]:
        origins: list[str] = []
        for value in values:
            if cls._contains_unsafe_whitespace(value):
                raise ValueError("CORS_ORIGINS contains whitespace or control characters")
            try:
                parsed = urlsplit(value)
                _ = parsed.port
            except ValueError as error:
                raise ValueError("CORS_ORIGINS contains an invalid origin") from error
            if (
                value == "*"
                or parsed.scheme.lower() not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError(
                    "CORS_ORIGINS must contain exact http(s) origins without paths or credentials"
                )
            origins.append(f"{parsed.scheme.lower()}://{parsed.netloc.lower()}")
        return origins

    @field_validator("allowed_hosts")
    @classmethod
    def validate_allowed_hosts(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            host = value.strip().lower()
            if host == "*" and value == "*":
                normalized.append(host)
                continue
            hostname = host.removeprefix("*.")
            if (
                not host
                or cls._contains_unsafe_whitespace(value)
                or ("*" in host and host != "*" and not host.startswith("*."))
                or "*" in hostname
                or _HOSTNAME_PATTERN.fullmatch(hostname) is None
            ):
                raise ValueError(
                    "ALLOWED_HOSTS must contain DNS host names or '*.domain' wildcards"
                )
            normalized.append(host)
        return normalized

    @field_validator(
        "web_frontend_url",
        "telegram_web_redirect_uri",
        "s3_endpoint_url",
        "s3_public_endpoint_url",
        "nexara_base_url",
        "tochka_api_base_url",
        "tochka_redirect_url",
        "tochka_fail_redirect_url",
    )
    @classmethod
    def validate_http_url(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None:
            return None
        field_name = info.field_name.upper() if info.field_name is not None else "URL"
        if cls._contains_unsafe_whitespace(value):
            raise ValueError(f"{field_name} contains whitespace or control characters")
        try:
            parsed = urlsplit(value)
            _ = parsed.port
        except ValueError as error:
            raise ValueError(f"{field_name} is not a valid URL") from error
        if (
            parsed.scheme.lower() not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            raise ValueError(
                f"{field_name} must be an http(s) URL without credentials or fragment"
            )
        if info.field_name == "web_frontend_url" and (
            parsed.path not in {"", "/"} or parsed.query
        ):
            raise ValueError("WEB_FRONTEND_URL must be an exact http(s) origin")
        if info.field_name in {
            "s3_endpoint_url",
            "s3_public_endpoint_url",
            "nexara_base_url",
            "tochka_api_base_url",
        } and parsed.query:
            raise ValueError(f"{field_name} must not contain a query string")
        return value

    @field_validator(
        "telegram_bot_token",
        "telegram_bot_proxy_url",
        "bot_integration_token",
        "telegram_web_client_secret",
        "telegram_oidc_proxy_url",
        "web_session_secret",
        "nexara_api_key",
        "openai_api_key",
        "openai_proxy_url",
        "tochka_jwt_token",
        "tochka_proxy_url",
        "tochka_public_key",
        mode="before",
    )
    @classmethod
    def empty_secret_is_none(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("s3_endpoint_url", "s3_public_endpoint_url", mode="before")
    @classmethod
    def empty_s3_endpoint_is_none(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator(
        "telegram_group_topic_id",
        "telegram_interview_python_topic_id",
        "telegram_interview_go_topic_id",
        mode="before",
    )
    @classmethod
    def empty_telegram_topic_is_none(cls, value: object) -> object:
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

    @field_validator("notification_reminder_timezone")
    @classmethod
    def validate_notification_reminder_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise ValueError(
                "NOTIFICATION_REMINDER_TIMEZONE must be a valid IANA timezone"
            ) from error
        return value

    @field_validator("interview_legacy_transcode_directory")
    @classmethod
    def validate_legacy_transcode_directory(cls, value: str) -> str:
        if not value.strip() or not Path(value).is_absolute():
            raise ValueError("INTERVIEW_LEGACY_TRANSCODE_DIRECTORY must be an absolute path")
        return value

    @field_validator("content_media_normalization_directory")
    @classmethod
    def validate_content_media_normalization_directory(cls, value: str) -> str:
        if not value.strip() or not Path(value).is_absolute():
            raise ValueError("CONTENT_MEDIA_NORMALIZATION_DIRECTORY must be an absolute path")
        return value

    @model_validator(mode="after")
    def validate_intelligence_job_lifetimes(self) -> "Settings":
        if self.app_env == "production":
            if self.app_debug:
                raise ValueError("APP_DEBUG must be false in production")
            if self.dev_auth_enabled:
                raise ValueError("DEV_AUTH_ENABLED must be false in production")
            if "*" in self.allowed_hosts:
                raise ValueError("ALLOWED_HOSTS must not contain '*' in production")
            self._validate_production_placeholders()
            self._validate_production_urls()
        if self.s3_multipart_presign_ttl_seconds > self.s3_multipart_session_ttl_seconds:
            raise ValueError(
                "S3_MULTIPART_PRESIGN_TTL_SECONDS must not exceed S3_MULTIPART_SESSION_TTL_SECONDS"
            )
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
        if self.interview_legacy_transcode_max_reserved_bytes < self.interview_audio_max_bytes * 2:
            raise ValueError(
                "INTERVIEW_LEGACY_TRANSCODE_MAX_RESERVED_BYTES must be at least twice "
                "INTERVIEW_AUDIO_MAX_BYTES"
            )
        required_normalization_bytes = (
            self.content_video_max_bytes * 2
            + self.content_media_normalization_output_overhead_bytes
        )
        if self.content_media_normalization_max_reserved_bytes < required_normalization_bytes:
            raise ValueError(
                "CONTENT_MEDIA_NORMALIZATION_MAX_RESERVED_BYTES must cover two copies of "
                "CONTENT_VIDEO_MAX_BYTES plus CONTENT_MEDIA_NORMALIZATION_OUTPUT_OVERHEAD_BYTES"
            )
        if (
            self.content_media_normalization_cleanup_age_seconds
            <= self.content_media_normalization_timeout_seconds
        ):
            raise ValueError(
                "CONTENT_MEDIA_NORMALIZATION_CLEANUP_AGE_SECONDS must exceed "
                "CONTENT_MEDIA_NORMALIZATION_TIMEOUT_SECONDS"
            )
        if (
            self.content_media_normalization_stale_seconds
            <= self.content_media_normalization_timeout_seconds
        ):
            raise ValueError(
                "CONTENT_MEDIA_NORMALIZATION_STALE_SECONDS must exceed "
                "CONTENT_MEDIA_NORMALIZATION_TIMEOUT_SECONDS"
            )
        return self

    def _validate_production_urls(self) -> None:
        web_runtime_configured = (
            self.web_frontend_url != _DEVELOPMENT_FRONTEND_URL
            or self.cors_origins != [_DEVELOPMENT_FRONTEND_URL]
            or self.web_session_secret is not None
            or self.telegram_web_client_id is not None
            or self.telegram_web_client_secret is not None
            or self.telegram_web_redirect_uri is not None
            or self.tochka_client_id is not None
            or self.tochka_jwt_token is not None
        )
        if web_runtime_configured:
            self._require_https("WEB_FRONTEND_URL", self.web_frontend_url)
            for origin in self.cors_origins:
                self._require_https("CORS_ORIGINS", origin)

        for name, value in (
            ("TELEGRAM_WEB_REDIRECT_URI", self.telegram_web_redirect_uri),
            ("NEXARA_BASE_URL", self.nexara_base_url),
            ("TOCHKA_API_BASE_URL", self.tochka_api_base_url),
            ("TOCHKA_REDIRECT_URL", self.tochka_redirect_url),
            ("TOCHKA_FAIL_REDIRECT_URL", self.tochka_fail_redirect_url),
        ):
            if value is not None:
                self._require_https(name, value)

        configured_s3 = (
            self.s3_endpoint_url not in {None, _DEVELOPMENT_S3_URL}
            or self.s3_public_endpoint_url not in {None, _DEVELOPMENT_S3_URL}
            or self.s3_bucket != "mentoring-platform"
            or self.s3_access_key_id != "mentoring-minio"
        )
        if configured_s3:
            for name, value in (
                ("S3_ENDPOINT_URL", self.s3_endpoint_url),
                ("S3_PUBLIC_ENDPOINT_URL", self.s3_public_endpoint_url),
            ):
                if value is not None:
                    self._require_https(name, value)

    @staticmethod
    def _require_https(name: str, value: str) -> None:
        if urlsplit(value).scheme.lower() != "https":
            raise ValueError(f"{name} must use HTTPS in production")

    @staticmethod
    def _contains_unsafe_whitespace(value: str) -> bool:
        return any(
            ord(character) < 32 or ord(character) == 127 or character.isspace()
            for character in value
        )

    def _validate_production_placeholders(self) -> None:
        secret_values = {
            "TELEGRAM_BOT_TOKEN": self.telegram_bot_token,
            "TELEGRAM_BOT_PROXY_URL": self.telegram_bot_proxy_url,
            "BOT_INTEGRATION_TOKEN": self.bot_integration_token,
            "TELEGRAM_WEB_CLIENT_SECRET": self.telegram_web_client_secret,
            "TELEGRAM_OIDC_PROXY_URL": self.telegram_oidc_proxy_url,
            "WEB_SESSION_SECRET": self.web_session_secret,
            "NEXARA_API_KEY": self.nexara_api_key,
            "OPENAI_API_KEY": self.openai_api_key,
            "OPENAI_PROXY_URL": self.openai_proxy_url,
            "TOCHKA_JWT_TOKEN": self.tochka_jwt_token,
            "TOCHKA_PROXY_URL": self.tochka_proxy_url,
            "TOCHKA_PUBLIC_KEY": self.tochka_public_key,
        }
        for name, secret in secret_values.items():
            if secret is not None and self._is_placeholder(secret.get_secret_value()):
                raise ValueError(f"{name} contains a placeholder value")

        if (
            self.database_url
            == "postgresql+asyncpg://mentoring:mentoring@localhost:5432/mentoring"
            or self._is_placeholder(self.database_url)
        ):
            raise ValueError("DATABASE_URL contains development or placeholder credentials")

        configured_s3 = (
            self.s3_endpoint_url not in {None, _DEVELOPMENT_S3_URL}
            or self.s3_public_endpoint_url not in {None, _DEVELOPMENT_S3_URL}
            or self.s3_bucket != "mentoring-platform"
            or self.s3_access_key_id != "mentoring-minio"
        )
        if configured_s3 and (
            self._is_placeholder(self.s3_access_key_id)
            or self._is_placeholder(self.s3_secret_access_key.get_secret_value())
            or self.s3_secret_access_key.get_secret_value() == "mentoring-minio-secret"
        ):
            raise ValueError("Production S3 credentials contain a placeholder value")

    @staticmethod
    def _is_placeholder(value: str) -> bool:
        normalized = value.strip().upper().replace("-", "_")
        return any(
            marker in normalized
            for marker in (
                "REPLACE_WITH",
                "CHANGE_ME",
                "CHANGEME",
                "YOUR_SECRET",
                "PLACEHOLDER",
            )
        )

    @field_validator(
        "telegram_web_client_id",
        "telegram_web_redirect_uri",
        "nexara_model",
        "openai_analysis_model",
        "openai_extraction_model",
        "openai_light_review_model",
        "tochka_client_id",
        "tochka_customer_code",
        "tochka_redirect_url",
        "tochka_fail_redirect_url",
        mode="before",
    )
    @classmethod
    def empty_string_is_none(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("openai_embedding_model", mode="before")
    @classmethod
    def empty_embedding_model_uses_default(cls, value: object) -> object:
        return "text-embedding-3-small" if value == "" else value

    @property
    def tochka_payment_modes(self) -> list[str]:
        modes = [item.strip() for item in self.tochka_payment_modes_raw.split(",") if item.strip()]
        return modes or ["sbp", "card"]

    @property
    def trusted_hosts(self) -> list[str]:
        hosts = {"127.0.0.1", "backend", "localhost", "test"}
        hosts.update(self.allowed_hosts)
        for url in (self.web_frontend_url, self.telegram_web_redirect_uri, *self.cors_origins):
            if not url or url == "*":
                continue
            hostname = urlsplit(url).hostname
            if hostname:
                hosts.add(hostname.lower())
        return sorted(hosts)

    @property
    def csrf_trusted_origins(self) -> frozenset[str]:
        origins: set[str] = set()
        for value in (self.web_frontend_url, *self.cors_origins):
            parsed = urlsplit(value)
            if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
                continue
            origins.add(f"{parsed.scheme.lower()}://{parsed.netloc.lower()}")
        return frozenset(origins)


@lru_cache
def get_settings() -> Settings:
    return Settings()
