from __future__ import annotations

from uuid import UUID

from sqlalchemy import ColumnElement, distinct, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.errors import api_error
from app.interviews.companies import suggest_companies
from app.interviews.models import (
    Company,
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
    InterviewCatalogMediaKind,
    InterviewCatalogStageRead,
    InterviewCatalogTrackRead,
    InterviewDirectionOption,
    InterviewStageAttachmentRead,
)
from app.tracks.models import LearningTrack, LearningTrackEnrollment
from app.users.models import User


def _catalog_process_filters(
    *,
    author_id: UUID | None,
    track_id: UUID | None,
    stage_type: InterviewStageType | None,
    has_offer: bool,
    media_kind: InterviewCatalogMediaKind | None,
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
    return conditions


def _student_direction_filter(user_id: UUID) -> ColumnElement[bool]:
    return exists(
        select(1)
        .select_from(LearningTrackEnrollment)
        .where(
            LearningTrackEnrollment.user_id == user_id,
            LearningTrackEnrollment.track_id == InterviewProcess.track_id,
        )
    )


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
    comment: InterviewStageComment, author: User, current_user: User
) -> InterviewCatalogCommentRead:
    return InterviewCatalogCommentRead(
        id=comment.id,
        author=_author(author),
        body=comment.body,
        is_own=comment.user_id == current_user.id,
        is_mentor_feedback=author.role.value in {"mentor", "admin"},
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
) -> list[InterviewCatalogCompanyListItem]:
    candidate_ids: list[UUID] | None = None
    if query and query.strip():
        candidates = await suggest_companies(session, query, 100)
        candidate_ids = [company.id for company in candidates]
        if not candidate_ids:
            return []

    statement = (
        select(
            Company,
            func.count(distinct(InterviewProcess.id)),
            func.count(InterviewProcessStage.id),
            func.max(InterviewProcessStage.scheduled_at),
        )
        .join(InterviewProcess, InterviewProcess.company_id == Company.id)
        .outerjoin(
            InterviewProcessStage,
            InterviewProcessStage.process_id == InterviewProcess.id,
        )
        .group_by(Company.id)
        .where(
            _student_direction_filter(current_user.id),
            *_catalog_process_filters(
                author_id=author_id,
                track_id=track_id,
                stage_type=stage_type,
                has_offer=has_offer,
                media_kind=media_kind,
            ),
        )
    )
    if candidate_ids is not None:
        statement = statement.where(Company.id.in_(candidate_ids))
    else:
        statement = statement.order_by(
            func.max(InterviewProcessStage.scheduled_at).desc().nullslast(),
            Company.name,
        )
    rows = (await session.execute(statement)).all()
    items = {
        company.id: InterviewCatalogCompanyListItem(
            id=company.id,
            name=company.name,
            track_count=track_count,
            interview_count=interview_count,
            last_interview_at=last_interview_at,
        )
        for company, track_count, interview_count, last_interview_at in rows
    }
    if candidate_ids is not None:
        return [items[company_id] for company_id in candidate_ids if company_id in items]
    return list(items.values())


async def list_catalog_directions(
    session: AsyncSession, current_user: User
) -> list[InterviewDirectionOption]:
    tracks = list(
        await session.scalars(
            select(LearningTrack)
            .join(
                LearningTrackEnrollment,
                LearningTrackEnrollment.track_id == LearningTrack.id,
            )
            .where(
                LearningTrackEnrollment.user_id == current_user.id,
                LearningTrack.is_published.is_(True),
            )
            .order_by(LearningTrack.position, LearningTrack.title)
        )
    )
    return [
        InterviewDirectionOption(id=track.id, slug=track.slug, title=track.title)
        for track in tracks
    ]


async def list_catalog_authors(
    session: AsyncSession, current_user: User
) -> list[InterviewCatalogAuthorRead]:
    authors = list(
        await session.scalars(
            select(User)
            .join(InterviewProcess, InterviewProcess.user_id == User.id)
            .where(_student_direction_filter(current_user.id))
            .distinct()
            .order_by(User.first_name, User.telegram_username, User.id)
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
                    _student_direction_filter(current_user.id),
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
                _student_direction_filter(current_user.id),
                *_catalog_process_filters(
                    author_id=author_id,
                    track_id=track_id,
                    stage_type=stage_type,
                    has_offer=has_offer,
                    media_kind=media_kind,
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
                .where(InterviewProcessStage.process_id.in_(process_ids))
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
                .join(User, User.id == InterviewStageComment.user_id)
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
    comments_by_stage: dict[UUID, list[tuple[InterviewStageComment, User]]] = {
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
            _student_direction_filter(current_user.id),
        )
    )
    if stage is None:
        api_error(404, "interview_catalog_stage_not_found", "Interview was not found")
    return stage


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
