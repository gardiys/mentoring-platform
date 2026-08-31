from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser
from app.db.session import get_db_session
from app.interviews.schemas import (
    InterviewCardStudy,
    InterviewDeckListItem,
    InterviewQuestionLearnedFilter,
    InterviewQuestionLearnedMutation,
    InterviewQuestionLearnedResult,
    InterviewQuestionSort,
    InterviewQuestionSortDirection,
    InterviewQuestionTablePage,
    InterviewReviewMutation,
    InterviewReviewResult,
    InterviewStudySession,
    InterviewTopicOption,
    InterviewTopicSelectionMutation,
)
from app.interviews.service import (
    get_interview_topics,
    get_study_session,
    list_interview_decks,
    list_interview_questions,
    review_interview_card,
    search_interview_cards,
    set_interview_question_learned,
    update_interview_topics,
)

router = APIRouter(prefix="/interviews", tags=["interviews"])
Session = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("/decks", response_model=list[InterviewDeckListItem])
async def interview_decks(
    session: Session, current_user: CurrentUser
) -> list[InterviewDeckListItem]:
    return await list_interview_decks(session, current_user)


@router.get("/decks/{deck_slug}/session", response_model=InterviewStudySession)
async def interview_study_session(
    deck_slug: str,
    session: Session,
    current_user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    frequent_only: bool = False,
) -> InterviewStudySession:
    return await get_study_session(
        session,
        current_user,
        deck_slug,
        limit,
        frequent_only=frequent_only,
    )


@router.get(
    "/decks/{deck_slug}/cards/search",
    response_model=list[InterviewCardStudy],
)
async def interview_card_search(
    deck_slug: str,
    session: Session,
    current_user: CurrentUser,
    query: Annotated[str, Query(min_length=2, max_length=200)],
    limit: Annotated[int, Query(ge=1, le=50)] = 30,
    frequent_only: bool = False,
) -> list[InterviewCardStudy]:
    return await search_interview_cards(
        session,
        current_user,
        deck_slug,
        query,
        limit,
        frequent_only=frequent_only,
    )


@router.get(
    "/decks/{deck_slug}/questions",
    response_model=InterviewQuestionTablePage,
)
async def interview_question_table(
    deck_slug: str,
    session: Session,
    current_user: CurrentUser,
    category: Annotated[list[str] | None, Query(max_length=240)] = None,
    frequent_only: bool = False,
    learned: InterviewQuestionLearnedFilter = InterviewQuestionLearnedFilter.ALL,
    sort: InterviewQuestionSort = InterviewQuestionSort.FREQUENCY,
    order: InterviewQuestionSortDirection = InterviewQuestionSortDirection.DESC,
    query: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> InterviewQuestionTablePage:
    return await list_interview_questions(
        session,
        current_user,
        deck_slug,
        categories=category,
        frequent_only=frequent_only,
        learned=learned,
        sort=sort,
        order=order,
        query=query,
        limit=limit,
        offset=offset,
    )


@router.get("/decks/{deck_slug}/topics", response_model=list[InterviewTopicOption])
async def interview_topics(
    deck_slug: str, session: Session, current_user: CurrentUser
) -> list[InterviewTopicOption]:
    return await get_interview_topics(session, current_user, deck_slug)


@router.put("/decks/{deck_slug}/topics", response_model=list[InterviewTopicOption])
async def interview_update_topics(
    deck_slug: str,
    payload: InterviewTopicSelectionMutation,
    session: Session,
    current_user: CurrentUser,
) -> list[InterviewTopicOption]:
    return await update_interview_topics(session, current_user, deck_slug, payload.categories)


@router.post("/cards/{card_id}/reviews", response_model=InterviewReviewResult)
async def interview_card_review(
    card_id: UUID,
    payload: InterviewReviewMutation,
    session: Session,
    current_user: CurrentUser,
) -> InterviewReviewResult:
    return await review_interview_card(session, current_user, card_id, payload.rating)


@router.put(
    "/cards/{card_id}/learned",
    response_model=InterviewQuestionLearnedResult,
)
async def interview_card_learned(
    card_id: UUID,
    payload: InterviewQuestionLearnedMutation,
    session: Session,
    current_user: CurrentUser,
) -> InterviewQuestionLearnedResult:
    return await set_interview_question_learned(
        session,
        current_user,
        card_id,
        learned=payload.learned,
    )
