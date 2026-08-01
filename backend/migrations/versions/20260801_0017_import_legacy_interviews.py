"""Import legacy users, companies, and interview history."""

from __future__ import annotations

import csv
import hashlib
import re
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit
from uuid import UUID, uuid5

import sqlalchemy as sa
from alembic import op

revision: str = "20260801_0017"
down_revision: str | None = "20260801_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
USER_FILE = DATA_DIR / "legacy_users.csv"
COMPANY_FILE = DATA_DIR / "legacy_companies.csv"
INTERVIEW_FILE = DATA_DIR / "legacy_interviews.csv"
DATA_FILES = {
    USER_FILE: (
        "4a9627d3d88cdc261fd59ece53aadfaf74d9f56bca841cc3fd49383671aa8773",
        238,
        {
            "id",
            "telegram_username",
            "role",
            "telegram_id",
            "chat_id",
            "name",
            "surname",
            "daily_notifications",
            "specialization",
            "extra_specialization",
        },
    ),
    COMPANY_FILE: (
        "9d7fe02327bccce9cfad7f9cb8f80769ad44c8facd75c8b562857f319eeba39e",
        694,
        {"id", "created_at", "updated_at", "name", "additional_names"},
    ),
    INTERVIEW_FILE: (
        "3464795d0b293dc00e0b7dcdc40923c02aa4cf15d8b1de15d2be8c5493ad152f",
        2499,
        {
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
        },
    ),
}

IMPORT_NAMESPACE = UUID("b4e13c60-0a0d-4b35-9237-270166e00440")
EXTERNAL_MEDIA_PREFIX = "https://s3.firstvds.ru:443/interviews/"
ROLE_MAP = {
    "Менти": "student",
    "Выпускник": "student",
    "Ментор": "mentor",
    "CEO": "admin",
}
STAGE_MAP = {
    "screaning": "screening",
    "tech": "technical_interview",
    "system": "system_design",
    "final": "final_interview",
    "audio": "other",
}
LEGAL_FORM_PATTERN = re.compile(
    r"(?:^|[\s,.;:()\-])(?:"
    r"ИП|ООО|ОАО|ЗАО|ПАО|АО|НКО|АНО|ФГУП|ГУП|МУП|ГБУ|ЧУ|"
    r"LLC|LTD|INC|JSC|PJSC|CORP(?:ORATION)?|COMPANY|CO"
    r")(?:$|[\s,.;:()\-])",
    flags=re.IGNORECASE,
)
NON_SEARCH_CHARACTER = re.compile(r"[^0-9a-zа-я]+", flags=re.IGNORECASE)
EDGE_QUOTES = " \t\r\n\"'`«»„“”()[]{}.,;:—–-"
TRANSLITERATION = dict(
    zip(
        "абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
        (
            "a",
            "b",
            "v",
            "g",
            "d",
            "e",
            "e",
            "zh",
            "z",
            "i",
            "y",
            "k",
            "l",
            "m",
            "n",
            "o",
            "p",
            "r",
            "s",
            "t",
            "u",
            "f",
            "kh",
            "ts",
            "ch",
            "sh",
            "shch",
            "",
            "y",
            "",
            "e",
            "yu",
            "ya",
        ),
        strict=True,
    )
)


def _read_rows(path: Path) -> list[dict[str, str]]:
    expected_hash, expected_count, expected_fields = DATA_FILES[path]
    raw_data = path.read_bytes()
    if hashlib.sha256(raw_data).hexdigest() != expected_hash:
        raise RuntimeError(f"Legacy import checksum does not match for {path.name}")
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if set(reader.fieldnames or []) != expected_fields:
            raise RuntimeError(f"Legacy import has unexpected columns in {path.name}")
        rows = list(reader)
    if len(rows) != expected_count:
        raise RuntimeError(f"Expected {expected_count} rows in {path.name}, got {len(rows)}")
    return rows


def _identity(kind: str, legacy_id: str) -> UUID:
    return uuid5(IMPORT_NAMESPACE, f"{kind}:{legacy_id}")


def _parse_datetime(value: str) -> datetime:
    normalized = re.sub(r"\s+([+-]\d{4})$", r"\1", value.strip())
    return datetime.fromisoformat(normalized)


def _clean_company_name(value: str) -> str:
    name = re.sub(r"\s+", " ", value.replace("\x00", " ")).strip(EDGE_QUOTES)
    previous = None
    while name and name != previous:
        previous = name
        name = LEGAL_FORM_PATTERN.sub(" ", f" {name} ")
        name = re.sub(r"\s+", " ", name).strip(EDGE_QUOTES)
    if not name:
        raise RuntimeError("Legacy company has an empty name after normalization")
    return name[:240]


