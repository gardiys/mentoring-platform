from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import AdminUser
from app.db.session import get_db_session
from app.interviews.schemas import (
    AdminInterviewCardMutation,
    AdminInterviewCardPage,
    AdminInterviewCardRead,
    AdminInterviewDeckMutation,
    AdminInterviewDeckRead,
    AdminInterviewDeckSettingsMutation,
    AdminInterviewDeckSummary,
)
from app.interviews.service import (
    create_admin_interview_card,
    create_admin_interview_deck,
    get_admin_interview_card,
    get_admin_interview_deck,
    get_admin_interview_deck_summary,
    list_admin_interview_cards,
    list_admin_interview_deck_summaries,
    list_admin_interview_decks,
    update_admin_interview_card,
    update_admin_interview_deck,
    update_admin_interview_deck_settings,
)

router = APIRouter(prefix="/admin/interviews/decks", tags=["admin-interviews"])
Session = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("", response_model=list[AdminInterviewDeckRead])
async def admin_interview_decks(
    session: Session, _admin: AdminUser
) -> list[AdminInterviewDeckRead]:
    return await list_admin_interview_decks(session)


@router.post("", response_model=AdminInterviewDeckRead, status_code=status.HTTP_201_CREATED)
async def admin_create_interview_deck(
    payload: AdminInterviewDeckMutation,
    session: Session,
    _admin: AdminUser,
) -> AdminInterviewDeckRead:
    return await create_admin_interview_deck(session, payload)


@router.get("/summaries", response_model=list[AdminInterviewDeckSummary])
async def admin_interview_deck_summaries(
    session: Session, _admin: AdminUser
) -> list[AdminInterviewDeckSummary]:
    return await list_admin_interview_deck_summaries(session)


@router.get("/{deck_id}/overview", response_model=AdminInterviewDeckSummary)
async def admin_interview_deck_overview(
    deck_id: UUID, session: Session, _admin: AdminUser
) -> AdminInterviewDeckSummary:
    return await get_admin_interview_deck_summary(session, deck_id)


@router.patch("/{deck_id}/overview", response_model=AdminInterviewDeckSummary)
async def admin_update_interview_deck_overview(
    deck_id: UUID,
    payload: AdminInterviewDeckSettingsMutation,
    session: Session,
    _admin: AdminUser,
) -> AdminInterviewDeckSummary:
    return await update_admin_interview_deck_settings(session, deck_id, payload)


@router.get("/{deck_id}/cards", response_model=AdminInterviewCardPage)
async def admin_interview_cards(
    deck_id: UUID,
    session: Session,
    _admin: AdminUser,
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> AdminInterviewCardPage:
    return await list_admin_interview_cards(
        session, deck_id, query=q, limit=limit, offset=offset
    )


@router.post(
    "/{deck_id}/cards",
    response_model=AdminInterviewCardRead,
    status_code=status.HTTP_201_CREATED,
)
async def admin_create_interview_card(
    deck_id: UUID,
    payload: AdminInterviewCardMutation,
    session: Session,
    _admin: AdminUser,
) -> AdminInterviewCardRead:
    return await create_admin_interview_card(session, deck_id, payload)


@router.get("/{deck_id}/cards/{card_id}", response_model=AdminInterviewCardRead)
async def admin_interview_card(
    deck_id: UUID, card_id: UUID, session: Session, _admin: AdminUser
) -> AdminInterviewCardRead:
    return await get_admin_interview_card(session, deck_id, card_id)


@router.put("/{deck_id}/cards/{card_id}", response_model=AdminInterviewCardRead)
async def admin_update_interview_card(
    deck_id: UUID,
    card_id: UUID,
    payload: AdminInterviewCardMutation,
    session: Session,
    _admin: AdminUser,
) -> AdminInterviewCardRead:
    return await update_admin_interview_card(session, deck_id, card_id, payload)


@router.get("/{deck_id}", response_model=AdminInterviewDeckRead)
async def admin_interview_deck(
    deck_id: UUID, session: Session, _admin: AdminUser
) -> AdminInterviewDeckRead:
    return await get_admin_interview_deck(session, deck_id)


@router.put("/{deck_id}", response_model=AdminInterviewDeckRead)
async def admin_update_interview_deck(
    deck_id: UUID,
    payload: AdminInterviewDeckMutation,
    session: Session,
    _admin: AdminUser,
) -> AdminInterviewDeckRead:
    return await update_admin_interview_deck(session, deck_id, payload)
