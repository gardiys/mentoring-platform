import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import parse_qsl

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class TelegramInitDataError(ValueError):
    pass


class TelegramInitDataExpiredError(TelegramInitDataError):
    pass


class TelegramWebAppUser(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    first_name: str = Field(min_length=1, max_length=120)
    last_name: str | None = Field(default=None, max_length=120)
    username: str | None = None
    language_code: str | None = None
    is_bot: bool = False


@dataclass(frozen=True)
class ValidatedTelegramInitData:
    user: TelegramWebAppUser
    auth_date: datetime


def validate_telegram_init_data(
    init_data: str,
    *,
    bot_token: str,
    max_age_seconds: int,
    now: datetime | None = None,
) -> ValidatedTelegramInitData:
    if not init_data or len(init_data) > 16_384:
        raise TelegramInitDataError("Telegram initData is empty or too large")

    try:
        pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise TelegramInitDataError("Telegram initData is malformed") from exc

    if len({key for key, _ in pairs}) != len(pairs):
        raise TelegramInitDataError("Telegram initData contains duplicate fields")

    values = dict(pairs)
    received_hash = values.pop("hash", None)
    if received_hash is None:
        raise TelegramInitDataError("Telegram initData hash is missing")

    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(values.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated_hash, received_hash):
        raise TelegramInitDataError("Telegram initData signature is invalid")

    try:
        auth_timestamp = int(values["auth_date"])
        auth_date = datetime.fromtimestamp(auth_timestamp, tz=UTC)
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise TelegramInitDataError("Telegram initData auth_date is invalid") from exc

    current_time = now or datetime.now(UTC)
    age_seconds = (current_time - auth_date).total_seconds()
    if age_seconds < -60 or age_seconds > max_age_seconds:
        raise TelegramInitDataExpiredError("Telegram initData has expired")

    try:
        user = TelegramWebAppUser.model_validate(json.loads(values["user"]))
    except (KeyError, json.JSONDecodeError, ValidationError) as exc:
        raise TelegramInitDataError("Telegram initData user is invalid") from exc
    if user.is_bot:
        raise TelegramInitDataError("Bots cannot authenticate as Mini App users")

    return ValidatedTelegramInitData(user=user, auth_date=auth_date)
