from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import api_error
from app.interviews.card_frequency import (
    card_frequency_mode,
    effective_card_frequency,
    effective_frequent_predicate,
    frequent_occurrence_threshold,
    refresh_card_frequency,
)
from app.interviews.models import (
    InterviewCard,
    InterviewCardFrequency,
    InterviewCardFrequencyMode,
    InterviewCardProgress,
    InterviewDeck,
    InterviewReviewRating,
    InterviewTopicSelection,
)
from app.interviews.schemas import (
    AdminInterviewCardMutation,
    AdminInterviewCardPage,
    AdminInterviewCardRead,
    AdminInterviewCardSummary,
    AdminInterviewDeckMutation,
    AdminInterviewDeckRead,
    AdminInterviewDeckSettingsMutation,
    AdminInterviewDeckSummary,
    InterviewCardStudy,
    InterviewDeckListItem,
    InterviewDeckStats,
    InterviewQuestionLearnedFilter,
    InterviewQuestionLearnedResult,
    InterviewQuestionSort,
    InterviewQuestionSortDirection,
    InterviewQuestionTableItem,
    InterviewQuestionTablePage,
    InterviewReviewResult,
    InterviewStudySession,
    InterviewTopicOption,
)
from app.tracks.access import accessible_track_ids, has_track_access
from app.tracks.models import LearningTrack
from app.users.models import User


async def _has_track_access(session: AsyncSession, user: User, track_id: UUID) -> bool:
    return await has_track_access(session, user, track_id)


async def _public_deck_model(
    session: AsyncSession, slug: str, user: User
) -> tuple[InterviewDeck, LearningTrack]:
    row = (
        await session.execute(
            select(InterviewDeck, LearningTrack)
            .join(LearningTrack, LearningTrack.id == InterviewDeck.track_id)
            .where(
                InterviewDeck.slug == slug,
                InterviewDeck.is_published.is_(True),
                LearningTrack.is_published.is_(True),
            )
        )
    ).one_or_none()
    if row is None:
        api_error(404, "interview_deck_not_found", "Interview deck was not found")
    deck, track = row
    if not await _has_track_access(session, user, deck.track_id):
        api_error(403, "interview_deck_access_denied", "Track access is required")
    return deck, track


async def _selected_categories(session: AsyncSession, user_id: UUID, deck_id: UUID) -> set[str]:
    return set(
        await session.scalars(
            select(InterviewTopicSelection.category).where(
                InterviewTopicSelection.user_id == user_id,
                InterviewTopicSelection.deck_id == deck_id,
            )
        )
    )


async def _deck_stats(
    session: AsyncSession,
    user_id: UUID,
    deck_id: UUID,
    *,
    frequent_only: bool = False,
) -> InterviewDeckStats:
    card_filters = [
        InterviewCard.deck_id == deck_id,
        InterviewCard.is_published.is_(True),
    ]
    if frequent_only:
        card_filters.append(effective_frequent_predicate())
    available = await session.scalar(select(func.count(InterviewCard.id)).where(*card_filters)) or 0
    total_categories = (
        await session.scalar(
            select(func.count(func.distinct(InterviewCard.category))).where(*card_filters)
        )
        or 0
    )
    selected_categories = await _selected_categories(session, user_id, deck_id)
    if not selected_categories:
        return InterviewDeckStats(
            available_cards=available,
            selected_categories=0,
            total_categories=total_categories,
            total_cards=0,
            learned_cards=0,
            remaining_cards=0,
            due_cards=0,
            progress_percent=0,
        )
    total = (
        await session.scalar(
            select(func.count(InterviewCard.id)).where(
                *card_filters,
                InterviewCard.category.in_(selected_categories),
            )
        )
        or 0
    )
    learned = (
        await session.scalar(
            select(func.count(InterviewCardProgress.card_id))
            .join(InterviewCard, InterviewCard.id == InterviewCardProgress.card_id)
            .where(
                *card_filters,
                InterviewCard.category.in_(selected_categories),
                InterviewCardProgress.user_id == user_id,
                InterviewCardProgress.first_learned_at.is_not(None),
            )
        )
        or 0
    )
    due = (
        await session.scalar(
            select(func.count(InterviewCardProgress.card_id))
            .join(InterviewCard, InterviewCard.id == InterviewCardProgress.card_id)
            .where(
                *card_filters,
                InterviewCard.category.in_(selected_categories),
                InterviewCardProgress.user_id == user_id,
                InterviewCardProgress.due_at <= datetime.now(UTC),
            )
        )
        or 0
    )
    return InterviewDeckStats(
        available_cards=available,
        selected_categories=len(selected_categories),
        total_categories=total_categories,
        total_cards=total,
        learned_cards=learned,
        remaining_cards=total - learned,
        due_cards=due,
        progress_percent=round(learned / total * 100) if total else 0,
    )


