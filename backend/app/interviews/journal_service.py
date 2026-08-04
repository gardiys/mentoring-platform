from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import api_error
from app.interviews.companies import resolve_company
from app.interviews.intelligence_models import IntelligenceInterview
from app.interviews.models import (
    InterviewProcess,
    InterviewProcessStage,
    InterviewProcessStageAttachment,
    InterviewProcessStatus,
    InterviewStageComment,
)
from app.interviews.schemas import (
    AdminInterviewProcessPage,
    AdminInterviewProcessSummary,
    InterviewAttachmentRead,
    InterviewCatalogAuthorRead,
    InterviewCatalogCommentRead,
    InterviewDirectionOption,
    InterviewProcessDetail,
    InterviewProcessMutation,
    InterviewProcessOutcomeMutation,
    InterviewProcessRecruitersMutation,
    InterviewProcessStageMutation,
    InterviewProcessStageRead,
    InterviewProcessSummary,
    InterviewStageAttachmentRead,
)
from app.interviews.uploads import StoredUpload
from app.tracks.access import accessible_track_ids
from app.tracks.models import LearningTrack
from app.users.models import User, UserRole


def _attachment(
    filename: str | None, content_type: str | None, size: int | None
) -> InterviewAttachmentRead | None:
    if filename is None or content_type is None or size is None:
        return None
    return InterviewAttachmentRead(
        filename=filename,
        content_type=content_type,
        size=size,
    )


MAX_STAGE_ATTACHMENTS = 20


def _stage_attachment_read(
    attachment: InterviewProcessStageAttachment,
) -> InterviewStageAttachmentRead:
    return InterviewStageAttachmentRead(
        id=attachment.id,
        filename=attachment.filename,
        content_type=attachment.content_type,
        size=attachment.size,
        created_at=attachment.created_at,
    )


def _stage_read(
    stage: InterviewProcessStage,
    attachments: list[InterviewProcessStageAttachment],
    comments: list[tuple[InterviewStageComment, User | None]],
    analysis: IntelligenceInterview | None,
    current_user: User,
) -> InterviewProcessStageRead:
    return InterviewProcessStageRead(
        id=stage.id,
        stage_type=stage.stage_type,
        scheduled_at=stage.scheduled_at,
        description=stage.description,
        media=_attachment(
            stage.media_filename,
            stage.media_content_type,
            stage.media_size,
        ),
        attachments=[_stage_attachment_read(attachment) for attachment in attachments],
        comments=[
            InterviewCatalogCommentRead(
                id=comment.id,
                author=(
                    InterviewCatalogAuthorRead(
                        id=author.id,
                        name=author.first_name,
                        telegram_username=author.telegram_username,
                    )
                    if author is not None
                    else None
                ),
                body=comment.body,
                is_own=comment.user_id == current_user.id,
                is_mentor_feedback=(
                    author is not None and author.role.value in {"mentor", "admin"}
                ),
                is_ai_feedback=comment.is_ai_feedback,
                created_at=comment.created_at,
                updated_at=comment.updated_at,
            )
            for comment, author in comments
        ],
        ai_analysis_id=analysis.id if analysis else None,
        ai_analysis_status=analysis.processing_status if analysis else None,
        ai_analysis_requested_at=stage.ai_analysis_requested_at,
        created_at=stage.created_at,
        updated_at=stage.updated_at,
    )


def _summary(
    process: InterviewProcess,
    track: LearningTrack,
    stage_count: int,
    next_stage_at: datetime | None,
) -> InterviewProcessSummary:
    return InterviewProcessSummary(
        id=process.id,
        company_name=process.company_name,
        recruiter_telegram_usernames=process.recruiter_telegram_usernames,
        track_id=track.id,
        track_slug=track.slug,
        track_title=track.title,
        status=process.status,
        close_reason=process.close_reason,
        closed_at=process.closed_at,
        stage_count=stage_count,
        next_stage_at=next_stage_at,
        has_offer_file=process.offer_storage_key is not None,
        created_at=process.created_at,
        updated_at=process.updated_at,
    )


async def list_interview_directions(
    session: AsyncSession,
    user: User,
) -> list[InterviewDirectionOption]:
    track_ids = await accessible_track_ids(session, user)
    tracks = list(
        await session.scalars(
            select(LearningTrack)
            .where(
                LearningTrack.is_published.is_(True),
                LearningTrack.id.in_(track_ids),
            )
            .order_by(LearningTrack.position, LearningTrack.title)
        )
    )
    return [
        InterviewDirectionOption(id=track.id, slug=track.slug, title=track.title)
        for track in tracks
    ]