def _search_key(value: str) -> str:
    return NON_SEARCH_CHARACTER.sub("", value.casefold().replace("ё", "е"))


def _transliterate(value: str) -> str:
    result = "".join(TRANSLITERATION.get(character, character) for character in _search_key(value))
    return result.replace("x", "ks")


def _company_aliases(value: str) -> list[str]:
    raw = value.strip()
    if not raw or raw == "{}":
        return []
    if not raw.startswith("{") or not raw.endswith("}"):
        raise RuntimeError("Legacy company aliases have an unexpected format")
    return [part.strip() for part in raw[1:-1].split(",") if part.strip()]


def _directions(*values: str) -> set[str]:
    return {
        normalized
        for value in values
        if (normalized := value.strip().casefold()) in {"python", "go"}
    }


def _stage_description(row: dict[str, str]) -> str | None:
    parts = [row["text"].strip()]
    recruiter = row["recruiter_telegram_login"].strip().lstrip("@")
    if recruiter:
        parts.append(f"Рекрутер: @{recruiter}")
    if row["telegram_file_id"].strip() and not row["video_url"].strip():
        parts.append(
            "Архивная запись сохранена в Telegram; технический идентификатор: "
            f"{row['telegram_file_id'].strip()}"
        )
    description = "\n\n---\n\n".join(part for part in parts if part)
    return description or None


def _media(row: dict[str, str]) -> tuple[str | None, str | None, str | None, int | None]:
    url = row["video_url"].strip()
    if not url:
        return None, None, None, None
    if not url.startswith(EXTERNAL_MEDIA_PREFIX):
        raise RuntimeError("Legacy interview contains a media URL outside the allowed S3 prefix")
    filename = unquote(Path(urlsplit(url).path).name)[:500] or f"interview-{row['id']}"
    media_type = row["type"].strip().casefold()
    content_type = (
        "audio/mpeg" if media_type == "audio" or filename.endswith(".mp3") else "video/mp4"
    )
    return f"external:{url}", filename, content_type, 0


def _import_companies(connection: sa.Connection, rows: list[dict[str, str]]) -> dict[str, UUID]:
    company_by_key: dict[str, UUID] = {
        row["normalized_name"]: row["id"]
        for row in connection.execute(
            sa.text("SELECT id, normalized_name FROM companies")
        ).mappings()
    }
    company_by_key.update(
        {
            row["normalized_name"]: row["company_id"]
            for row in connection.execute(
                sa.text("SELECT company_id, normalized_name FROM company_aliases")
            ).mappings()
        }
    )
    legacy_company_ids: dict[str, UUID] = {}

    for row in rows:
        name = _clean_company_name(row["name"])
        normalized = _search_key(name)
        company_id = company_by_key.get(normalized)
        if company_id is None:
            company_id = _identity("company", row["id"])
            connection.execute(
                sa.text(
                    """
                    INSERT INTO companies
                        (id, name, normalized_name, transliterated_name,
                         created_at, updated_at)
                    VALUES
                        (:id, :name, :normalized_name, :transliterated_name,
                         :created_at, :updated_at)
                    """
                ),
                {
                    "id": company_id,
                    "name": name,
                    "normalized_name": normalized,
                    "transliterated_name": _transliterate(name),
                    "created_at": _parse_datetime(row["created_at"]),
                    "updated_at": _parse_datetime(row["updated_at"]),
                },
            )
            company_by_key[normalized] = company_id
        legacy_company_ids[row["id"]] = company_id

        for alias_name in _company_aliases(row["additional_names"]):
            alias = _clean_company_name(alias_name)
            alias_key = _search_key(alias)
            if not alias_key or alias_key in company_by_key:
                continue
            connection.execute(
                sa.text(
                    """
                    INSERT INTO company_aliases
                        (id, company_id, name, normalized_name,
                         transliterated_name, created_at, updated_at)
                    VALUES
                        (:id, :company_id, :name, :normalized_name,
                         :transliterated_name, :created_at, :updated_at)
                    """
                ),
                {
                    "id": _identity("company-alias", f"{row['id']}:{alias_key}"),
                    "company_id": company_id,
                    "name": alias,
                    "normalized_name": alias_key,
                    "transliterated_name": _transliterate(alias),
                    "created_at": _parse_datetime(row["created_at"]),
                    "updated_at": _parse_datetime(row["updated_at"]),
                },
            )
            company_by_key[alias_key] = company_id

    return legacy_company_ids


