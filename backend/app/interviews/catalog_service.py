from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import ColumnElement, and_, case, delete, distinct, exists, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.errors import api_error
from app.interviews.companies import suggest_companies
from app.interviews.models import (
    Company,
    InterviewCatalogFavorite,
    InterviewCatalogView,
    InterviewProcess,
    InterviewProcessStage,
    InterviewProcessStageAttachment,
    InterviewProcessStatus,
    InterviewStageComment,
    InterviewStageType,
)
from app.interviews.schemas import (
    InterviewAttachmentRead,
    InterviewCatalogAuthorRead,
    InterviewCatalogCommentMutation,
    InterviewCatalogCommentRead,
    InterviewCatalogCompanyDetail,
    InterviewCatalogCompanyListItem,
    InterviewCatalogCompanyPage,
    InterviewCatalogHistoryItem,
    InterviewCatalogHistoryPage,
    InterviewCatalogMediaKind,
    InterviewCatalogStageRead,
    InterviewCatalogTrackRead,
    InterviewDirectionOption,
    InterviewStageAttachmentRead,
)
from app.mentors.models import MentorTrackAssignment
from app.tracks.models import LearningTrack, LearningTrackEnrollment
from app.users.models import User, UserRole


def _catalog_process_filters(
    *,
    author_id: UUID | None,
    track_id: UUID | None,
    stage_type: InterviewStageType | None,
    has_offer: bool,
    media_kind: InterviewCatalogMediaKind | None,
    current_user_id: UUID,
    has_ai_review: bool = False,
    favorites_only: bool = False,
) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []
    if author_id is not None:
        conditions.append(InterviewProcess.user_id == author_id)
    if track_id is not None:
        conditions.append(InterviewProcess.track_id == track_id)
    if has_offer:
        conditions.append(InterviewProcess.status == InterviewProcessStatus.OFFER)
    if stage_type is not None or media_kind is not None:
        matching_stage = aliased(InterviewProcessStage)
        stage_conditions: list[ColumnElement[bool]] = [
            matching_stage.process_id == InterviewProcess.id
        ]
        if stage_type is not None:
            stage_conditions.append(matching_stage.stage_type == stage_type)
        if media_kind is not None:
            media_content_filter = (
                or_(
                    matching_stage.media_content_type.like("video/%"),
                    matching_stage.media_content_type.like("audio/%"),
                )
                if media_kind is InterviewCatalogMediaKind.ANY
                else matching_stage.media_content_type.like(f"{media_kind.value}/%")
            )
            stage_conditions.extend(
                [matching_stage.media_storage_key.is_not(None), media_content_filter]
            )
        conditions.append(exists(select(1).select_from(matching_stage).where(*stage_conditions)))
    if has_ai_review:
        ai_stage = aliased(InterviewProcessStage)
        ai_comment = aliased(InterviewStageComment)
        conditions.append(
            exists(
                select(1)
                .select_from(ai_comment)
                .join(ai_stage, ai_stage.id == ai_comment.stage_id)
                .where(
                    ai_stage.process_id == InterviewProcess.id,
                    ai_comment.is_ai_feedback.is_(True),
                )
            )
        )
    if favorites_only:
        favorite_stage = aliased(InterviewProcessStage)
        favorite = aliased(InterviewCatalogFavorite)
        conditions.append(
            exists(
                select(1)
                .select_from(favorite)
                .join(favorite_stage, favorite_stage.id == favorite.stage_id)
                .where(
                    favorite_stage.process_id == InterviewProcess.id,
                    favorite.user_id == current_user_id,
                )
            )
        )
    return conditions