async def _deck_list_item(
    session: AsyncSession,
    user_id: UUID,
    deck: InterviewDeck,
    track: LearningTrack,
    *,
    frequent_only: bool = False,
) -> InterviewDeckListItem:
    return InterviewDeckListItem(
        id=deck.id,
        slug=deck.slug,
        title=deck.title,
        description=deck.description,
        track_id=track.id,
        track_slug=track.slug,
        track_title=track.title,
        stats=await _deck_stats(
            session,
            user_id,
            deck.id,
            frequent_only=frequent_only,
        ),
    )


async def list_interview_decks(session: AsyncSession, user: User) -> list[InterviewDeckListItem]:
    statement = (
        select(InterviewDeck, LearningTrack)
        .join(LearningTrack, LearningTrack.id == InterviewDeck.track_id)
        .where(
            InterviewDeck.is_published.is_(True),
            LearningTrack.is_published.is_(True),
        )
        .order_by(LearningTrack.position, InterviewDeck.position, InterviewDeck.title)
    )
    track_ids = await accessible_track_ids(session, user)
    if track_ids is not None:
        statement = statement.where(InterviewDeck.track_id.in_(track_ids))
    rows = (await session.execute(statement)).all()
    return [await _deck_list_item(session, user.id, deck, track) for deck, track in rows]


async def get_study_session(
    session: AsyncSession,
    user: User,
    deck_slug: str,
    limit: int,
    *,
    frequent_only: bool = False,
) -> InterviewStudySession:
    deck, track = await _public_deck_model(session, deck_slug, user)
    now = datetime.now(UTC)
    selected_categories = await _selected_categories(session, user.id, deck.id)
    if not selected_categories:
        return InterviewStudySession(
            deck=await _deck_list_item(
                session,
                user.id,
                deck,
                track,
                frequent_only=frequent_only,
            ),
            cards=[],
        )
    card_filters = [
        InterviewCard.deck_id == deck.id,
        InterviewCard.is_published.is_(True),
        InterviewCard.category.in_(selected_categories),
    ]
    if frequent_only:
        card_filters.append(effective_frequent_predicate())
    rows = list(
        (
            await session.execute(
                select(InterviewCard, InterviewCardProgress)
                .outerjoin(
                    InterviewCardProgress,
                    (InterviewCardProgress.card_id == InterviewCard.id)
                    & (InterviewCardProgress.user_id == user.id),
                )
                .where(
                    *card_filters,
                    or_(
                        InterviewCardProgress.card_id.is_(None),
                        InterviewCardProgress.due_at <= now,
                    ),
                )
            )
        ).all()
    )
    frequency_order = {
        InterviewCardFrequency.FREQUENT: 0,
        InterviewCardFrequency.OCCASIONAL: 1,
    }
    rows.sort(
        key=lambda row: (
            frequency_order[effective_card_frequency(row[0])],
            1 if row[1] is None else 0,
            row[1].due_at if row[1] is not None else now,
            row[0].position,
        )
    )
    cards = [
        InterviewCardStudy(
            id=card.id,
            slug=card.slug,
            category=card.category,
            subcategory=card.subcategory,
            companies=card.companies,
            question_markdown=card.question_markdown,
            answer_markdown=card.answer_markdown,
            frequency=effective_card_frequency(card),
            is_new=progress is None,
            repetitions=progress.repetitions if progress is not None else 0,
        )
        for card, progress in rows[:limit]
    ]
    return InterviewStudySession(
        deck=await _deck_list_item(
            session,
            user.id,
            deck,
            track,
            frequent_only=frequent_only,
        ),
        cards=cards,
    )


