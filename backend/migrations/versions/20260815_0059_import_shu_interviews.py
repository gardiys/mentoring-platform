"""Import interviews uploaded through Shu after the initial archive migration.

Revision ID: 20260815_0059
Revises: 20260815_0058
"""

from __future__ import annotations

import csv
import hashlib
import logging
import re
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit
from uuid import UUID, uuid5

import sqlalchemy as sa
from alembic import op

revision: str = "20260815_0059"
down_revision: str | None = "20260815_0058"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
INTERVIEW_FILE = DATA_DIR / "shu_interviews_20260815.csv"
COMPANY_FILE = DATA_DIR / "shu_companies_20260815.csv"
INTERVIEW_CHECKSUM = "1615971c2f94fecb7d1c6e229c9ce822c08cdf4f17da335a3d8e5f1ef094c4bd"
COMPANY_CHECKSUM = "05c36decd9d5a5039887bd96fa625efe404d4a65130547f90289c42ca0843822"
INTERVIEW_FIELDS = {
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
COMPANY_FIELDS = {"id", "created_at", "updated_at", "name", "additional_names"}
IMPORT_NAMESPACE = UUID("b4e13c60-0a0d-4b35-9237-270166e00440")
logger = logging.getLogger("alembic.runtime.migration")
# Only irreversible fingerprints are kept in the image. The full legacy user
# export contains personal data and is intentionally excluded by .dockerignore.
AUTHOR_TELEGRAM_FINGERPRINTS = {
    "51": "9345355039293a60ed2cd45acd289145538344ca22ecbd9018ed7859ff0e9f0b",
    "99": "941f7607886f23231f9648533ce1fdaa74cebdee6107a28f1878727bcda71dc8",
    "176": "6f4d42c67ce45352d1dfb17286950bee0c4c84efa024b734e858e3bcfb48bb06",
    "364": "35e94b7575ee32af5546b6e8ab28c0b2a89c112e9efd9f2b1f59c3441ead92b6",
    "369": "7564758a6fb3db23d3cf134f7543ee504bc4500ecc6db76dbb3ce5daf89ee607",
    "2587": "dedde0d48451d7dd4bd819637b0e396b998ff3a438bb063fa4166aebe58bf0b2",
    "2773": "a546a2ba6986c462206b1383001655fe8cc2e074e218ccccbb7d657f817d38f4",
    "2777": "ac4f13ba45ae95059b4f7ce71dc04447e8f7e1b6f1801413d735da2bd5f2ab47",
    "2782": "f407cb89dad95c8acc5bcd39e94314a43631f86b64a51846691ac57567ef4fa4",
    "3185": "a082861dac56eb61ae7e4aa8975493dad3adbf25364c9c9161d7e80692b0595d",
}
EXTERNAL_MEDIA_PREFIX = "https://s3.firstvds.ru:443/interviews/"
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
TELEGRAM_USERNAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")
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


def _read_rows(path: Path, *, checksum: str, count: int, fields: set[str]) -> list[dict[str, str]]:
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != checksum:
        raise RuntimeError(f"Import checksum does not match for {path.name}")
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if set(reader.fieldnames or []) != fields:
            raise RuntimeError(f"Unexpected columns in {path.name}")
        rows = list(reader)
    if len(rows) != count:
        raise RuntimeError(f"Expected {count} rows in {path.name}, got {len(rows)}")
    return rows


def _identity(kind: str, source_id: str) -> UUID:
    return uuid5(IMPORT_NAMESPACE, f"{kind}:{source_id}")


def _telegram_fingerprint(telegram_id: int | str) -> str:
    return hashlib.sha256(f"shu:{telegram_id}".encode()).hexdigest()


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
        raise RuntimeError("Shu company has an empty name after normalization")
    return name[:240]


def _search_key(value: str) -> str:
    return NON_SEARCH_CHARACTER.sub("", value.casefold().replace("ё", "е"))


def _transliterate(value: str) -> str:
    result = "".join(TRANSLITERATION.get(char, char) for char in _search_key(value))
    return result.replace("x", "ks")


def _recruiters(value: str) -> set[str]:
    source = value.strip()
    if source.casefold().startswith("https://t.me/"):
        source = source[len("https://t.me/") :].strip("/")
    return {
        username
        for part in re.split(r"[,\n]+", source)
        if TELEGRAM_USERNAME_PATTERN.fullmatch(username := part.strip().lstrip("@").casefold())
    }


def _description(row: dict[str, str]) -> str | None:
    parts = [row["text"].strip()]
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
        raise RuntimeError("Shu interview contains media outside the allowed S3 prefix")
    filename = unquote(Path(urlsplit(url).path).name)[:500] or f"interview-{row['id']}"
    content_type = (
        "audio/mpeg"
        if row["type"].strip().casefold() == "audio" or filename.casefold().endswith(".mp3")
        else "video/mp4"
    )
    return f"external:{url}", filename, content_type, 0


def _resolve_users(
    connection: sa.Connection,
    interviews: list[dict[str, str]],
) -> dict[str, UUID]:
    author_ids = {row["author_id"] for row in interviews}
    unknown_authors = author_ids - AUTHOR_TELEGRAM_FINGERPRINTS.keys()
    if unknown_authors:
        raise RuntimeError(f"Unknown Shu interview authors: {sorted(unknown_authors)}")
    existing_by_fingerprint = {
        _telegram_fingerprint(row["telegram_id"]): row["id"]
        for row in connection.execute(
            sa.text("SELECT id, telegram_id FROM users WHERE telegram_id IS NOT NULL")
        ).mappings()
    }
    result: dict[str, UUID] = {}
    for author_id in author_ids:
        user_id = existing_by_fingerprint.get(AUTHOR_TELEGRAM_FINGERPRINTS[author_id])
        if user_id is None:
            candidate = _identity("user", author_id)
            user_id = connection.scalar(
                sa.text("SELECT id FROM users WHERE id = :id"), {"id": candidate}
            )
        if user_id is None:
            logger.warning(
                "Skipping Shu interviews for unresolved legacy author %s; "
                "the deployment image intentionally has no legacy user PII",
                author_id,
            )
            continue
        result[author_id] = user_id
    return result


def _resolve_companies(
    connection: sa.Connection,
    interviews: list[dict[str, str]],
    company_rows: list[dict[str, str]],
) -> dict[str, UUID]:
    source_companies = {row["id"]: row for row in company_rows}
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
    incremental_ids = {
        row["id"]
        for row in _read_rows(
            COMPANY_FILE,
            checksum=COMPANY_CHECKSUM,
            count=7,
            fields=COMPANY_FIELDS,
        )
    }
    result: dict[str, UUID] = {}
    for source_id in {row["company_id"] for row in interviews}:
        source = source_companies.get(source_id)
        if source is None:
            raise RuntimeError(f"Shu company {source_id} was not found in source data")
        name = _clean_company_name(source["name"])
        normalized = _search_key(name)
        company_id = company_by_key.get(normalized)
        if company_id is None:
            candidate = _identity("company", source_id)
            company_id = connection.scalar(
                sa.text("SELECT id FROM companies WHERE id = :id"), {"id": candidate}
            )
        if company_id is None and source_id in incremental_ids:
            company_id = _identity("company", source_id)
            connection.execute(
                sa.text(
                    """
                    INSERT INTO companies
                        (id, name, normalized_name, transliterated_name,
                         created_at, updated_at)
                    VALUES
                        (:id, :name, :normalized_name, :transliterated_name,
                         :created_at, :updated_at)
                    ON CONFLICT (normalized_name) DO NOTHING
                    """
                ),
                {
                    "id": company_id,
                    "name": name,
                    "normalized_name": normalized,
                    "transliterated_name": _transliterate(name),
                    "created_at": _parse_datetime(source["created_at"]),
                    "updated_at": _parse_datetime(source["updated_at"]),
                },
            )
            company_id = connection.scalar(
                sa.text("SELECT id FROM companies WHERE normalized_name = :normalized"),
                {"normalized": normalized},
            )
        if company_id is None:
            raise RuntimeError(f"Platform company for Shu company {source_id} was not found")
        company_by_key[normalized] = company_id
        result[source_id] = company_id
    return result


def upgrade() -> None:
    interviews = _read_rows(
        INTERVIEW_FILE,
        checksum=INTERVIEW_CHECKSUM,
        count=34,
        fields=INTERVIEW_FIELDS,
    )
    incremental_companies = _read_rows(
        COMPANY_FILE,
        checksum=COMPANY_CHECKSUM,
        count=7,
        fields=COMPANY_FIELDS,
    )
    legacy_companies = _read_rows(
        DATA_DIR / "legacy_companies.csv",
        checksum="9d7fe02327bccce9cfad7f9cb8f80769ad44c8facd75c8b562857f319eeba39e",
        count=694,
        fields=COMPANY_FIELDS,
    )
    connection = op.get_bind()
    track_ids = {
        row["slug"]: row["id"]
        for row in connection.execute(
            sa.text("SELECT id, slug FROM learning_tracks WHERE slug IN ('python', 'go')")
        ).mappings()
    }
    if set(track_ids) != {"python", "go"}:
        raise RuntimeError("Python and Go learning tracks are required for Shu import")
    user_ids = _resolve_users(connection, interviews)
    interviews = [row for row in interviews if row["author_id"] in user_ids]
    if not interviews:
        logger.warning(
            "No resolvable Shu authors were found; skipping incremental interview import"
        )
        return
    company_ids = _resolve_companies(
        connection,
        interviews,
        [*legacy_companies, *incremental_companies],
    )
    company_names = {
        row["id"]: row["name"]
        for row in connection.execute(sa.text("SELECT id, name FROM companies")).mappings()
    }

    grouped: dict[tuple[str, UUID], list[dict[str, str]]] = defaultdict(list)
    for row in interviews:
        grouped[(row["author_id"], company_ids[row["company_id"]])].append(row)

    for (author_id, company_id), rows in grouped.items():
        directions = {
            value
            for row in rows
            if (value := row["specialization"].strip().casefold()) in {"python", "go"}
        }
        if len(directions) != 1:
            raise RuntimeError("A Shu interview process must have exactly one direction")
        direction = next(iter(directions))
        process_id = _identity("process", f"{author_id}:{company_id}")
        created_at = min(_parse_datetime(row["created_at"]) for row in rows)
        updated_at = max(_parse_datetime(row["updated_at"]) for row in rows)
        recruiters = sorted(
            {username for row in rows for username in _recruiters(row["recruiter_telegram_login"])}
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO interview_processes
                    (id, user_id, track_id, company_id, company_name,
                     recruiter_telegram_usernames, status, close_reason,
                     closed_at, created_at, updated_at)
                VALUES
                    (:id, :user_id, :track_id, :company_id, :company_name,
                     CAST(:recruiters AS varchar[]),
                     CAST('closed' AS interview_process_status),
                     'Импортировано из архива собеседований Shu',
                     :updated_at, :created_at, :updated_at)
                ON CONFLICT (id) DO NOTHING
                """
            ),
            {
                "id": process_id,
                "user_id": user_ids[author_id],
                "track_id": track_ids[direction],
                "company_id": company_id,
                "company_name": company_names[company_id],
                "recruiters": recruiters,
                "created_at": created_at,
                "updated_at": updated_at,
            },
        )
        connection.execute(
            sa.text(
                """
                UPDATE interview_processes
                SET recruiter_telegram_usernames = ARRAY(
                        SELECT DISTINCT username
                        FROM unnest(
                            COALESCE(recruiter_telegram_usernames, '{}'::varchar[])
                            || CAST(:recruiters AS varchar[])
                        ) AS username
                        ORDER BY username
                    ),
                    updated_at = GREATEST(updated_at, :updated_at),
                    closed_at = CASE
                        WHEN status = CAST('closed' AS interview_process_status)
                        THEN GREATEST(COALESCE(closed_at, :updated_at), :updated_at)
                        ELSE closed_at
                    END
                WHERE id = :id
                """
            ),
            {"id": process_id, "recruiters": recruiters, "updated_at": updated_at},
        )
        for row in rows:
            storage_key, filename, content_type, size = _media(row)
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
                    ON CONFLICT (id) DO NOTHING
                    """
                ),
                {
                    "id": _identity("stage", row["id"]),
                    "process_id": process_id,
                    "stage_type": STAGE_MAP[row["stage"].strip()],
                    "scheduled_at": _parse_datetime(row["created_at"]),
                    "description": _description(row),
                    "media_storage_key": storage_key,
                    "media_filename": filename,
                    "media_content_type": content_type,
                    "media_size": size,
                    "created_at": _parse_datetime(row["created_at"]),
                    "updated_at": _parse_datetime(row["updated_at"]),
                },
            )


