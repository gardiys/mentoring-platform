from __future__ import annotations

import re
from uuid import UUID

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import api_error
from app.interviews.models import Company, CompanyAlias, InterviewProcess

LEGAL_FORM_PATTERN = re.compile(
    r"(?:^|[\s,.;:()\-])(?:"
    r"ИП|ООО|ОАО|ЗАО|ПАО|АО|НКО|АНО|ФГУП|ГУП|МУП|ГБУ|ЧУ|"
    r"LLC|LTD|INC|JSC|PJSC|CORP(?:ORATION)?|COMPANY|CO"
    r")(?:$|[\s,.;:()\-])",
    flags=re.IGNORECASE,
)
NON_SEARCH_CHARACTER = re.compile(r"[^0-9a-zа-я]+", flags=re.IGNORECASE)
SPACE_PATTERN = re.compile(r"\s+")
EDGE_QUOTES = " \t\r\n\"'`«»„“”()[]{}.,;:—–-"

TRANSLITERATION = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "kh",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "shch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}


def normalize_company_name(value: str) -> str:
    name = SPACE_PATTERN.sub(" ", value.replace("\x00", " ")).strip(EDGE_QUOTES)
    previous = None
    while name and name != previous:
        previous = name
        name = LEGAL_FORM_PATTERN.sub(" ", f" {name} ")
        name = SPACE_PATTERN.sub(" ", name).strip(EDGE_QUOTES)
    if not name:
        api_error(422, "invalid_company_name", "Enter a company name without its legal form")
    return name[:240]


def company_search_key(value: str) -> str:
    return NON_SEARCH_CHARACTER.sub("", value.casefold().replace("ё", "е"))


def transliterate_company_name(value: str) -> str:
    transliterated = "".join(
        TRANSLITERATION.get(character, character) for character in company_search_key(value)
    )
    # Common brand spellings should produce the same key in both scripts:
    # Яндекс -> yandeks and Yandex -> yandeks.
    return transliterated.replace("x", "ks")


async def _company_by_search_key(session: AsyncSession, normalized_name: str) -> Company | None:
    company = await session.scalar(
        select(Company).where(Company.normalized_name == normalized_name)
    )
    if company is not None:
        return company
    aliased_company: Company | None = await session.scalar(
        select(Company)
        .join(CompanyAlias, CompanyAlias.company_id == Company.id)
        .where(CompanyAlias.normalized_name == normalized_name)
    )
    return aliased_company


async def get_or_create_company(session: AsyncSession, raw_name: str) -> Company:
    name = normalize_company_name(raw_name)
    normalized_name = company_search_key(name)
    if not normalized_name:
        api_error(422, "invalid_company_name", "Enter a valid company name")
    company = await _company_by_search_key(session, normalized_name)
    if company is not None:
        return company

    company = Company(
        name=name,
        normalized_name=normalized_name,
        transliterated_name=transliterate_company_name(name),
    )
    try:
        async with session.begin_nested():
            session.add(company)
            await session.flush()
    except IntegrityError:
        company = await session.scalar(
            select(Company).where(Company.normalized_name == normalized_name)
        )
        if company is None:
            raise
    return company


async def _merge_companies(session: AsyncSession, target: Company, source: Company) -> None:
    if target.id == source.id:
        return

    source_aliases = list(
        await session.scalars(select(CompanyAlias).where(CompanyAlias.company_id == source.id))
    )
    target_alias_keys = set(
        await session.scalars(
            select(CompanyAlias.normalized_name).where(CompanyAlias.company_id == target.id)
        )
    )
    for alias in source_aliases:
        if (
            alias.normalized_name == target.normalized_name
            or alias.normalized_name in target_alias_keys
        ):
            await session.delete(alias)
        else:
            alias.company_id = target.id
            target_alias_keys.add(alias.normalized_name)

    await session.execute(
        update(InterviewProcess)
        .where(InterviewProcess.company_id == source.id)
        .values(company_id=target.id, company_name=target.name)
    )
    source_name = source.name
    source_normalized_name = source.normalized_name
    source_transliterated_name = source.transliterated_name
    await session.delete(source)
    await session.flush()
    if (
        source_normalized_name != target.normalized_name
        and source_normalized_name not in target_alias_keys
    ):
        session.add(
            CompanyAlias(
                company_id=target.id,
                name=source_name,
                normalized_name=source_normalized_name,
                transliterated_name=source_transliterated_name,
            )
        )
        await session.flush()


