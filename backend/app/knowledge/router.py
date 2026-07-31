from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser
from app.db.session import get_db_session
from app.knowledge.schemas import (
    KnowledgeEntryDetail,
    KnowledgeSearchResult,
    KnowledgeTopicDetail,
    KnowledgeTopicListItem,
)
from app.knowledge.service import (
    get_public_entry,
    get_public_topic,
    list_public_topics,
    search_public_entries,
)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])
Session = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("/topics", response_model=list[KnowledgeTopicListItem])
async def knowledge_topics(
    session: Session, _current_user: CurrentUser
) -> list[KnowledgeTopicListItem]:
    return await list_public_topics(session)


@router.get("/topics/{topic_slug}", response_model=KnowledgeTopicDetail)
async def knowledge_topic(
    topic_slug: str, session: Session, _current_user: CurrentUser
) -> KnowledgeTopicDetail:
    return await get_public_topic(session, topic_slug)


@router.get("/entries/{entry_slug}", response_model=KnowledgeEntryDetail)
async def knowledge_entry(
    entry_slug: str, session: Session, _current_user: CurrentUser
) -> KnowledgeEntryDetail:
    return await get_public_entry(session, entry_slug)


@router.get("/search", response_model=list[KnowledgeSearchResult])
async def knowledge_search(
    session: Session,
    _current_user: CurrentUser,
    q: Annotated[str, Query(min_length=2, max_length=120)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> list[KnowledgeSearchResult]:
    return await search_public_entries(session, q.strip(), limit)