async def _get_interview_direction(
    session: AsyncSession, user: User, track_id: UUID
) -> LearningTrack:
    track_ids = await accessible_track_ids(session, user)
    track = await session.scalar(
        select(LearningTrack).where(
            LearningTrack.id == track_id,
            LearningTrack.is_published.is_(True),
            LearningTrack.id.in_(track_ids),
        )
    )
    if track is None:
        api_error(
            422,
            "interview_direction_not_available",
            "Selected interview direction is not available",
        )
    return track


async def get_process_model(
    session: AsyncSession,
    user: User,
    process_id: UUID,
    *,
    lock: bool = False,
) -> InterviewProcess:
    statement = select(InterviewProcess).where(
        InterviewProcess.id == process_id,
        InterviewProcess.user_id == user.id,
    )
    if lock:
        statement = statement.with_for_update()
    process = await session.scalar(statement)
    if process is None:
        api_error(404, "interview_process_not_found", "Interview process was not found")
    return process


async def get_stage_model(
    session: AsyncSession,
    user: User,
    process_id: UUID,
    stage_id: UUID,
    *,
    lock: bool = False,
) -> InterviewProcessStage:
    statement = (
        select(InterviewProcessStage)
        .join(InterviewProcess, InterviewProcess.id == InterviewProcessStage.process_id)
        .where(
            InterviewProcessStage.id == stage_id,
            InterviewProcessStage.process_id == process_id,
            InterviewProcess.user_id == user.id,
        )
    )
    if lock:
        statement = statement.with_for_update()
    stage = await session.scalar(statement)
    if stage is None:
        api_error(404, "interview_stage_not_found", "Interview stage was not found")
    return stage


async def get_stage_attachment_model(
    session: AsyncSession,
    user: User,
    process_id: UUID,
    stage_id: UUID,
    attachment_id: UUID,
    *,
    lock: bool = False,
) -> InterviewProcessStageAttachment:
    statement = (
        select(InterviewProcessStageAttachment)
        .join(
            InterviewProcessStage,
            InterviewProcessStage.id == InterviewProcessStageAttachment.stage_id,
        )
        .join(InterviewProcess, InterviewProcess.id == InterviewProcessStage.process_id)
        .where(
            InterviewProcessStageAttachment.id == attachment_id,
            InterviewProcessStageAttachment.stage_id == stage_id,
            InterviewProcessStage.process_id == process_id,
            InterviewProcess.user_id == user.id,
        )
    )
    if lock:
        statement = statement.with_for_update()
    attachment = await session.scalar(statement)
    if attachment is None:
        api_error(
            404,
            "interview_attachment_not_found",
            "Interview attachment was not found",
        )
    return attachment


async def ensure_stage_attachment_capacity(
    session: AsyncSession, user: User, process_id: UUID, stage_id: UUID
) -> None:
    await get_stage_model(session, user, process_id, stage_id)
    count = await session.scalar(
        select(func.count(InterviewProcessStageAttachment.id)).where(
            InterviewProcessStageAttachment.stage_id == stage_id
        )
    )
    if (count or 0) >= MAX_STAGE_ATTACHMENTS:
        api_error(
            409,
            "interview_attachment_limit_reached",
            f"An interview stage can have at most {MAX_STAGE_ATTACHMENTS} attachments",
        )


async def list_processes(
    session: AsyncSession,
    user: User,
    status: InterviewProcessStatus | None,
    track_ids: set[UUID] | None = None,
) -> list[InterviewProcessSummary]:
    now = datetime.now(UTC)
    statement = (
        select(
            InterviewProcess,
            LearningTrack,
            func.count(InterviewProcessStage.id),
            func.min(
                case(
                    (InterviewProcessStage.scheduled_at >= now, InterviewProcessStage.scheduled_at),
                    else_=None,
                )
            ),
        )
        .outerjoin(
            InterviewProcessStage,
            InterviewProcessStage.process_id == InterviewProcess.id,
        )
        .join(LearningTrack, LearningTrack.id == InterviewProcess.track_id)
        .where(InterviewProcess.user_id == user.id)
        .group_by(InterviewProcess.id, LearningTrack.id)
        .order_by(
            case((InterviewProcess.status == InterviewProcessStatus.ACTIVE, 0), else_=1),
            InterviewProcess.updated_at.desc(),
        )
    )
    if status is not None:
        statement = statement.where(InterviewProcess.status == status)
    if track_ids is not None:
        statement = statement.where(InterviewProcess.track_id.in_(track_ids))
    rows = (await session.execute(statement)).all()
    return [_summary(process, track, count, next_at) for process, track, count, next_at in rows]