async def search_interview_cards(
    session: AsyncSession,
    user: User,
    deck_slug: str,
    query: str,
    limit: int,
    *,
    frequent_only: bool = False,
) -> list[InterviewCardStudy]:
    deck, _track = await _public_deck_model(session, deck_slug, user)
    selected_categories = await _selected_categories(session, user.id, deck.id)
    if not selected_categories:
        return []

    normalized_query = query.strip()
    if not normalized_query:
        return []
    search_query = func.websearch_to_tsquery(
        "russian",
        normalized_query,
    ).op("||")(
        func.websearch_to_tsquery("simple", normalized_query),
    )
    card_filters = [
        InterviewCard.deck_id == deck.id,
        InterviewCard.is_published.is_(True),
        InterviewCard.category.in_(selected_categories),
    ]
    if frequent_only:
        card_filters.append(effective_frequent_predicate())
    card_filters.append(InterviewCard.search_vector.op("@@")(search_query))
    rank = func.ts_rank_cd(InterviewCard.search_vector, search_query)

    rows = (
        await session.execute(
            select(InterviewCard, InterviewCardProgress)
            .outerjoin(
                InterviewCardProgress,
                (InterviewCardProgress.card_id == InterviewCard.id)
                & (InterviewCardProgress.user_id == user.id),
            )
            .where(*card_filters)
            .order_by(
                rank.desc(),
                effective_frequent_predicate().desc(),
                InterviewCard.category,
                InterviewCard.position,
            )
            .limit(limit)
        )
    ).all()
    return [
        InterviewCardStudy(
            id=card.id,
            slug=card.slug,
            category=card.category,
            subcategory=card.subcategory,
            companies=card.companies,
            question_markdown=card.question_markdown,
            answer_markdown=card.answer_markdown,
            frequency=effective_card_frequency(card),
            is_new=progress is None,
            repetitions=progress.repetitions if progress is not None else 0,
        )
        for card, progress in rows
    ]