def _catalog_stage_filters(
    *,
    stage_type: InterviewStageType | None,
    media_kind: InterviewCatalogMediaKind | None,
    current_user_id: UUID,
    has_ai_review: bool = False,
    favorites_only: bool = False,
) -> list[ColumnElement[bool]]:
    """Narrow which stages of an already-matched track are actually shown.

    _catalog_process_filters decides whether a track qualifies (it has *some*
    stage matching the filters); this narrows the returned stages to just the
    ones that match, so e.g. filtering by favorites doesn't dump the whole
    track's unrelated stages alongside the one the user actually favorited.
    """
    conditions: list[ColumnElement[bool]] = []
    if stage_type is not None:
        conditions.append(InterviewProcessStage.stage_type == stage_type)
    if media_kind is not None:
        media_content_filter = (
            or_(
                InterviewProcessStage.media_content_type.like("video/%"),
                InterviewProcessStage.media_content_type.like("audio/%"),
            )
            if media_kind is InterviewCatalogMediaKind.ANY
            else InterviewProcessStage.media_content_type.like(f"{media_kind.value}/%")
        )
        conditions.extend(
            [InterviewProcessStage.media_storage_key.is_not(None), media_content_filter]
        )
    if has_ai_review:
        ai_comment = aliased(InterviewStageComment)
        conditions.append(
            exists(
                select(1)
                .select_from(ai_comment)
                .where(
                    ai_comment.stage_id == InterviewProcessStage.id,
                    ai_comment.is_ai_feedback.is_(True),
                )
            )
        )
    if favorites_only:
        favorite = aliased(InterviewCatalogFavorite)
        conditions.append(
            exists(
                select(1)
                .select_from(favorite)
                .where(
                    favorite.stage_id == InterviewProcessStage.id,
                    favorite.user_id == current_user_id,
                )
            )
        )
    return conditions


def _student_direction_filter(user_id: UUID) -> ColumnElement[bool]:
    return exists(
        select(1)
        .select_from(LearningTrackEnrollment)
        .join(
            LearningTrack,
            LearningTrack.id == LearningTrackEnrollment.track_id,
        )
        .where(
            LearningTrackEnrollment.user_id == user_id,
            LearningTrackEnrollment.track_id == InterviewProcess.track_id,
            LearningTrack.is_published.is_(True),
        )
    )


def _direction_filters(current_user: User) -> list[ColumnElement[bool]]:
    if current_user.role is UserRole.ADMIN:
        return []
    if current_user.role is UserRole.MENTOR:
        return [
            exists(
                select(1)
                .select_from(MentorTrackAssignment)
                .join(
                    LearningTrack,
                    LearningTrack.id == MentorTrackAssignment.track_id,
                )
                .where(
                    MentorTrackAssignment.mentor_id == current_user.id,
                    MentorTrackAssignment.track_id == InterviewProcess.track_id,
                    LearningTrack.is_published.is_(True),
                )
            )
        ]
    return [_student_direction_filter(current_user.id)]


def _author(user: User) -> InterviewCatalogAuthorRead:
    return InterviewCatalogAuthorRead(
        id=user.id,
        name=user.first_name,
        telegram_username=user.telegram_username,
    )


def _media(stage: InterviewProcessStage) -> InterviewAttachmentRead | None:
    if stage.media_filename is None or stage.media_content_type is None or stage.media_size is None:
        return None
    return InterviewAttachmentRead(
        filename=stage.media_filename,
        content_type=stage.media_content_type,
        size=stage.media_size,
    )


def _attachment(
    attachment: InterviewProcessStageAttachment,
) -> InterviewStageAttachmentRead:
    return InterviewStageAttachmentRead(
        id=attachment.id,
        filename=attachment.filename,
        content_type=attachment.content_type,
        size=attachment.size,
        created_at=attachment.created_at,
    )


def _comment(
    comment: InterviewStageComment, author: User | None, current_user: User
) -> InterviewCatalogCommentRead:
    return InterviewCatalogCommentRead(
        id=comment.id,
        author=_author(author) if author is not None else None,
        body=comment.body,
        is_own=comment.user_id == current_user.id,
        is_mentor_feedback=(author is not None and author.role.value in {"mentor", "admin"}),
        is_ai_feedback=comment.is_ai_feedback,
        created_at=comment.created_at,
        updated_at=comment.updated_at,
    )