async def remember_company_alias(
    session: AsyncSession,
    company: Company,
    raw_alias: str,
    *,
    allow_company_merge: bool = False,
) -> Company:
    alias_name = normalize_company_name(raw_alias)
    alias_key = company_search_key(alias_name)
    if not alias_key or alias_key == company.normalized_name:
        return company

    existing_alias = await session.scalar(
        select(CompanyAlias).where(CompanyAlias.normalized_name == alias_key)
    )
    if existing_alias is not None:
        if existing_alias.company_id != company.id:
            source = await session.get(Company, existing_alias.company_id)
            if source is not None:
                if not allow_company_merge:
                    api_error(
                        409,
                        "company_alias_conflict",
                        "This name already belongs to another company. "
                        "An administrator must review the merge",
                    )
                await _merge_companies(session, company, source)
        return company

    existing_company = await session.scalar(
        select(Company).where(Company.normalized_name == alias_key)
    )
    if existing_company is not None and existing_company.id != company.id:
        if not allow_company_merge:
            api_error(
                409,
                "company_alias_conflict",
                "This name already belongs to another company. "
                "An administrator must review the merge",
            )
        await _merge_companies(session, company, existing_company)
        return company

    alias = CompanyAlias(
        company_id=company.id,
        name=alias_name,
        normalized_name=alias_key,
        transliterated_name=transliterate_company_name(alias_name),
    )
    try:
        async with session.begin_nested():
            session.add(alias)
            await session.flush()
    except IntegrityError:
        existing_alias = await session.scalar(
            select(CompanyAlias).where(CompanyAlias.normalized_name == alias_key)
        )
        if existing_alias is None or existing_alias.company_id != company.id:
            raise
    return company


async def resolve_company(
    session: AsyncSession,
    raw_name: str,
    *,
    company_id: UUID | None = None,
    raw_alias: str | None = None,
    allow_company_merge: bool = False,
) -> Company:
    if company_id is None:
        return await get_or_create_company(session, raw_name)

    company = await session.get(Company, company_id)
    if company is None:
        api_error(422, "invalid_company", "The selected company no longer exists")
    return await remember_company_alias(
        session,
        company,
        raw_alias or raw_name,
        allow_company_merge=allow_company_merge,
    )


def _match_rank(
    query_key: str,
    transliterated_query: str,
    normalized_name: str,
    transliterated_name: str,
) -> int:
    if normalized_name == query_key or transliterated_name == transliterated_query:
        return 0
    if normalized_name.startswith(query_key):
        return 1
    if transliterated_name.startswith(transliterated_query):
        return 2
    if normalized_name.startswith(query_key[:1]) or transliterated_name.startswith(
        transliterated_query[:1]
    ):
        return 3
    return 4


async def suggest_companies(session: AsyncSession, query: str, limit: int) -> list[Company]:
    normalized_query = company_search_key(normalize_company_name(query))
    transliterated_query = transliterate_company_name(normalized_query)
    first = normalized_query[:1]
    transliterated_first = transliterated_query[:1]
    companies = list(
        await session.scalars(
            select(Company).where(
                or_(
                    Company.normalized_name.startswith(first),
                    Company.transliterated_name.startswith(transliterated_first),
                )
            )
        )
    )
    alias_rows = (
        await session.execute(
            select(CompanyAlias, Company)
            .join(Company, Company.id == CompanyAlias.company_id)
            .where(
                or_(
                    CompanyAlias.normalized_name.startswith(first),
                    CompanyAlias.transliterated_name.startswith(transliterated_first),
                )
            )
        )
    ).all()

    ranked: dict[UUID, tuple[int, Company]] = {
        company.id: (
            _match_rank(
                normalized_query,
                transliterated_query,
                company.normalized_name,
                company.transliterated_name,
            ),
            company,
        )
        for company in companies
    }
    for alias, company in alias_rows:
        alias_rank = _match_rank(
            normalized_query,
            transliterated_query,
            alias.normalized_name,
            alias.transliterated_name,
        )
        current = ranked.get(company.id)
        if current is None or alias_rank < current[0]:
            ranked[company.id] = (alias_rank, company)

    return [
        company
        for _, company in sorted(
            ranked.values(), key=lambda item: (item[0], item[1].name.casefold())
        )[:limit]
    ]
