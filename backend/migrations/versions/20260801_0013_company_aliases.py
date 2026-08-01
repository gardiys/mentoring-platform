"""Add learned company aliases and phonetic search keys."""

import re
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260801_0013"
down_revision: str | None = "20260801_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

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


def search_key(value: str) -> str:
    return NON_SEARCH_CHARACTER.sub("", value.casefold().replace("ё", "е"))


def transliterate(value: str, *, phonetic: bool) -> str:
    result = "".join(TRANSLITERATION.get(character, character) for character in search_key(value))
    return result.replace("x", "ks") if phonetic else result


def _refresh_company_keys(*, phonetic: bool) -> None:
    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, name FROM companies")).mappings()
    for row in rows:
        connection.execute(
            sa.text(
                "UPDATE companies SET transliterated_name = :transliterated WHERE id = :id"
            ),
            {
                "id": row["id"],
                "transliterated": transliterate(row["name"], phonetic=phonetic),
            },
        )


def upgrade() -> None:
    op.create_table(
        "company_aliases",
        sa.Column("company_id", sa.UUID(), nullable=False),
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
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("normalized_name"),
    )
    op.create_index("ix_company_aliases_company_id", "company_aliases", ["company_id"])
    op.create_index(
        "ix_company_aliases_transliterated_name",
        "company_aliases",
        ["transliterated_name"],
    )
    _refresh_company_keys(phonetic=True)


def downgrade() -> None:
    _refresh_company_keys(phonetic=False)
    op.drop_index("ix_company_aliases_transliterated_name", table_name="company_aliases")
    op.drop_index("ix_company_aliases_company_id", table_name="company_aliases")
    op.drop_table("company_aliases")
