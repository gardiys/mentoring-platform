"""Owner-scoped interview preparation/upload and server-attested usage."""

import hmac
from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import AdminUser, CurrentUser, StudentUser
from app.copilot.access import eligibility, ensure_copilot_student
from app.copilot.models import CopilotSession
from app.core.config import get_settings
from app.core.errors import api_error
from app.db.session import get_db_session
from app.interviews.catalog_service import catalog_company_detail
from app.interviews.journal_router import (
    journal_company_suggestions,
    journal_complete_stage_media_upload,
    journal_create_stage_media_upload,
)
from app.interviews.journal_service import (
    create_process,
    get_process_model,
    list_interview_directions,
    list_processes,
    process_detail,
    update_stage,
)
from app.interviews.models import InterviewProcess, InterviewProcessStage, InterviewProcessStatus
from app.interviews.schemas import (
    InterviewProcessMutation,
    InterviewProcessStageMutation,
    InterviewUploadComplete,
    InterviewUploadIntentResponse,
    InterviewUploadRequest,
)
from app.users.models import User, UserRole

router = APIRouter(prefix="/copilot", tags=["copilot-interviews"])
Session = Annotated[AsyncSession, Depends(get_db_session)]
Tenant = Annotated[str, Header(alias="X-Copilot-Tenant", min_length=1, max_length=100)]


async def permitted_student(session: Session, user: StudentUser) -> User:
    await ensure_copilot_student(session, user)
    return user


CopilotUser = Annotated[User, Depends(permitted_student)]


@router.get("/access")
async def access(session: Session, user: CurrentUser, response: Response) -> dict[str, object]:
    response.headers["Cache-Control"] = "private, no-store"
    return {
        "id": str(user.id),
        "role": user.role.value,
        "is_active": user.is_active,
        **await eligibility(session, user),
    }


@router.get("/tracks")
async def tracks(session: Session, user: CopilotUser) -> dict[str, Any]:
    return {
        "tracks": await list_processes(session, user, None),
        "directions": await list_interview_directions(session, user),
    }


@router.get("/companies")
async def companies(
    session: Session, user: CopilotUser, q: str = Query(min_length=1, max_length=240)
) -> Any:
    return await journal_company_suggestions(session, user, q, 8)


@router.post("/tracks", status_code=201)
async def create_track(
    payload: InterviewProcessMutation, session: Session, user: CopilotUser
) -> Any:
    return await create_process(session, user, payload)


def normalized(value: str | None) -> str:
    return " ".join((value or "").casefold().split())


@router.get("/tracks/{process_id}/context")
async def track_context(
    process_id: UUID, session: Session, user: CopilotUser, stage_type: str = "technical_interview"
) -> dict[str, Any]:
    process = await get_process_model(session, user, process_id)
    detail = await process_detail(session, user, process_id)
    # Use exactly the existing public catalog policy, including anonymous-author
    # redaction. Never read another student's raw transcript, feedback or documents.
    catalog = await catalog_company_detail(
        session, user, process.company_id, track_id=process.track_id
    )
    peers = []
    if normalized(process.team_name):
        candidates = list(
            (
                await session.scalars(
                    select(InterviewProcess).where(
                        InterviewProcess.id.in_([p.id for p in catalog.tracks]),
                        InterviewProcess.user_id != user.id,
                    )
                )
            ).all()
        )
        same_team = {
            p.id
            for p in candidates
            if normalized(p.team_name) == normalized(process.team_name)
            and (
                not process.position_name
                or normalized(p.position_name) == normalized(process.position_name)
            )
        }
        for other in sorted(catalog.tracks, key=lambda p: p.updated_at, reverse=True):
            if other.id not in same_team:
                continue
            for stage in other.stages:
                if (
                    stage.stage_type.value != stage_type
                    or not stage.description
                    or stage.scheduled_at > datetime.now(UTC)
                ):
                    continue
                peers.append(
                    {
                        "stage_type": stage.stage_type.value,
                        "date": stage.scheduled_at.isoformat(),
                        "description": stage.description[:1500],
                        "source": "platform_catalog",
                        "relevance": "same_team_direction_and_stage",
                        "candidate_experience": False,
                    }
                )
    previous = [
        {
            "id": str(s.id),
            "stage_type": s.stage_type.value,
            "date": s.scheduled_at.isoformat(),
            "description": (s.description or "")[:2000],
            "feedback": [
                {
                    "body": c.body[:1500],
                    "source": "mentor" if c.is_mentor_feedback else "platform_ai",
                }
                for c in s.comments
                if c.is_mentor_feedback or c.is_ai_feedback
            ][:2],
        }
        for s in sorted(detail.stages, key=lambda s: s.scheduled_at, reverse=True)
        if s.scheduled_at <= datetime.now(UTC)
    ][:8]
    return {
        "process": detail.model_dump(mode="json"),
        "context": {
            "company": process.company_name,
            "team": process.team_name,
            "position": process.position_name,
            "company_notes": (process.company_notes or "")[:4000],
            "previous_interviews": previous,
            "peer_examples": peers[:5],
            "policy": (
                "Use only as background. Other candidates' interviews are not this candidate's "
                "biography or a prediction of questions. Team, role, stage and date matter. "
                "Current interviewer speech takes priority."
            ),
        },
        "peer_note": ("Учтены доступные описания того же направления, команды, роли и типа этапа.")
        if process.team_name
        else "Команда не указана: опыт других учеников не подмешивается.",
    }


