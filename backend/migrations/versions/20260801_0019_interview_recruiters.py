"""Add interview process recruiters and import their Telegram usernames."""

from __future__ import annotations

import csv
import hashlib
import re
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from uuid import UUID, uuid5

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260801_0019"
down_revision: str | None = "20260801_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "legacy_interviews.csv"
DATA_CHECKSUM = "3464795d0b293dc00e0b7dcdc40923c02aa4cf15d8b1de15d2be8c5493ad152f"
DATA_ROW_COUNT = 2499
EXPECTED_FIELDS = {
    "id",
    "created_at",
    "updated_at",
    "author_id",
    "company_id",
    "recruiter_telegram_login",
    "stage",
    "telegram_file_id",
    "video_url",
    "text",
    "type",
    "specialization",
}
IMPORT_NAMESPACE = UUID("b4e13c60-0a0d-4b35-9237-270166e00440")
TELEGRAM_USERNAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")
DESCRIPTION_SEPARATOR = "\n\n---\n\n"


def _read_rows() -> list[dict[str, str]]:
    if hashlib.sha256(DATA_FILE.read_bytes()).hexdigest() != DATA_CHECKSUM:
        raise RuntimeError("Legacy interview import checksum does not match")
    with DATA_FILE.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if set(reader.fieldnames or []) != EXPECTED_FIELDS:
            raise RuntimeError("Legacy interview import has unexpected columns")
        rows = list(reader)
    if len(rows) != DATA_ROW_COUNT:
        raise RuntimeError(f"Expected {DATA_ROW_COUNT} legacy interviews, got {len(rows)}")
    return rows


def _identity(kind: str, legacy_id: str) -> UUID:
    return uuid5(IMPORT_NAMESPACE, f"{kind}:{legacy_id}")


def _recruiter_usernames(value: str) -> set[str]:
    source = value.strip()
    if source.casefold().startswith("https://t.me/"):
        source = source[len("https://t.me/") :].strip("/")
    return {
        username
        for part in re.split(r"[,\n]+", source)
        if TELEGRAM_USERNAME_PATTERN.fullmatch(
            username := part.strip().lstrip("@").casefold()
        )
    }


def _remove_legacy_recruiter(description: str | None, source_value: str) -> str | None:
    if description is None or not source_value.strip():
        return description
    marker = f"Рекрутер: @{source_value.strip().lstrip('@')}"
    parts = [part for part in description.split(DESCRIPTION_SEPARATOR) if part != marker]
    return DESCRIPTION_SEPARATOR.join(parts) or None


def upgrade() -> None:
    op.add_column(
        "interview_processes",
        sa.Column(
            "recruiter_telegram_usernames",
            postgresql.ARRAY(sa.String(32)),
            server_default=sa.text("'{}'::character varying[]"),
            nullable=False,
        ),
    )
    connection = op.get_bind()
    stage_rows = {
        row["id"]: row
        for row in connection.execute(
            sa.text("SELECT id, process_id, description FROM interview_process_stages")
        ).mappings()
    }
    recruiters_by_process: dict[UUID, set[str]] = defaultdict(set)
    description_updates: list[dict[str, object]] = []
    for source_row in _read_rows():
        stage = stage_rows.get(_identity("stage", source_row["id"]))
        if stage is None:
            continue
        recruiters_by_process[stage["process_id"]].update(
            _recruiter_usernames(source_row["recruiter_telegram_login"])
        )
        description = _remove_legacy_recruiter(
            stage["description"], source_row["recruiter_telegram_login"]
        )
        if description != stage["description"]:
            description_updates.append({"stage_id": stage["id"], "description": description})

    if recruiters_by_process:
        connection.execute(
            sa.text(
                """
                UPDATE interview_processes
                SET recruiter_telegram_usernames = :usernames
                WHERE id = :process_id
                """
            ),
            [
                {"process_id": process_id, "usernames": sorted(usernames)}
                for process_id, usernames in recruiters_by_process.items()
                if usernames
            ],
        )
    if description_updates:
        connection.execute(
            sa.text(
                """
                UPDATE interview_process_stages
                SET description = :description
                WHERE id = :stage_id
                """
            ),
            description_updates,
        )


def downgrade() -> None:
    op.drop_column("interview_processes", "recruiter_telegram_usernames")