def _import_users(
    connection: sa.Connection,
    user_rows: list[dict[str, str]],
    interview_rows: list[dict[str, str]],
    track_ids: dict[str, UUID],
) -> dict[str, UUID]:
    existing_users = {
        str(row["telegram_id"]): row["id"]
        for row in connection.execute(
            sa.text("SELECT id, telegram_id FROM users WHERE telegram_id IS NOT NULL")
        ).mappings()
    }
    interviews_by_author: dict[str, list[dict[str, str]]] = defaultdict(list)
    for interview in interview_rows:
        interviews_by_author[interview["author_id"]].append(interview)

    legacy_user_ids: dict[str, UUID] = {}
    for row in user_rows:
        source_role = row["role"].strip()
        if source_role == "Гость":
            continue
        role = ROLE_MAP.get(source_role)
        if role is None:
            raise RuntimeError(f"Unknown legacy user role: {source_role}")

        telegram_value = row["telegram_id"].strip()
        telegram_id = int(telegram_value) if telegram_value else None
        user_id = existing_users.get(telegram_value) if telegram_value else None
        inserted = user_id is None
        if user_id is None:
            user_id = _identity("user", row["id"])
            connection.execute(
                sa.text(
                    """
                    INSERT INTO users
                        (id, telegram_id, first_name, last_name, role,
                         onboarding_completed_at, is_active)
                    VALUES
                        (:id, :telegram_id, :first_name, :last_name,
                         CAST(:role AS user_role),
                         CASE WHEN :role = 'student' THEN now() ELSE NULL END,
                         true)
                    """
                ),
                {
                    "id": user_id,
                    "telegram_id": telegram_id,
                    "first_name": row["name"].strip()[:120],
                    "last_name": row["surname"].strip()[:120] or None,
                    "role": role,
                },
            )
            if telegram_value:
                existing_users[telegram_value] = user_id
        legacy_user_ids[row["id"]] = user_id

        if not inserted or role != "student":
            continue
        directions = _directions(row["specialization"], row["extra_specialization"])
        for interview in interviews_by_author[row["id"]]:
            directions.update(_directions(interview["specialization"]))
        if not directions:
            directions = {"python"}
        connection.execute(
            sa.text(
                """
                INSERT INTO learning_track_enrollments (user_id, track_id)
                VALUES (:user_id, :track_id)
                ON CONFLICT DO NOTHING
                """
            ),
            [
                {"user_id": user_id, "track_id": track_ids[direction]}
                for direction in sorted(directions)
            ],
        )

    return legacy_user_ids