class UsageSnapshot(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=100)
    session_id: UUID
    student_id: UUID
    process_id: UUID | None = None
    mode: Literal["real", "mock"]
    track: Literal["python", "go"]
    state: Literal["active", "paused", "finishing", "completed", "deleted"]
    started_at: datetime
    finished_at: datetime | None = None
    active_ms: int = Field(ge=0, le=604_800_000)
    revision: int = Field(ge=1)

    @model_validator(mode="after")
    def valid_duration(self) -> "UsageSnapshot":
        if self.started_at.tzinfo is None or (self.finished_at and self.finished_at.tzinfo is None):
            raise ValueError("Timezone required")
        end = self.finished_at or datetime.now(UTC)
        if (
            end < self.started_at
            or self.active_ms > (end - self.started_at).total_seconds() * 1000 + 2000
        ):
            raise ValueError("Invalid active duration")
        if self.mode != "real" and self.process_id:
            raise ValueError("Mock interviews cannot belong to a company process")
        return self


@router.post("/internal/sessions")
async def sync_usage(
    payload: UsageSnapshot, session: Session, authorization: Annotated[str, Header()]
) -> dict[str, bool]:
    secret = get_settings().copilot_integration_token
    expected = secret.get_secret_value() if secret else ""
    if not expected or not hmac.compare_digest(authorization, "Bearer " + expected):
        api_error(403, "copilot_integration_denied", "Server credential required")
    user = await session.get(User, payload.student_id)
    if user is None or user.role is not UserRole.STUDENT:
        api_error(404, "student_not_found", "Student not found")
    if payload.process_id:
        await get_process_model(session, user, payload.process_id)
    old = await session.get(CopilotSession, (payload.tenant_id, payload.session_id))
    if old and (old.student_id != payload.student_id or old.started_at != payload.started_at):
        api_error(409, "copilot_session_conflict", "Session identity cannot change")
    statement = insert(CopilotSession).values(**payload.model_dump())
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[CopilotSession.tenant_id, CopilotSession.session_id],
            set_={
                key: getattr(statement.excluded, key)
                for key in ["process_id", "state", "finished_at", "active_ms", "revision"]
            },
            where=(CopilotSession.revision < statement.excluded.revision)
            & (CopilotSession.active_ms <= statement.excluded.active_ms)
            & (CopilotSession.student_id == statement.excluded.student_id),
        )
    )
    await session.commit()
    return {"synced": True}


async def owned_record(
    session: AsyncSession, user: User, tenant: str, sid: UUID, *, lock: bool = False
) -> CopilotSession:
    query = select(CopilotSession).where(
        CopilotSession.tenant_id == tenant,
        CopilotSession.session_id == sid,
        CopilotSession.student_id == user.id,
    )
    if lock:
        query = query.with_for_update()
    record = await session.scalar(query)
    if record is None:
        api_error(
            404, "copilot_session_not_found", "Интервью ещё не синхронизировано. Повтори загрузку."
        )
    return record


