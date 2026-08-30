from __future__ import annotations

from app.users.models import User

HIDDEN_STUDENT_NAME = "Скрытый ученик"


def public_identity_is_hidden(user: User) -> bool:
    return user.public_identity_hidden_at is not None or user.personal_data_erased_at is not None


def public_user_name(user: User) -> str:
    return HIDDEN_STUDENT_NAME if public_identity_is_hidden(user) else user.first_name


def public_telegram_username(user: User) -> str | None:
    return None if public_identity_is_hidden(user) else user.telegram_username