async def list_catalog_companies(
    session: AsyncSession,
    current_user: User,
    query: str | None,
    *,
    author_id: UUID | None = None,
    track_id: UUID | None = None,
    stage_type: InterviewStageType | None = None,
    has_offer: bool = False,
    media_kind: InterviewCatalogMediaKind | None = None,
    has_ai_review: bool = False,
    favorites_only: bool = False,
    limit: int = 24,
    offset: int = 0,
) -> InterviewCatalogCompanyPage:
    candidate_ids: list[UUID] | None = None
    if query and query.strip():
        candidates = await suggest_companies(session, query, 100)
        candidate_ids = [company.id for company in candidates]
        if not candidate_ids:
            return InterviewCatalogCompanyPage(items=[], total=0, limit=limit, offset=offset)

    stage_match_conditions = _catalog_stage_filters(
        stage_type=stage_type,
        media_kind=media_kind,
        current_user_id=current_user.id,
        has_ai_review=has_ai_review,
        favorites_only=favorites_only,
    )
    matching_stage_id = (
        case((and_(*stage_match_conditions), InterviewProcessStage.id))
        if stage_match_conditions
        else InterviewProcessStage.id
    )
    matching_stage_scheduled_at = (
        case((and_(*stage_match_conditions), InterviewProcessStage.scheduled_at))
        if stage_match_conditions
        else InterviewProcessStage.scheduled_at
    )
    view_alias = aliased(InterviewCatalogView)
    favorite_alias = aliased(InterviewCatalogFavorite)
    statement = (
        select(
            Company,
            func.count(distinct(InterviewProcess.id)),
            func.count(distinct(matching_stage_id)),
            func.max(matching_stage_scheduled_at),
            func.count(distinct(case((view_alias.stage_id.is_(None), matching_stage_id)))),
            func.bool_or(favorite_alias.stage_id.is_not(None)),
        )
        .join(InterviewProcess, InterviewProcess.company_id == Company.id)
        .outerjoin(
            InterviewProcessStage,
            InterviewProcessStage.process_id == InterviewProcess.id,
        )
        .outerjoin(
            view_alias,
            and_(
                view_alias.stage_id == InterviewProcessStage.id,
                view_alias.user_id == current_user.id,
            ),
        )
        .outerjoin(
            favorite_alias,
            and_(
                favorite_alias.stage_id == InterviewProcessStage.id,
                favorite_alias.user_id == current_user.id,
            ),
        )
        .group_by(Company.id)
        .where(
            *_direction_filters(current_user),
            *_catalog_process_filters(
                author_id=author_id,
                track_id=track_id,
                stage_type=stage_type,
                has_offer=has_offer,
                media_kind=media_kind,
                current_user_id=current_user.id,
                has_ai_review=has_ai_review,
                favorites_only=favorites_only,
            ),
        )
    )
    if candidate_ids is not None:
        statement = statement.where(Company.id.in_(candidate_ids)).order_by(
            case(
                *[
                    (Company.id == company_id, position)
                    for position, company_id in enumerate(candidate_ids)
                ],
                else_=len(candidate_ids),
            )
        )
    else:
        statement = statement.order_by(
            func.max(matching_stage_scheduled_at).desc().nullslast(),
            Company.name,
        )
    total = int(
        await session.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))
        or 0
    )
    rows = (await session.execute(statement.limit(limit).offset(offset))).all()
    items = [
        InterviewCatalogCompanyListItem(
            id=company.id,
            name=company.name,
            track_count=track_count,
            interview_count=interview_count,
            last_interview_at=last_interview_at,
            unviewed_count=unviewed_count,
            has_favorite=bool(has_favorite),
        )
        for (
            company,
            track_count,
            interview_count,
            last_interview_at,
            unviewed_count,
            has_favorite,
        ) in rows
    ]
    return InterviewCatalogCompanyPage(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


async def list_catalog_directions(
    session: AsyncSession, current_user: User
) -> list[InterviewDirectionOption]:
    statement = select(LearningTrack).where(LearningTrack.is_published.is_(True))
    if current_user.role is UserRole.MENTOR:
        statement = statement.join(
            MentorTrackAssignment,
            MentorTrackAssignment.track_id == LearningTrack.id,
        ).where(MentorTrackAssignment.mentor_id == current_user.id)
    elif current_user.role is not UserRole.ADMIN:
        statement = statement.join(
            LearningTrackEnrollment,
            LearningTrackEnrollment.track_id == LearningTrack.id,
        ).where(LearningTrackEnrollment.user_id == current_user.id)
    tracks = list(
        await session.scalars(statement.order_by(LearningTrack.position, LearningTrack.title))
    )
    return [
        InterviewDirectionOption(id=track.id, slug=track.slug, title=track.title)
        for track in tracks
    ]


async def list_catalog_authors(
    session: AsyncSession, current_user: User
) -> list[InterviewCatalogAuthorRead]:
    statement = select(User).join(InterviewProcess, InterviewProcess.user_id == User.id)
    statement = statement.where(*_direction_filters(current_user))
    authors = list(
        await session.scalars(
            statement.distinct().order_by(User.first_name, User.telegram_username, User.id)
        )
    )
    return [_author(author) for author in authors]


async def catalog_company_detail(
    session: AsyncSession,
    current_user: User,
    company_id: UUID,
    *,
    author_id: UUID | None = None,
    track_id: UUID | None = None,
    stage_type: InterviewStageType | None = None,
    has_offer: bool = False,
    media_kind: InterviewCatalogMediaKind | None = None,
    has_ai_review: bool = False,
    favorites_only: bool = False,
) -> InterviewCatalogCompanyDetail:
    company = await session.get(Company, company_id)
    if company is None:
        api_error(404, "interview_catalog_company_not_found", "Company was not found")

    has_accessible_process = await session.scalar(
        select(
            exists(
                select(1)
                .select_from(InterviewProcess)
                .where(
                    InterviewProcess.company_id == company.id,
                    *_direction_filters(current_user),
                )
            )
        )
    )
    if not has_accessible_process:
        api_error(
            404,
            "interview_catalog_company_not_available",
            "Company is not available for your learning directions",
        )

    process_rows = (
        await session.execute(
            select(InterviewProcess, User, LearningTrack)
            .join(User, User.id == InterviewProcess.user_id)
            .join(LearningTrack, LearningTrack.id == InterviewProcess.track_id)
            .where(
                InterviewProcess.company_id == company.id,
                *_direction_filters(current_user),
                *_catalog_process_filters(
                    author_id=author_id,
                    track_id=track_id,
                    stage_type=stage_type,
                    has_offer=has_offer,
                    media_kind=media_kind,
                    current_user_id=current_user.id,
                    has_ai_review=has_ai_review,
                    favorites_only=favorites_only,
                ),
            )
            .order_by(InterviewProcess.updated_at.desc())
        )
    ).all()
    process_ids = [process.id for process, _, _ in process_rows]
    stages = (
        list(
            await session.scalars(
                select(InterviewProcessStage)
                .where(
                    InterviewProcessStage.process_id.in_(process_ids),
                    *_catalog_stage_filters(
                        stage_type=stage_type,
                        media_kind=media_kind,
                        current_user_id=current_user.id,
                        has_ai_review=has_ai_review,
                        favorites_only=favorites_only,
                    ),
                )
                .order_by(
                    InterviewProcessStage.scheduled_at,
                    InterviewProcessStage.created_at,
                )
            )
        )
        if process_ids
        else []
    )
    stage_ids = [stage.id for stage in stages]
    view_by_stage: dict[UUID, InterviewCatalogView] = (
        {
            view.stage_id: view
            for view in await session.scalars(
                select(InterviewCatalogView).where(
                    InterviewCatalogView.user_id == current_user.id,
                    InterviewCatalogView.stage_id.in_(stage_ids),
                )
            )
        }
        if stage_ids
        else {}
    )
    favorite_stage_ids: set[UUID] = (
        set(
            await session.scalars(
                select(InterviewCatalogFavorite.stage_id).where(
                    InterviewCatalogFavorite.user_id == current_user.id,
                    InterviewCatalogFavorite.stage_id.in_(stage_ids),
                )
            )
        )
        if stage_ids
        else set()
    )
    attachments = (
        list(
            await session.scalars(
                select(InterviewProcessStageAttachment)
                .where(InterviewProcessStageAttachment.stage_id.in_(stage_ids))
                .order_by(InterviewProcessStageAttachment.created_at)
            )
        )
        if stage_ids
        else []
    )
    comment_rows = (
        (
            await session.execute(
                select(InterviewStageComment, User)
                .outerjoin(User, User.id == InterviewStageComment.user_id)
                .where(InterviewStageComment.stage_id.in_(stage_ids))
                .order_by(InterviewStageComment.created_at)
            )
        ).all()
        if stage_ids
        else []
    )

    attachments_by_stage: dict[UUID, list[InterviewProcessStageAttachment]] = {
        stage_id: [] for stage_id in stage_ids
    }
    for attachment in attachments:
        attachments_by_stage[attachment.stage_id].append(attachment)
    comments_by_stage: dict[UUID, list[tuple[InterviewStageComment, User | None]]] = {
        stage_id: [] for stage_id in stage_ids
    }
    for comment, author in comment_rows:
        comments_by_stage[comment.stage_id].append((comment, author))
    stages_by_process: dict[UUID, list[InterviewProcessStage]] = {
        process_id: [] for process_id in process_ids
    }
    for stage in stages:
        stages_by_process[stage.process_id].append(stage)

    tracks = []
    for process, author, track in process_rows:
        track_stages = [
            InterviewCatalogStageRead(
                id=stage.id,
                stage_type=stage.stage_type,
                scheduled_at=stage.scheduled_at,
                description=stage.description,
                media=_media(stage),
                attachments=[
                    _attachment(attachment) for attachment in attachments_by_stage[stage.id]
                ],
                comments=[
                    _comment(comment, comment_author, current_user)
                    for comment, comment_author in comments_by_stage[stage.id]
                ],
                is_viewed=stage.id in view_by_stage,
                first_viewed_at=(
                    view_by_stage[stage.id].first_viewed_at if stage.id in view_by_stage else None
                ),
                last_viewed_at=(
                    view_by_stage[stage.id].last_viewed_at if stage.id in view_by_stage else None
                ),
                is_favorite=stage.id in favorite_stage_ids,
            )
            for stage in stages_by_process[process.id]
        ]
        tracks.append(
            InterviewCatalogTrackRead(
                id=process.id,
                author=_author(author),
                recruiter_telegram_usernames=process.recruiter_telegram_usernames,
                track_id=track.id,
                track_slug=track.slug,
                track_title=track.title,
                status=process.status,
                close_reason=process.close_reason,
                created_at=process.created_at,
                updated_at=process.updated_at,
                stages=track_stages,
            )
        )
    return InterviewCatalogCompanyDetail(id=company.id, name=company.name, tracks=tracks)


async def get_catalog_stage(
    session: AsyncSession, current_user: User, stage_id: UUID
) -> InterviewProcessStage:
    stage = await session.scalar(
        select(InterviewProcessStage)
        .join(
            InterviewProcess,
            InterviewProcess.id == InterviewProcessStage.process_id,
        )
        .where(
            InterviewProcessStage.id == stage_id,
            *_direction_filters(current_user),
        )
    )
    if stage is None:
        api_error(404, "interview_catalog_stage_not_found", "Interview was not found")
    return stage


async def mark_catalog_stage_viewed(
    session: AsyncSession, current_user: User, stage_id: UUID
) -> None:
    stage = await get_catalog_stage(session, current_user, stage_id)
    now = datetime.now(UTC)
    await session.execute(
        insert(InterviewCatalogView)
        .values(
            user_id=current_user.id,
            stage_id=stage.id,
            first_viewed_at=now,
            last_viewed_at=now,
        )
        .on_conflict_do_update(
            index_elements=[InterviewCatalogView.user_id, InterviewCatalogView.stage_id],
            set_={"last_viewed_at": now},
        )
    )
    await session.commit()


async def list_catalog_view_history(
    session: AsyncSession,
    current_user: User,
    *,
    limit: int = 50,
    offset: int = 0,
) -> InterviewCatalogHistoryPage:
    statement = (
        select(
            InterviewCatalogView,
            InterviewProcessStage,
            InterviewProcess,
            LearningTrack,
            Company,
        )
        .join(InterviewProcessStage, InterviewProcessStage.id == InterviewCatalogView.stage_id)
        .join(InterviewProcess, InterviewProcess.id == InterviewProcessStage.process_id)
        .join(LearningTrack, LearningTrack.id == InterviewProcess.track_id)
        .join(Company, Company.id == InterviewProcess.company_id)
        .where(
            InterviewCatalogView.user_id == current_user.id,
            *_direction_filters(current_user),
        )
        .order_by(InterviewCatalogView.last_viewed_at.desc())
    )
    total = int(
        await session.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))
        or 0
    )
    rows = (await session.execute(statement.limit(limit).offset(offset))).all()
    items = [
        InterviewCatalogHistoryItem(
            stage_id=stage.id,
            process_id=process.id,
            company_id=company.id,
            company_name=company.name,
            track_title=track.title,
            stage_type=stage.stage_type,
            scheduled_at=stage.scheduled_at,
            description=stage.description,
            first_viewed_at=view.first_viewed_at,
            last_viewed_at=view.last_viewed_at,
        )
        for view, stage, process, track, company in rows
    ]
    return InterviewCatalogHistoryPage(items=items, total=total, limit=limit, offset=offset)