async def list_interview_questions(
    session: AsyncSession,
    user: User,
    deck_slug: str,
    *,
    categories: list[str] | None,
    frequent_only: bool,
    learned: InterviewQuestionLearnedFilter,
    sort: InterviewQuestionSort,
    order: InterviewQuestionSortDirection,
    query: str | None,
    limit: int,
    offset: int,
) -> InterviewQuestionTablePage:
    deck, track = await _public_deck_model(session, deck_slug, user)
    filters = [
        InterviewCard.deck_id == deck.id,
        InterviewCard.is_published.is_(True),
    ]
    normalized_categories = {
        category.strip() for category in categories or [] if category.strip()
    }
    if normalized_categories:
        filters.append(InterviewCard.category.in_(normalized_categories))
    if frequent_only:
        filters.append(effective_frequent_predicate())
    if learned is InterviewQuestionLearnedFilter.LEARNED:
        filters.append(InterviewCardProgress.first_learned_at.is_not(None))
    elif learned is InterviewQuestionLearnedFilter.UNLEARNED:
        filters.append(InterviewCardProgress.first_learned_at.is_(None))

    normalized_query = query.strip() if query else ""
    if normalized_query:
        search_query = func.websearch_to_tsquery("russian", normalized_query).op("||")(
            func.websearch_to_tsquery("simple", normalized_query)
        )
        filters.append(InterviewCard.search_vector.op("@@")(search_query))

    base = (
        select(InterviewCard, InterviewCardProgress)
        .outerjoin(
            InterviewCardProgress,
            (InterviewCardProgress.card_id == InterviewCard.id)
            & (InterviewCardProgress.user_id == user.id),
        )
        .where(*filters)
    )
    total = (
        await session.scalar(
            select(func.count())
            .select_from(InterviewCard)
            .outerjoin(
                InterviewCardProgress,
                (InterviewCardProgress.card_id == InterviewCard.id)
                & (InterviewCardProgress.user_id == user.id),
            )
            .where(*filters)
        )
        or 0
    )
    sort_expression = {
        InterviewQuestionSort.FREQUENCY: effective_frequent_predicate(),
        InterviewQuestionSort.QUESTION: func.lower(InterviewCard.question_markdown),
        InterviewQuestionSort.CATEGORY: func.lower(InterviewCard.category),
        InterviewQuestionSort.LEARNED: InterviewCardProgress.first_learned_at.is_not(None),
        InterviewQuestionSort.DUE_AT: InterviewCardProgress.due_at,
    }[sort]
    primary_order = (
        sort_expression.desc()
        if order is InterviewQuestionSortDirection.DESC
        else sort_expression.asc()
    )
    if sort is InterviewQuestionSort.DUE_AT:
        primary_order = primary_order.nulls_last()

    rows = (
        await session.execute(
            base.order_by(
                primary_order,
                effective_frequent_predicate().desc(),
                InterviewCard.category,
                InterviewCard.position,
                InterviewCard.id,
            )
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return InterviewQuestionTablePage(
        deck=await _deck_list_item(session, user.id, deck, track),
        items=[
            InterviewQuestionTableItem(
                id=card.id,
                slug=card.slug,
                category=card.category,
                subcategory=card.subcategory,
                question_markdown=card.question_markdown,
                answer_markdown=card.answer_markdown,
                frequency=effective_card_frequency(card),
                learned=progress is not None and progress.first_learned_at is not None,
                learned_at=progress.first_learned_at if progress is not None else None,
                repetitions=progress.repetitions if progress is not None else 0,
                due_at=progress.due_at if progress is not None else None,
            )
            for card, progress in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


async def set_interview_question_learned(
    session: AsyncSession,
    user: User,
    card_id: UUID,
    *,
    learned: bool,
) -> InterviewQuestionLearnedResult:
    row = (
        await session.execute(
            select(InterviewCard, InterviewDeck)
            .join(InterviewDeck, InterviewDeck.id == InterviewCard.deck_id)
            .join(LearningTrack, LearningTrack.id == InterviewDeck.track_id)
            .where(
                InterviewCard.id == card_id,
                InterviewCard.is_published.is_(True),
                InterviewDeck.is_published.is_(True),
                LearningTrack.is_published.is_(True),
            )
        )
    ).one_or_none()
    if row is None:
        api_error(404, "interview_card_not_found", "Interview card was not found")
    card, deck = row
    if not await _has_track_access(session, user, deck.track_id):
        api_error(403, "interview_deck_access_denied", "Track access is required")

    progress = await session.get(InterviewCardProgress, (user.id, card.id), with_for_update=True)
    now = datetime.now(UTC)
    if learned:
        if progress is None:
            progress = InterviewCardProgress(
                user_id=user.id,
                card_id=card.id,
                repetitions=1,
                interval_days=30,
                ease_factor=2.65,
                lapses=0,
                due_at=now + timedelta(days=30),
                first_learned_at=now,
                last_reviewed_at=now,
                last_rating=InterviewReviewRating.KNOWN,
            )
            session.add(progress)
        elif progress.first_learned_at is None:
            progress.repetitions = max(1, progress.repetitions)
            progress.interval_days = 30
            progress.ease_factor = max(2.65, progress.ease_factor)
            progress.due_at = now + timedelta(days=30)
            progress.first_learned_at = now
            progress.last_reviewed_at = now
            progress.last_rating = InterviewReviewRating.KNOWN
    elif progress is not None:
        progress.repetitions = 0
        progress.interval_days = 0
        progress.ease_factor = 2.5
        progress.lapses = 0
        progress.due_at = now
        progress.first_learned_at = None
        progress.last_reviewed_at = None
        progress.last_rating = None

    await session.commit()
    if progress is not None:
        await session.refresh(progress)
    return InterviewQuestionLearnedResult(
        card_id=card.id,
        learned=progress is not None and progress.first_learned_at is not None,
        learned_at=progress.first_learned_at if progress is not None else None,
        due_at=progress.due_at if progress is not None else None,
    )


async def get_interview_topics(
    session: AsyncSession, user: User, deck_slug: str
) -> list[InterviewTopicOption]:
    deck, _track = await _public_deck_model(session, deck_slug, user)
    frequent_count = func.count(InterviewCard.id).filter(effective_frequent_predicate())
    rows = (
        await session.execute(
            select(
                InterviewCard.category,
                func.count(InterviewCard.id),
                frequent_count,
            )
            .where(
                InterviewCard.deck_id == deck.id,
                InterviewCard.is_published.is_(True),
            )
            .group_by(InterviewCard.category)
            .order_by(InterviewCard.category)
        )
    ).all()
    selected = await _selected_categories(session, user.id, deck.id)
    return [
        InterviewTopicOption(
            name=category,
            total_cards=total,
            frequent_cards=frequent,
            is_selected=category in selected,
        )
        for category, total, frequent in rows
    ]


async def update_interview_topics(
    session: AsyncSession,
    user: User,
    deck_slug: str,
    categories: list[str],
) -> list[InterviewTopicOption]:
    deck, _track = await _public_deck_model(session, deck_slug, user)
    available = set(
        await session.scalars(
            select(InterviewCard.category)
            .where(
                InterviewCard.deck_id == deck.id,
                InterviewCard.is_published.is_(True),
            )
            .distinct()
        )
    )
    unknown = set(categories) - available
    if unknown:
        api_error(422, "invalid_interview_topics", "Some interview topics are unavailable")
    await session.execute(
        delete(InterviewTopicSelection).where(
            InterviewTopicSelection.user_id == user.id,
            InterviewTopicSelection.deck_id == deck.id,
        )
    )
    session.add_all(
        [
            InterviewTopicSelection(user_id=user.id, deck_id=deck.id, category=category)
            for category in categories
        ]
    )
    await session.commit()
    return await get_interview_topics(session, user, deck_slug)


def _next_interval(
    progress: InterviewCardProgress, rating: InterviewReviewRating
) -> tuple[int, float]:
    ease = progress.ease_factor
    if rating is InterviewReviewRating.AGAIN:
        return 0, max(1.3, ease - 0.2)
    if rating is InterviewReviewRating.HARD:
        return max(1, round(progress.interval_days * 1.2)), max(1.3, ease - 0.15)
    if rating is InterviewReviewRating.GOOD:
        interval = 2 if progress.interval_days == 0 else round(progress.interval_days * ease)
        return min(365, max(2, interval)), ease
    if rating is InterviewReviewRating.KNOWN:
        return 30, max(2.65, ease)
    interval = 4 if progress.interval_days == 0 else round(progress.interval_days * ease * 1.3)
    return min(365, max(4, interval)), ease + 0.15


async def review_interview_card(
    session: AsyncSession,
    user: User,
    card_id: UUID,
    rating: InterviewReviewRating,
) -> InterviewReviewResult:
    row = (
        await session.execute(
            select(InterviewCard, InterviewDeck, LearningTrack)
            .join(InterviewDeck, InterviewDeck.id == InterviewCard.deck_id)
            .join(LearningTrack, LearningTrack.id == InterviewDeck.track_id)
            .where(
                InterviewCard.id == card_id,
                InterviewCard.is_published.is_(True),
                InterviewDeck.is_published.is_(True),
                LearningTrack.is_published.is_(True),
            )
        )
    ).one_or_none()
    if row is None:
        api_error(404, "interview_card_not_found", "Interview card was not found")
    card, deck, _track = row
    if not await _has_track_access(session, user, deck.track_id):
        api_error(403, "interview_deck_access_denied", "Track access is required")
    selection = await session.get(InterviewTopicSelection, (user.id, deck.id, card.category))
    if selection is None:
        api_error(403, "interview_topic_not_selected", "Select this topic before reviewing it")

    progress = await session.get(InterviewCardProgress, (user.id, card.id), with_for_update=True)
    if progress is None:
        progress = InterviewCardProgress(
            user_id=user.id,
            card_id=card.id,
            repetitions=0,
            interval_days=0,
            ease_factor=2.5,
            lapses=0,
            due_at=datetime.now(UTC),
        )
        session.add(progress)
    now = datetime.now(UTC)
    interval_days, ease_factor = _next_interval(progress, rating)
    if rating is InterviewReviewRating.AGAIN:
        progress.repetitions = 0
        progress.lapses += 1
        progress.due_at = now + timedelta(minutes=10)
    else:
        progress.repetitions += 1
        progress.first_learned_at = progress.first_learned_at or now
        progress.due_at = now + timedelta(days=interval_days)
    progress.interval_days = interval_days
    progress.ease_factor = ease_factor
    progress.last_reviewed_at = now
    progress.last_rating = rating
    await session.commit()
    await session.refresh(progress)
    return InterviewReviewResult(
        card_id=card.id,
        rating=rating,
        repetitions=progress.repetitions,
        interval_days=progress.interval_days,
        due_at=progress.due_at,
        learned=progress.first_learned_at is not None,
    )


async def _admin_deck_model(
    session: AsyncSession, deck_id: UUID, *, lock: bool = False
) -> InterviewDeck:
    statement = (
        select(InterviewDeck)
        .where(InterviewDeck.id == deck_id)
        .options(selectinload(InterviewDeck.cards))
    )
    if lock:
        statement = statement.with_for_update()
    deck = cast(InterviewDeck | None, await session.scalar(statement))
    if deck is None:
        api_error(404, "interview_deck_not_found", "Interview deck was not found")
    return deck


async def _track(session: AsyncSession, track_id: UUID) -> LearningTrack:
    track = await session.get(LearningTrack, track_id)
    if track is None:
        api_error(422, "interview_track_not_found", "Learning track was not found")
    return track


def _admin_card_read(card: InterviewCard) -> AdminInterviewCardRead:
    return AdminInterviewCardRead(
        id=card.id,
        slug=card.slug,
        category=card.category,
        subcategory=card.subcategory,
        companies=card.companies,
        source_number=card.source_number,
        source_occurrence=card.source_occurrence,
        question_markdown=card.question_markdown,
        answer_markdown=card.answer_markdown,
        frequency=effective_card_frequency(card),
        frequency_override=card.frequency_override,
        frequency_mode=card_frequency_mode(card),
        frequency_threshold=frequent_occurrence_threshold(),
        position=card.position,
        is_published=card.is_published,
        asked_count=card.asked_count,
        updated_at=card.updated_at,
    )


async def _admin_deck_read(session: AsyncSession, deck: InterviewDeck) -> AdminInterviewDeckRead:
    track = await _track(session, deck.track_id)
    return AdminInterviewDeckRead(
        id=deck.id,
        track_id=track.id,
        track_slug=track.slug,
        track_title=track.title,
        slug=deck.slug,
        title=deck.title,
        description=deck.description,
        position=deck.position,
        is_published=deck.is_published,
        cards=[
            _admin_card_read(card) for card in sorted(deck.cards, key=lambda item: item.position)
        ],
    )


async def list_admin_interview_decks(
    session: AsyncSession,
) -> list[AdminInterviewDeckRead]:
    decks = list(
        await session.scalars(
            select(InterviewDeck)
            .order_by(InterviewDeck.position, InterviewDeck.title)
            .options(selectinload(InterviewDeck.cards))
        )
    )
    return [await _admin_deck_read(session, deck) for deck in decks]


async def get_admin_interview_deck(session: AsyncSession, deck_id: UUID) -> AdminInterviewDeckRead:
    return await _admin_deck_read(session, await _admin_deck_model(session, deck_id))


async def list_admin_interview_deck_summaries(
    session: AsyncSession,
) -> list[AdminInterviewDeckSummary]:
    frequent_count = func.count(InterviewCard.id).filter(effective_frequent_predicate())
    rows = (
        await session.execute(
            select(
                InterviewDeck,
                LearningTrack.slug,
                LearningTrack.title,
                func.count(InterviewCard.id),
                frequent_count,
            )
            .join(LearningTrack, LearningTrack.id == InterviewDeck.track_id)
            .outerjoin(InterviewCard, InterviewCard.deck_id == InterviewDeck.id)
            .group_by(InterviewDeck.id, LearningTrack.slug, LearningTrack.title)
            .order_by(InterviewDeck.position, InterviewDeck.title)
        )
    ).all()
    return [
        AdminInterviewDeckSummary(
            id=deck.id,
            track_id=deck.track_id,
            track_slug=track_slug,
            track_title=track_title,
            slug=deck.slug,
            title=deck.title,
            description=deck.description,
            position=deck.position,
            is_published=deck.is_published,
            card_count=card_count,
            frequent_count=frequent,
        )
        for deck, track_slug, track_title, card_count, frequent in rows
    ]


async def get_admin_interview_deck_summary(
    session: AsyncSession, deck_id: UUID
) -> AdminInterviewDeckSummary:
    summaries = await list_admin_interview_deck_summaries(session)
    summary = next((item for item in summaries if item.id == deck_id), None)
    if summary is None:
        api_error(404, "interview_deck_not_found", "Interview deck was not found")
    return summary


async def update_admin_interview_deck_settings(
    session: AsyncSession,
    deck_id: UUID,
    payload: AdminInterviewDeckSettingsMutation,
) -> AdminInterviewDeckSummary:
    deck = await session.get(InterviewDeck, deck_id, with_for_update=True)
    if deck is None:
        api_error(404, "interview_deck_not_found", "Interview deck was not found")
    await _track(session, payload.track_id)
    conflict = select(InterviewDeck.id).where(
        InterviewDeck.slug == payload.slug, InterviewDeck.id != deck_id
    )
    if await session.scalar(conflict) is not None:
        api_error(409, "interview_deck_slug_conflict", "Deck slug is already in use")
    deck.track_id = payload.track_id
    deck.slug = payload.slug
    deck.title = payload.title
    deck.description = payload.description
    deck.position = payload.position
    deck.is_published = payload.is_published
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        api_error(409, "interview_deck_conflict", "Interview deck contains conflicts")
    return await get_admin_interview_deck_summary(session, deck_id)


async def list_admin_interview_cards(
    session: AsyncSession,
    deck_id: UUID,
    *,
    query: str | None,
    limit: int,
    offset: int,
) -> AdminInterviewCardPage:
    if await session.get(InterviewDeck, deck_id) is None:
        api_error(404, "interview_deck_not_found", "Interview deck was not found")
    filters = [InterviewCard.deck_id == deck_id]
    if query:
        pattern = f"%{query.strip()}%"
        filters.append(
            or_(
                InterviewCard.question_markdown.ilike(pattern),
                InterviewCard.category.ilike(pattern),
                InterviewCard.slug.ilike(pattern),
            )
        )
    total = await session.scalar(select(func.count(InterviewCard.id)).where(*filters)) or 0
    cards = list(
        await session.scalars(
            select(InterviewCard)
            .where(*filters)
            .order_by(InterviewCard.position, InterviewCard.id)
            .limit(limit)
            .offset(offset)
        )
    )
    return AdminInterviewCardPage(
        items=[
            AdminInterviewCardSummary(
                id=card.id,
                slug=card.slug,
                category=card.category,
                subcategory=card.subcategory,
                question_preview=card.question_markdown[:180],
                frequency=effective_card_frequency(card),
                frequency_override=card.frequency_override,
                frequency_mode=card_frequency_mode(card),
                frequency_threshold=frequent_occurrence_threshold(),
                position=card.position,
                is_published=card.is_published,
                asked_count=card.asked_count,
            )
            for card in cards
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


async def get_admin_interview_card(
    session: AsyncSession, deck_id: UUID, card_id: UUID
) -> AdminInterviewCardRead:
    card = await session.get(InterviewCard, card_id)
    if card is None or card.deck_id != deck_id:
        api_error(404, "interview_card_not_found", "Interview card was not found")
    return _admin_card_read(card)


async def _validate_card_slug(
    session: AsyncSession, slug: str, card_id: UUID | None = None
) -> None:
    statement = select(InterviewCard.id).where(InterviewCard.slug == slug)
    if card_id is not None:
        statement = statement.where(InterviewCard.id != card_id)
    if await session.scalar(statement) is not None:
        api_error(409, "interview_card_slug_conflict", "Card slug is already in use")


async def create_admin_interview_card(
    session: AsyncSession, deck_id: UUID, payload: AdminInterviewCardMutation
) -> AdminInterviewCardRead:
    deck = await session.get(InterviewDeck, deck_id)
    if deck is None:
        api_error(404, "interview_deck_not_found", "Interview deck was not found")
    await _validate_card_slug(session, payload.slug)
    card = InterviewCard(deck_id=deck_id)
    _apply_card(card, payload)
    session.add(card)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        api_error(409, "interview_card_conflict", "Interview card contains conflicts")
    await session.refresh(card)
    return _admin_card_read(card)


async def update_admin_interview_card(
    session: AsyncSession,
    deck_id: UUID,
    card_id: UUID,
    payload: AdminInterviewCardMutation,
) -> AdminInterviewCardRead:
    card = await session.get(InterviewCard, card_id, with_for_update=True)
    if card is None or card.deck_id != deck_id:
        api_error(404, "interview_card_not_found", "Interview card was not found")
    if payload.id is not None and payload.id != card_id:
        api_error(422, "invalid_interview_card", "Card ID does not match the route")
    await _validate_card_slug(session, payload.slug, card_id)
    _apply_card(card, payload)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        api_error(409, "interview_card_conflict", "Interview card contains conflicts")
    await session.refresh(card)
    return _admin_card_read(card)


async def _validate_admin_payload(
    session: AsyncSession,
    payload: AdminInterviewDeckMutation,
    deck_id: UUID | None,
) -> None:
    await _track(session, payload.track_id)
    deck_conflict = select(InterviewDeck.id).where(InterviewDeck.slug == payload.slug)
    if deck_id is not None:
        deck_conflict = deck_conflict.where(InterviewDeck.id != deck_id)
    if await session.scalar(deck_conflict) is not None:
        api_error(409, "interview_deck_slug_conflict", "Deck slug is already in use")
    slugs = [card.slug for card in payload.cards]
    if not slugs:
        return
    card_conflict = select(InterviewCard.id).where(InterviewCard.slug.in_(slugs))
    if deck_id is not None:
        card_conflict = card_conflict.where(InterviewCard.deck_id != deck_id)
    if await session.scalar(card_conflict.limit(1)) is not None:
        api_error(409, "interview_card_slug_conflict", "Card slug is already in use")


def _apply_card(card: InterviewCard, payload: AdminInterviewCardMutation) -> None:
    if card.question_markdown != payload.question_markdown:
        card.question_embedding = None
        card.question_embedding_model = None
        card.question_embedding_dimensions = None
        card.question_embedding_source_hash = None
    card.slug = payload.slug
    card.category = payload.category
    card.subcategory = payload.subcategory
    card.companies = payload.companies
    card.question_markdown = payload.question_markdown
    card.answer_markdown = payload.answer_markdown
    card.frequency_override = (
        payload.frequency if payload.frequency_mode is InterviewCardFrequencyMode.MANUAL else None
    )
    refresh_card_frequency(card)
    card.position = payload.position
    card.is_published = payload.is_published


async def create_admin_interview_deck(
    session: AsyncSession, payload: AdminInterviewDeckMutation
) -> AdminInterviewDeckRead:
    await _validate_admin_payload(session, payload, None)
    deck = InterviewDeck(
        track_id=payload.track_id,
        slug=payload.slug,
        title=payload.title,
        description=payload.description,
        position=payload.position,
        is_published=payload.is_published,
    )
    for card_payload in payload.cards:
        card = InterviewCard()
        _apply_card(card, card_payload)
        deck.cards.append(card)
    session.add(deck)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        api_error(409, "interview_deck_conflict", "Interview deck contains conflicts")
    return await get_admin_interview_deck(session, deck.id)


async def update_admin_interview_deck(
    session: AsyncSession,
    deck_id: UUID,
    payload: AdminInterviewDeckMutation,
) -> AdminInterviewDeckRead:
    deck = await _admin_deck_model(session, deck_id, lock=True)
    await _validate_admin_payload(session, payload, deck_id)
    existing = {card.id: card for card in deck.cards}
    supplied_ids = {card.id for card in payload.cards if card.id is not None}
    if not supplied_ids.issubset(existing):
        api_error(422, "invalid_interview_structure", "Card does not belong to this deck")
    deck.track_id = payload.track_id
    deck.slug = payload.slug
    deck.title = payload.title
    deck.description = payload.description
    deck.position = payload.position
    deck.is_published = payload.is_published
    for card in list(deck.cards):
        if card.id not in supplied_ids:
            deck.cards.remove(card)
    for card_payload in payload.cards:
        card = InterviewCard() if card_payload.id is None else existing[card_payload.id]
        _apply_card(card, card_payload)
        if card_payload.id is None:
            deck.cards.append(card)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        api_error(409, "interview_deck_conflict", "Interview deck contains conflicts")
    return await get_admin_interview_deck(session, deck.id)