def downgrade() -> None:
    interviews = _read_rows(
        INTERVIEW_FILE,
        checksum=INTERVIEW_CHECKSUM,
        count=34,
        fields=INTERVIEW_FIELDS,
    )
    companies = _read_rows(
        COMPANY_FILE,
        checksum=COMPANY_CHECKSUM,
        count=7,
        fields=COMPANY_FIELDS,
    )
    connection = op.get_bind()
    stage_ids = [_identity("stage", row["id"]) for row in interviews]
    process_ids = list(
        connection.scalars(
            sa.text(
                "SELECT DISTINCT process_id FROM interview_process_stages WHERE id IN :ids"
            ).bindparams(sa.bindparam("ids", expanding=True)),
            {"ids": stage_ids},
        )
    )
    connection.execute(
        sa.text("DELETE FROM interview_process_stages WHERE id IN :ids").bindparams(
            sa.bindparam("ids", expanding=True)
        ),
        {"ids": stage_ids},
    )
    if process_ids:
        connection.execute(
            sa.text(
                """
                DELETE FROM interview_processes process
                WHERE process.id IN :ids
                  AND process.close_reason = 'Импортировано из архива собеседований Shu'
                  AND NOT EXISTS (
                      SELECT 1 FROM interview_process_stages stage
                      WHERE stage.process_id = process.id
                  )
                """
            ).bindparams(sa.bindparam("ids", expanding=True)),
            {"ids": process_ids},
        )
    new_company_ids = [_identity("company", row["id"]) for row in companies]
    connection.execute(
        sa.text(
            """
            DELETE FROM companies company
            WHERE company.id IN :ids
              AND NOT EXISTS (
                  SELECT 1 FROM interview_processes process
                  WHERE process.company_id = company.id
              )
            """
        ).bindparams(sa.bindparam("ids", expanding=True)),
        {"ids": new_company_ids},
    )
