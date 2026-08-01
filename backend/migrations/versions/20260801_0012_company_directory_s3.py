"""Add normalized company directory and attach interview processes."""

import re
from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "20260801_0012"
down_revision: str | None = "20260801_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEGAL_FORM_PATTERN = re.compile(
    r"(?:^|[\s,.;:()\-])(?:ИП|ООО|ОАО|ЗАО|ПАО|АО|НКО|АНО|ФГУП|ГУП|МУП|ГБУ|ЧУ|"
    r"LLC|LTD|INC|JSC|PJSC|CORP(?:ORATION)?|COMPANY|CO)(?:$|[\s,.;:()\-])",
    flags=re.IGNORECASE,
)
NON_SEARCH_CHARACTER = re.compile(r"[^0-9a-zа-я]+", flags=re.IGNORECASE)
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
EDGE_QUOTES = " \t\r\n\"'`«»„“”()[]{}.,;:—–-"


def clean_name(value: str) -> str:
    name = re.sub(r"\s+", " ", value.replace("\x00", " ")).strip(EDGE_QUOTES)
    previous = None
    while name and name != previous:
        previous = name
        name = LEGAL_FORM_PATTERN.sub(" ", f" {name} ")
        name = re.sub(r"\s+", " ", name).strip(EDGE_QUOTES)
    return (name or value.strip())[:240]


def search_key(value: str) -> str:
    return NON_SEARCH_CHARACTER.sub("", value.casefold().replace("ё", "е"))


def transliterate(value: str) -> str:
    return "".join(TRANSLITERATION.get(character, character) for character in search_key(value))


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("normalized_name", sa.String(length=240), nullable=False),
        sa.Column("transliterated_name", sa.String(length=500), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("normalized_name"),
    )
    op.create_index("ix_companies_transliterated_name", "companies", ["transliterated_name"])
    op.add_column("interview_processes", sa.Column("company_id", sa.UUID(), nullable=True))

    connection = op.get_bind()
    rows = list(
        connection.execute(sa.text("SELECT id, company_name FROM interview_processes")).mappings()
    )
    companies: dict[str, tuple[object, str]] = {}
    for row in rows:
        name = clean_name(row["company_name"])
        normalized = search_key(name)
        company = companies.get(normalized)
        if company is None:
            company = (uuid4(), name)
            companies[normalized] = company
            connection.execute(
                sa.text(
                    "INSERT INTO companies "
                    "(id, name, normalized_name, transliterated_name) "
                    "VALUES (:id, :name, :normalized, :transliterated)"
                ),
                {
                    "id": company[0],
                    "name": name,
                    "normalized": normalized,
                    "transliterated": transliterate(name),
                },
            )
        connection.execute(
            sa.text(
                "UPDATE interview_processes "
                "SET company_id = :company_id, company_name = :name "
                "WHERE id = :process_id"
            ),
            {
                "company_id": company[0],
                "name": company[1],
                "process_id": row["id"],
            },
        )

    op.alter_column("interview_processes", "company_id", nullable=False)
    op.create_foreign_key(
        "fk_interview_processes_company_id_companies",
        "interview_processes",
        "companies",
        ["company_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_interview_processes_company_id", "interview_processes", ["company_id"])


def downgrade() -> None:
    op.drop_index("ix_interview_processes_company_id", table_name="interview_processes")
    op.drop_constraint(
        "fk_interview_processes_company_id_companies",
        "interview_processes",
        type_="foreignkey",
    )
    op.drop_column("interview_processes", "company_id")
    op.drop_index("ix_companies_transliterated_name", table_name="companies")
    op.drop_table("companies")