async def list_admin_processes(
    session: AsyncSession,
    status: InterviewProcessStatus | None,
    *,
    limit: int,
    offset: int,
) -> AdminInterviewProcessPage:
    now = datetime.now(UTC)
    statement = (
        select(
            InterviewProcess,
            User,
            LearningTrack,
            func.count(InterviewProcessStage.id),
            func.min(
                case(
                    (InterviewProcessStage.scheduled_at >= now, InterviewProcessStage.scheduled_at),
                    else_=None,
                )
            ),
        )
        .join(User, User.id == InterviewProcess.user_id)
        .join(LearningTrack, LearningTrack.id == InterviewProcess.track_id)
        .outerjoin(
            InterviewProcessStage,
            InterviewProcessStage.process_id == InterviewProcess.id,
        )
        .group_by(InterviewProcess.id, User.id, LearningTrack.id)
        .order_by(
            case((InterviewProcess.status == InterviewProcessStatus.ACTIVE, 0), else_=1),
            InterviewProcess.updated_at.desc(),
        )
    )
    if status is not None:
        statement = statement.where(InterviewProcess.status == status)
    total = int(
        await session.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))
        or 0
    )
    rows = (await session.execute(statement.limit(limit).offset(offset))).all()
    items = [
        AdminInterviewProcessSummary(
            **_summary(process, track, count, next_at).model_dump(),
            company_id=process.company_id,
            author=InterviewCatalogAuthorRead(
                id=author.id,
                name=author.first_name,
                telegram_username=author.telegram_username,
            ),
        )
        for process, author, track, count, next_at in rows
    ]
    return AdminInterviewProcessPage(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


async def process_detail(
    session: AsyncSession, user: User, process_id: UUID
) -> InterviewProcessDetail:
    process = await get_process_model(session, user, process_id)
    track = await session.get(LearningTrack, process.track_id)
    if track is None:
        api_error(500, "interview_direction_missing", "Interview direction was not found")
    stages = list(
        await session.scalars(
            select(InterviewProcessStage)
            .where(InterviewProcessStage.process_id == process.id)
            .order_by(InterviewProcessStage.scheduled_at, InterviewProcessStage.created_at)
        )
    )
    attachments_by_stage: dict[UUID, list[InterviewProcessStageAttachment]] = {
        stage.id: [] for stage in stages
    }
    if stages:
        attachments = list(
            await session.scalars(
                select(InterviewProcessStageAttachment)
                .where(InterviewProcessStageAttachment.stage_id.in_([stage.id for stage in stages]))
                .order_by(InterviewProcessStageAttachment.created_at)
            )
        )
        for attachment in attachments:
            attachments_by_stage[attachment.stage_id].append(attachment)
    comments_by_stage: dict[UUID, list[tuple[InterviewStageComment, User | None]]] = {
        stage.id: [] for stage in stages
    }
    analyses_by_stage: dict[UUID, IntelligenceInterview] = {}
    if stages:
        stage_ids = [stage.id for stage in stages]
        comment_rows = (
            await session.execute(
                select(InterviewStageComment, User)
                .outerjoin(User, User.id == InterviewStageComment.user_id)
                .where(InterviewStageComment.stage_id.in_(stage_ids))
                .order_by(InterviewStageComment.created_at)
            )
        ).all()
        for comment, author in comment_rows:
            comments_by_stage[comment.stage_id].append((comment, author))
        analyses = list(
            await session.scalars(
                select(IntelligenceInterview).where(IntelligenceInterview.stage_id.in_(stage_ids))
            )
        )
        analyses_by_stage = {analysis.stage_id: analysis for analysis in analyses}
    now = datetime.now(UTC)
    next_stage_at = next(
        (stage.scheduled_at for stage in stages if stage.scheduled_at >= now),
        None,
    )
    summary = _summary(process, track, len(stages), next_stage_at)
    return InterviewProcessDetail(
        **summary.model_dump(),
        stages=[
            _stage_read(
                stage,
                attachments_by_stage[stage.id],
                comments_by_stage[stage.id],
                analyses_by_stage.get(stage.id),
                user,
            )
            for stage in stages
        ],
        offer=_attachment(
            process.offer_filename,
            process.offer_content_type,
            process.offer_size,
        ),
    )


async def create_process(
    session: AsyncSession, user: User, payload: InterviewProcessMutation
) -> InterviewProcessDetail:
    track = await _get_interview_direction(session, user, payload.track_id)
    company = await resolve_company(
        session,
        payload.company_name,
        company_id=payload.company_id,
        raw_alias=payload.company_alias,
        allow_company_merge=user.role is UserRole.ADMIN,
    )
    process = InterviewProcess(
        user_id=user.id,
        track_id=track.id,
        company_id=company.id,
        company_name=company.name,
        recruiter_telegram_usernames=payload.recruiter_telegram_usernames or [],
    )
    session.add(process)
    await session.commit()
    return await process_detail(session, user, process.id)


async def update_process(
    session: AsyncSession,
    user: User,
    process_id: UUID,
    payload: InterviewProcessMutation,
) -> InterviewProcessDetail:
    process = await get_process_model(session, user, process_id, lock=True)
    track = await _get_interview_direction(session, user, payload.track_id)
    company = await resolve_company(
        session,
        payload.company_name,
        company_id=payload.company_id,
        raw_alias=payload.company_alias,
        allow_company_merge=user.role is UserRole.ADMIN,
    )
    process.company_id = company.id
    process.company_name = company.name
    process.track_id = track.id
    if payload.recruiter_telegram_usernames is not None:
        process.recruiter_telegram_usernames = payload.recruiter_telegram_usernames
    await session.commit()
    return await process_detail(session, user, process.id)


async def set_process_recruiters(
    session: AsyncSession,
    user: User,
    process_id: UUID,
    payload: InterviewProcessRecruitersMutation,
) -> InterviewProcessDetail:
    process = await get_process_model(session, user, process_id, lock=True)
    process.recruiter_telegram_usernames = payload.recruiter_telegram_usernames
    await session.commit()
    return await process_detail(session, user, process.id)


async def set_process_outcome(
    session: AsyncSession,
    user: User,
    process_id: UUID,
    payload: InterviewProcessOutcomeMutation,
) -> InterviewProcessDetail:
    process = await get_process_model(session, user, process_id, lock=True)
    if (
        process.status is InterviewProcessStatus.OFFER
        and payload.status is InterviewProcessStatus.ACTIVE
    ):
        api_error(
            409,
            "interview_offer_requires_cancellation",
            "Cancel the offer to reopen this interview process",
        )
    process.status = payload.status
    # Keep the latest rejection in the process history when it is reopened or
    # later results in an offer. A new closure replaces it with the new reason.
    if payload.status is InterviewProcessStatus.CLOSED:
        process.close_reason = payload.close_reason
        process.closed_at = datetime.now(UTC)
    await session.commit()
    return await process_detail(session, user, process.id)


async def create_stage(
    session: AsyncSession,
    user: User,
    process_id: UUID,
    payload: InterviewProcessStageMutation,
) -> InterviewProcessDetail:
    process = await get_process_model(session, user, process_id)
    if process.status is not InterviewProcessStatus.ACTIVE:
        api_error(409, "interview_process_not_active", "Interview process is not active")
    session.add(
        InterviewProcessStage(
            process_id=process.id,
            stage_type=payload.stage_type,
            scheduled_at=payload.scheduled_at,
            description=payload.description or None,
        )
    )
    await session.commit()
    return await process_detail(session, user, process.id)


async def update_stage(
    session: AsyncSession,
    user: User,
    process_id: UUID,
    stage_id: UUID,
    payload: InterviewProcessStageMutation,
) -> InterviewProcessDetail:
    stage = await get_stage_model(session, user, process_id, stage_id, lock=True)
    stage.stage_type = payload.stage_type
    stage.scheduled_at = payload.scheduled_at
    stage.description = payload.description or None
    await session.commit()
    return await process_detail(session, user, process_id)


async def set_stage_media(
    session: AsyncSession,
    user: User,
    process_id: UUID,
    stage_id: UUID,
    upload: StoredUpload,
) -> tuple[InterviewProcessDetail, str | None]:
    stage = await get_stage_model(session, user, process_id, stage_id, lock=True)
    previous_key = stage.media_storage_key
    if previous_key == upload.storage_key:
        return await process_detail(session, user, process_id), previous_key
    if stage.ai_analysis_requested_at is not None:
        api_error(
            409,
            "interview_recording_locked_for_ai_analysis",
            "The recording cannot be replaced after AI analysis was requested",
        )
    stage.media_storage_key = upload.storage_key
    stage.media_filename = upload.filename
    stage.media_content_type = upload.content_type
    stage.media_size = upload.size
    await session.commit()
    return await process_detail(session, user, process_id), previous_key


async def clear_stage_media(
    session: AsyncSession, user: User, process_id: UUID, stage_id: UUID
) -> tuple[InterviewProcessDetail, str | None]:
    stage = await get_stage_model(session, user, process_id, stage_id, lock=True)
    if stage.ai_analysis_requested_at is not None:
        api_error(
            409,
            "interview_recording_locked_for_ai_analysis",
            "The recording cannot be deleted after AI analysis was requested",
        )
    previous_key = stage.media_storage_key
    stage.media_storage_key = None
    stage.media_filename = None
    stage.media_content_type = None
    stage.media_size = None
    await session.commit()
    return await process_detail(session, user, process_id), previous_key


async def add_stage_attachment(
    session: AsyncSession,
    user: User,
    process_id: UUID,
    stage_id: UUID,
    upload: StoredUpload,
) -> InterviewProcessDetail:
    await get_stage_model(session, user, process_id, stage_id, lock=True)
    existing = await session.scalar(
        select(InterviewProcessStageAttachment.id).where(
            InterviewProcessStageAttachment.stage_id == stage_id,
            InterviewProcessStageAttachment.storage_key == upload.storage_key,
        )
    )
    if existing is not None:
        return await process_detail(session, user, process_id)
    count = await session.scalar(
        select(func.count(InterviewProcessStageAttachment.id)).where(
            InterviewProcessStageAttachment.stage_id == stage_id
        )
    )
    if (count or 0) >= MAX_STAGE_ATTACHMENTS:
        api_error(
            409,
            "interview_attachment_limit_reached",
            f"An interview stage can have at most {MAX_STAGE_ATTACHMENTS} attachments",
        )
    session.add(
        InterviewProcessStageAttachment(
            stage_id=stage_id,
            storage_key=upload.storage_key,
            filename=upload.filename,
            content_type=upload.content_type,
            size=upload.size,
        )
    )
    await session.commit()
    return await process_detail(session, user, process_id)


async def clear_stage_attachment(
    session: AsyncSession,
    user: User,
    process_id: UUID,
    stage_id: UUID,
    attachment_id: UUID,
) -> tuple[InterviewProcessDetail, str]:
    attachment = await get_stage_attachment_model(
        session,
        user,
        process_id,
        stage_id,
        attachment_id,
        lock=True,
    )
    storage_key = attachment.storage_key
    await session.delete(attachment)
    await session.commit()
    return await process_detail(session, user, process_id), storage_key


async def set_offer_file(
    session: AsyncSession,
    user: User,
    process_id: UUID,
    upload: StoredUpload,
) -> tuple[InterviewProcessDetail, str | None]:
    process = await get_process_model(session, user, process_id, lock=True)
    if process.status is not InterviewProcessStatus.OFFER:
        api_error(409, "interview_offer_not_marked", "Mark the process as an offer first")
    previous_key = process.offer_storage_key
    process.offer_storage_key = upload.storage_key
    process.offer_filename = upload.filename
    process.offer_content_type = upload.content_type
    process.offer_size = upload.size
    await session.commit()
    return await process_detail(session, user, process_id), previous_key


async def cancel_offer(
    session: AsyncSession, user: User, process_id: UUID
) -> tuple[InterviewProcessDetail, str | None]:
    process = await get_process_model(session, user, process_id, lock=True)
    if process.status is not InterviewProcessStatus.OFFER:
        api_error(409, "interview_offer_not_marked", "The process has no offer to cancel")
    previous_key = process.offer_storage_key
    process.status = InterviewProcessStatus.ACTIVE
    process.offer_storage_key = None
    process.offer_filename = None
    process.offer_content_type = None
    process.offer_size = None
    await session.commit()
    return await process_detail(session, user, process_id), previous_key