async def get_catalog_attachment(
    session: AsyncSession,
    current_user: User,
    stage_id: UUID,
    attachment_id: UUID,
) -> InterviewProcessStageAttachment:
    await get_catalog_stage(session, current_user, stage_id)
    attachment = await session.scalar(
        select(InterviewProcessStageAttachment).where(
            InterviewProcessStageAttachment.id == attachment_id,
            InterviewProcessStageAttachment.stage_id == stage_id,
        )
    )
    if attachment is None:
        api_error(404, "interview_attachment_not_found", "Attachment was not found")
    return attachment


async def create_catalog_comment(
    session: AsyncSession,
    current_user: User,
    stage_id: UUID,
    payload: InterviewCatalogCommentMutation,
) -> InterviewCatalogCommentRead:
    await get_catalog_stage(session, current_user, stage_id)
    comment = InterviewStageComment(
        stage_id=stage_id,
        user_id=current_user.id,
        body=payload.body,
    )
    session.add(comment)
    await session.commit()
    return _comment(comment, current_user, current_user)


async def delete_catalog_comment(
    session: AsyncSession, current_user: User, comment_id: UUID
) -> None:
    comment = await session.scalar(
        select(InterviewStageComment).where(
            InterviewStageComment.id == comment_id,
            InterviewStageComment.user_id == current_user.id,
        )
    )
    if comment is None:
        api_error(404, "interview_comment_not_found", "Comment was not found")
    await get_catalog_stage(session, current_user, comment.stage_id)
    await session.delete(comment)
    await session.commit()


async def set_catalog_favorite(session: AsyncSession, current_user: User, stage_id: UUID) -> None:
    stage = await get_catalog_stage(session, current_user, stage_id)
    await session.execute(
        insert(InterviewCatalogFavorite)
        .values(user_id=current_user.id, stage_id=stage.id)
        .on_conflict_do_nothing(
            index_elements=[
                InterviewCatalogFavorite.user_id,
                InterviewCatalogFavorite.stage_id,
            ]
        )
    )
    await session.commit()


async def remove_catalog_favorite(
    session: AsyncSession, current_user: User, stage_id: UUID
) -> None:
    await session.execute(
        delete(InterviewCatalogFavorite).where(
            InterviewCatalogFavorite.user_id == current_user.id,
            InterviewCatalogFavorite.stage_id == stage_id,
        )
    )
    await session.commit()