@router.post("/sessions/{session_id}/stage")
async def create_record_stage(
    session_id: UUID,
    payload: InterviewProcessStageMutation,
    session: Session,
    user: CopilotUser,
    x_copilot_tenant: Tenant,
) -> dict[str, Any]:
    record = await owned_record(session, user, x_copilot_tenant, session_id, lock=True)
    if record.mode != "real" or not record.process_id or record.state != "completed":
        api_error(
            409,
            "copilot_upload_not_ready",
            "Загружать можно завершённые реальные интервью с выбранным треком.",
        )
    process = await get_process_model(session, user, record.process_id)
    if record.stage_id:
        # Retry returns the same stage. Once media exists, never overwrite it.
        stage = await session.get(InterviewProcessStage, record.stage_id)
        if stage and not stage.media_storage_key:
            await update_stage(session, user, process.id, stage.id, payload)
    else:
        if process.status is not InterviewProcessStatus.ACTIVE:
            api_error(
                409, "interview_process_not_active", "Открой трек на платформе перед загрузкой."
            )
        stage = InterviewProcessStage(process_id=process.id, **payload.model_dump())
        session.add(stage)
        await session.flush()
        record.stage_id = stage.id
        await session.commit()
    return {
        "process_id": str(process.id),
        "stage_id": str(record.stage_id),
        "uploaded": bool(stage and stage.media_storage_key),
    }


@router.post("/sessions/{session_id}/media/upload", response_model=InterviewUploadIntentResponse)
async def upload_media(
    session_id: UUID,
    payload: InterviewUploadRequest,
    session: Session,
    user: CopilotUser,
    x_copilot_tenant: Tenant,
) -> Any:
    record = await owned_record(session, user, x_copilot_tenant, session_id)
    if not record.process_id or not record.stage_id:
        api_error(409, "copilot_stage_required", "Сначала укажи данные этапа.")
    stage = await session.get(InterviewProcessStage, record.stage_id)
    if stage and stage.media_storage_key:
        api_error(409, "copilot_already_uploaded", "Запись уже загружена.")
    return await journal_create_stage_media_upload(
        record.process_id, record.stage_id, payload, session, user
    )


@router.post("/sessions/{session_id}/media/complete")
async def complete_media(
    session_id: UUID,
    payload: InterviewUploadComplete,
    session: Session,
    user: CopilotUser,
    x_copilot_tenant: Tenant,
) -> dict[str, str]:
    record = await owned_record(session, user, x_copilot_tenant, session_id, lock=True)
    if not record.process_id or not record.stage_id:
        api_error(409, "copilot_stage_required", "Сначала укажи данные этапа.")
    stage = await session.get(InterviewProcessStage, record.stage_id)
    if stage and stage.media_storage_key != payload.storage_key:
        if stage.media_storage_key:
            api_error(409, "copilot_already_uploaded", "У этого интервью уже есть другая запись.")
        await journal_complete_stage_media_upload(
            record.process_id, record.stage_id, payload, session, user
        )
    return {
        "process_id": str(record.process_id),
        "stage_id": str(record.stage_id),
        "status": "uploaded",
    }


@router.get("/usage")
async def usage(
    session: Session,
    user: AdminUser,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
) -> dict[str, Any]:
    total = await session.scalar(
        select(func.count()).select_from(User).where(User.role == UserRole.STUDENT)
    )
    students = list(
        (
            await session.scalars(
                select(User)
                .where(User.role == UserRole.STUDENT)
                .order_by(User.id)
                .offset(offset)
                .limit(limit)
            )
        ).all()
    )
    rows = []
    for student in students:
        records = list(
            (
                await session.scalars(
                    select(CopilotSession).where(CopilotSession.student_id == student.id)
                )
            ).all()
        )
        rows.append(
            {
                "student_id": str(student.id),
                "name": " ".join(filter(None, [student.first_name, student.last_name])),
                "is_active": student.is_active,
                **await eligibility(session, student),
                "interviews_completed": sum(r.state == "completed" for r in records),
                "real_completed": sum(r.state == "completed" and r.mode == "real" for r in records),
                "mock_completed": sum(r.state == "completed" and r.mode == "mock" for r in records),
                "sessions_started": len(records),
                "active_ms": sum(r.active_ms for r in records),
                "last_interview_at": max((r.started_at for r in records), default=None),
            }
        )
    return {"students": rows, "total": total, "offset": offset, "limit": limit}
