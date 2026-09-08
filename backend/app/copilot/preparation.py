"""Read-only, owner-scoped sources for Copilot preparation. No release-catalog access."""

import hashlib
import json
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import StudentUser
from app.career_packages.models import CareerPackage, CareerPackageVersion
from app.career_packages.service import authorized_version
from app.core.config import get_settings
from app.core.errors import api_error
from app.db.session import get_db_session
from app.interviews.models import InterviewProcess, InterviewProcessStage
from app.mentors.models import MentorStudentDocument
from app.tracks.models import LearningTrack

router = APIRouter(prefix="/copilot/preparation", tags=["copilot-preparation"])
Session = Annotated[AsyncSession, Depends(get_db_session)]
Kind = Literal["profile", "document", "resume", "conditions", "interview"]


def source(kind: str, source_id: UUID, title: str, text: str, **meta: Any) -> dict[str, Any]:
    revision = hashlib.sha256(
        json.dumps([kind, str(source_id), text, meta], sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    return {
        "key": f"{kind}:{source_id}",
        "kind": kind,
        "id": str(source_id),
        "title": title,
        "text": text,
        "version": revision,
        **meta,
    }


@router.get("/options")
async def options(session: Session, student: StudentUser, response: Response) -> dict[str, Any]:
    response.headers["Cache-Control"] = "private, no-store"
    items: list[dict[str, Any]] = []
    docs = await session.scalars(
        select(MentorStudentDocument)
        .where(MentorStudentDocument.student_id == student.id)
        .limit(100)
    )
    for doc in docs:
        items.append(
            {
                "key": f"document:{doc.id}",
                "kind": "document",
                "id": str(doc.id),
                "title": {"resume": "Резюме", "legend": "Описание опыта"}.get(
                    doc.kind.value, doc.kind.value
                ),
                "track": "all",
                "available": bool(doc.text_content),
            }
        )
    versions = await session.execute(
        select(CareerPackageVersion, LearningTrack.slug)
        .join(CareerPackage, CareerPackage.id == CareerPackageVersion.package_id)
        .join(LearningTrack, LearningTrack.id == CareerPackage.track_id)
        .where(
            CareerPackage.student_id == student.id,
            CareerPackageVersion.provided_at.is_not(None),
            get_settings().career_package_enabled,
        )
        .order_by(CareerPackageVersion.published_at.desc())
        .limit(100)
    )
    for version, track in versions:
        for kind, title in [
            ("resume", "Опубликованное резюме"),
            ("conditions", "Условия поиска работы"),
        ]:
            items.append(
                {
                    "key": f"{kind}:{version.id}",
                    "kind": kind,
                    "id": str(version.id),
                    "title": f"{title} · {track} · v{version.version_number}",
                    "track": track,
                    "available": bool(version.snapshot.get("resume", {}).get("text_content"))
                    if kind == "resume"
                    else bool(version.snapshot.get("active_search_parameters")),
                }
            )
    processes = await session.execute(
        select(InterviewProcess, LearningTrack.slug)
        .join(LearningTrack, LearningTrack.id == InterviewProcess.track_id)
        .where(InterviewProcess.user_id == student.id)
        .order_by(InterviewProcess.updated_at.desc())
        .limit(100)
    )
    for process, track in processes:
        items.append(
            {
                "key": f"interview:{process.id}",
                "kind": "interview",
                "id": str(process.id),
                "title": process.company_name,
                "track": track,
                "available": True,
            }
        )
    return {
        "profile_id": str(student.id),
        "name": " ".join(filter(None, [student.first_name, student.last_name])),
        "sources": items,
    }


@router.get("/sources/{kind}/{source_id}")
async def read_source(
    kind: Kind, source_id: UUID, session: Session, student: StudentUser, response: Response
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "private, no-store"
    if kind == "profile":
        if source_id != student.id:
            api_error(404, "source_not_found", "Source not found")
        return source(
            kind,
            source_id,
            "Профиль",
            " ".join(filter(None, [student.first_name, student.last_name])),
            track="all",
            provenance="platform_profile",
        )
    if kind == "document":
        doc = await session.scalar(
            select(MentorStudentDocument).where(
                MentorStudentDocument.id == source_id,
                MentorStudentDocument.student_id == student.id,
            )
        )
        if doc is None:
            api_error(404, "source_not_found", "Source not found")
        return source(
            kind,
            source_id,
            "Резюме" if doc.kind.value == "resume" else "Описание опыта",
            doc.text_content or "",
            track="all",
            provenance=doc.kind.value,
            updated_at=doc.updated_at.isoformat(),
            mentor_review="not_reviewed",
        )
    if kind in {"resume", "conditions"}:
        if not get_settings().career_package_enabled:
            api_error(404, "career_package_disabled", "Career packages are not enabled")
        version = await authorized_version(session, student, source_id)
        package = await session.get(CareerPackage, version.package_id)
        assert package is not None
        track = await session.get(LearningTrack, package.track_id)
        assert track is not None
        if kind == "resume":
            text = str(version.snapshot.get("resume", {}).get("text_content") or "")
        else:
            # Published search advice is not a candidate-confirmed preference.
            text = json.dumps(
                version.snapshot.get("active_search_parameters") or {}, ensure_ascii=False, indent=2
            )
        return source(
            kind,
            source_id,
            "Опубликованное резюме" if kind == "resume" else "Условия поиска работы",
            text,
            track=track.slug,
            provenance="published_resume" if kind == "resume" else "published_search_advice",
            version_number=version.version_number,
            published_at=version.published_at.isoformat(),
            mentor_review="not_reviewed",
        )
    process = await session.scalar(
        select(InterviewProcess).where(
            InterviewProcess.id == source_id, InterviewProcess.user_id == student.id
        )
    )
    if process is None:
        api_error(404, "source_not_found", "Source not found")
    track = await session.get(LearningTrack, process.track_id)
    assert track is not None
    stages = await session.scalars(
        select(InterviewProcessStage)
        .where(InterviewProcessStage.process_id == process.id)
        .order_by(InterviewProcessStage.scheduled_at)
        .limit(100)
    )
    text = (
        process.company_name
        + "\n"
        + "\n".join(f"{s.stage_type.value}: {s.description or ''}" for s in stages)
    )
    return source(
        kind, source_id, process.company_name, text, track=track.slug, provenance="interview_plan"
    )