def _import_interviews(
    connection: sa.Connection,
    rows: list[dict[str, str]],
    user_rows: list[dict[str, str]],
    legacy_user_ids: dict[str, UUID],
    legacy_company_ids: dict[str, UUID],
    track_ids: dict[str, UUID],
) -> None:
    source_users = {row["id"]: row for row in user_rows}
    grouped: dict[tuple[str, UUID], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        if row["author_id"] not in legacy_user_ids:
            if source_users[row["author_id"]]["role"].strip() != "Гость":
                raise RuntimeError("Legacy interview author was not imported")
            continue
        if row["company_id"] not in legacy_company_ids:
            raise RuntimeError("Legacy interview company was not imported")
        grouped[(row["author_id"], legacy_company_ids[row["company_id"]])].append(row)

    process_payloads = []
    stage_payloads = []
    canonical_company_names = {
        row["id"]: row["name"]
        for row in connection.execute(sa.text("SELECT id, name FROM companies")).mappings()
    }
    for (author_id, company_id), process_rows in grouped.items():
        explicit_directions = set()
        for row in process_rows:
            explicit_directions.update(_directions(row["specialization"]))
        if len(explicit_directions) > 1:
            raise RuntimeError("One legacy user/company process has mixed directions")
        if explicit_directions:
            direction = next(iter(explicit_directions))
        else:
            user = source_users[author_id]
            user_directions = _directions(user["specialization"], user["extra_specialization"])
            direction = next(iter(user_directions), "python")

        process_id = _identity("process", f"{author_id}:{company_id}")
        created_at = min(_parse_datetime(row["created_at"]) for row in process_rows)
        updated_at = max(_parse_datetime(row["updated_at"]) for row in process_rows)
        process_payloads.append(
            {
                "id": process_id,
                "user_id": legacy_user_ids[author_id],
                "track_id": track_ids[direction],
                "company_id": company_id,
                "company_name": canonical_company_names[company_id],
                "closed_at": updated_at,
                "created_at": created_at,
                "updated_at": updated_at,
            }
        )
        for row in process_rows:
            storage_key, filename, content_type, size = _media(row)
            stage_payloads.append(
                {
                    "id": _identity("stage", row["id"]),
                    "process_id": process_id,
                    "stage_type": STAGE_MAP[row["stage"].strip()],
                    "scheduled_at": _parse_datetime(row["created_at"]),
                    "description": _stage_description(row),
                    "media_storage_key": storage_key,
                    "media_filename": filename,
                    "media_content_type": content_type,
                    "media_size": size,
                    "created_at": _parse_datetime(row["created_at"]),
                    "updated_at": _parse_datetime(row["updated_at"]),
                }
            )

    connection.execute(
        sa.text(
            """
            INSERT INTO interview_processes
                (id, user_id, track_id, company_id, company_name, status,
                 close_reason, closed_at, created_at, updated_at)
            VALUES
                (:id, :user_id, :track_id, :company_id, :company_name,
                 CAST('closed' AS interview_process_status),
                 'Импортировано из архива собеседований', :closed_at,
                 :created_at, :updated_at)
            """
        ),
        process_payloads,
    )
    connection.execute(
        sa.text(
            """
            INSERT INTO interview_process_stages
                (id, process_id, stage_type, scheduled_at, description,
                 media_storage_key, media_filename, media_content_type,
                 media_size, created_at, updated_at)
            VALUES
                (:id, :process_id, CAST(:stage_type AS interview_stage_type),
                 :scheduled_at, :description, :media_storage_key,
                 :media_filename, :media_content_type, :media_size,
                 :created_at, :updated_at)
            """
        ),
        stage_payloads,
    )


def upgrade() -> None:
    user_rows = _read_rows(USER_FILE)
    company_rows = _read_rows(COMPANY_FILE)
    interview_rows = _read_rows(INTERVIEW_FILE)
    connection = op.get_bind()
    track_ids = {
        row["slug"]: row["id"]
        for row in connection.execute(
            sa.text("SELECT id, slug FROM learning_tracks WHERE slug IN ('python', 'go')")
        ).mappings()
    }
    if set(track_ids) != {"python", "go"}:
        raise RuntimeError("Python and Go learning tracks are required for the legacy import")

    legacy_company_ids = _import_companies(connection, company_rows)
    legacy_user_ids = _import_users(connection, user_rows, interview_rows, track_ids)
    _import_interviews(
        connection,
        interview_rows,
        user_rows,
        legacy_user_ids,
        legacy_company_ids,
        track_ids,
    )


def downgrade() -> None:
    user_rows = _read_rows(USER_FILE)
    company_rows = _read_rows(COMPANY_FILE)
    interview_rows = _read_rows(INTERVIEW_FILE)
    connection = op.get_bind()

    stage_ids = [_identity("stage", row["id"]) for row in interview_rows]
    company_by_key: dict[str, UUID] = {
        row["normalized_name"]: row["id"]
        for row in connection.execute(
            sa.text("SELECT id, normalized_name FROM companies")
        ).mappings()
    }
    company_by_key.update(
        {
            row["normalized_name"]: row["company_id"]
            for row in connection.execute(
                sa.text("SELECT company_id, normalized_name FROM company_aliases")
            ).mappings()
        }
    )
    legacy_company_ids = {
        row["id"]: company_by_key[_search_key(_clean_company_name(row["name"]))]
        for row in company_rows
    }
    process_ids = [
        _identity("process", f"{author_id}:{company_id}")
        for author_id, company_id in {
            (row["author_id"], legacy_company_ids[row["company_id"]]) for row in interview_rows
        }
    ]
    alias_ids = [
        _identity(
            "company-alias",
            f"{row['id']}:{_search_key(_clean_company_name(alias))}",
        )
        for row in company_rows
        for alias in _company_aliases(row["additional_names"])
    ]
    company_ids = [_identity("company", row["id"]) for row in company_rows]
    user_ids = [_identity("user", row["id"]) for row in user_rows if row["role"].strip() != "Гость"]

    for table, ids in (
        ("interview_process_stages", stage_ids),
        ("interview_processes", process_ids),
        ("company_aliases", alias_ids),
    ):
        connection.execute(
            sa.text(f"DELETE FROM {table} WHERE id IN :ids").bindparams(
                sa.bindparam("ids", expanding=True)
            ),
            {"ids": ids},
        )
    connection.execute(
        sa.text(
            """
            DELETE FROM companies
            WHERE id IN :ids
              AND NOT EXISTS (
                  SELECT 1 FROM interview_processes
                  WHERE interview_processes.company_id = companies.id
              )
            """
        ).bindparams(sa.bindparam("ids", expanding=True)),
        {"ids": company_ids},
    )
    connection.execute(
        sa.text("DELETE FROM users WHERE id IN :ids").bindparams(
            sa.bindparam("ids", expanding=True)
        ),
        {"ids": user_ids},
    )
