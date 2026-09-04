from datetime import UTC, datetime
from uuid import UUID, uuid4

from httpx import AsyncClient
from pydantic import SecretStr
from pytest import MonkeyPatch
from sqlalchemy import func, select

from app.auth import dependencies as auth_dependencies
from app.auth.web_session import create_browser_session
from app.interviews.models import (
    Company,
    InterviewMediaAnonymizationStatus,
    InterviewProcess,
    InterviewProcessStage,
    InterviewStageType,
)
from app.mentors.models import MentorStudent, StudentLearningStatus
from app.roadmaps.models import RoadmapEnrollment
from app.students import service as student_service
from app.tracks.models import LearningTrackEnrollment
from app.users.models import User, UserRole
from tests.conftest import SeededData, TestSession, auth


def student_payload(
    data: SeededData,
    *,
    telegram_id: int = 777000111,
    first_name: str = "Мария",
    telegram_username: str | None = None,
    track_ids: list[str] | None = None,
) -> dict[str, object]:
    return {
        "telegram_id": telegram_id,
        "telegram_username": telegram_username,
        "first_name": first_name,
        "last_name": "Петрова",
        "email": "maria@example.com",
        "track_ids": track_ids if track_ids is not None else [str(data.python_track_id)],
    }


async def test_only_admin_can_manage_students(client: AsyncClient, seeded: SeededData) -> None:
    student = await client.get("/api/v1/admin/students", headers=auth(seeded.student_id))
    mentor = await client.get("/api/v1/admin/students", headers=auth(seeded.mentor_id))
    admin = await client.get("/api/v1/admin/students", headers=auth(seeded.admin_id))

    assert student.status_code == mentor.status_code == 403
    assert admin.status_code == 200
    assert admin.json()["total"] == 1
    assert admin.json()["items"][0]["id"] == str(seeded.student_id)
    assert admin.json()["items"][0]["telegram_id"] is None


async def test_admin_creates_student_with_track_access(
    client: AsyncClient, seeded: SeededData
) -> None:
    response = await client.post(
        "/api/v1/admin/students",
        headers=auth(seeded.admin_id),
        json=student_payload(seeded, telegram_username="  @@maria_dev  "),
    )

    assert response.status_code == 201
    created = response.json()
    assert created["first_name"] == "Мария"
    assert created["telegram_username"] == "maria_dev"
    assert created["is_active"] is True
    assert created["learning_start_date"] == created["created_at"][:10]
    assert [track["slug"] for track in created["tracks"]] == ["python"]

    async with TestSession() as session:
        enrollment = await session.get(RoadmapEnrollment, (UUID(created["id"]), seeded.roadmap_id))
        assert enrollment is not None
        assert enrollment.started_at.date().isoformat() == created["learning_start_date"]

    me = await client.get("/api/v1/me", headers=auth(created["id"]))
    roadmaps = await client.get("/api/v1/roadmaps", headers=auth(created["id"]))
    assert me.status_code == 200
    assert [roadmap["slug"] for roadmap in roadmaps.json()] == ["python-backend"]

    listing = await client.get("/api/v1/admin/students", headers=auth(seeded.admin_id))
    detail = await client.get(
        f"/api/v1/admin/students/{created['id']}", headers=auth(seeded.admin_id)
    )
    listed = next(item for item in listing.json()["items"] if item["id"] == created["id"])
    assert listed["telegram_username"] == "maria_dev"
    assert detail.json()["telegram_username"] == "maria_dev"


async def test_admin_creates_go_student_with_cards_access_and_go_mentor_default(
    client: AsyncClient, seeded: SeededData
) -> None:
    deck = await client.post(
        "/api/v1/admin/interviews/decks",
        headers=auth(seeded.admin_id),
        json={
            "track_id": str(seeded.go_track_id),
            "slug": "go-core-for-new-students",
            "title": "Go Core",
            "description": "Вопросы по Go",
            "position": 0,
            "is_published": True,
            "cards": [
                {
                    "slug": "go-new-student-goroutine",
                    "category": "Конкурентность",
                    "question_markdown": "Что такое goroutine?",
                    "answer_markdown": "Легковесная конкурентная задача Go.",
                    "frequency": "frequent",
                    "position": 0,
                    "is_published": True,
                }
            ],
        },
    )
    assert deck.status_code == 201, deck.text

    created = await client.post(
        "/api/v1/admin/students",
        headers=auth(seeded.admin_id),
        json=student_payload(seeded, track_ids=[str(seeded.go_track_id)])
        | {"mentor_id": str(seeded.other_mentor_id)},
    )
    assert created.status_code == 201, created.text
    assert created.json()["mentor_reward_percent"] == "45.00"

    available_decks = await client.get(
        "/api/v1/interviews/decks",
        headers=auth(UUID(created.json()["id"])),
    )
    assert available_decks.status_code == 200, available_decks.text
    assert [item["slug"] for item in available_decks.json()] == [
        "go-core-for-new-students"
    ]


async def test_admin_cannot_create_student_without_learning_track(
    client: AsyncClient, seeded: SeededData
) -> None:
    response = await client.post(
        "/api/v1/admin/students",
        headers=auth(seeded.admin_id),
        json=student_payload(seeded, track_ids=[]),
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "student_track_required"


async def test_admin_edits_student_data_and_track_access(
    client: AsyncClient, seeded: SeededData
) -> None:
    response = await client.put(
        f"/api/v1/admin/students/{seeded.student_id}",
        headers=auth(seeded.admin_id),
        json=student_payload(
            seeded,
            telegram_id=777000222,
            first_name="Новое имя",
            track_ids=[str(seeded.go_track_id)],
        )
        | {"learning_start_date": "2026-07-15"},
    )
    roadmaps = await client.get("/api/v1/roadmaps", headers=auth(seeded.student_id))

    assert response.status_code == 200
    assert response.json()["telegram_id"] == 777000222
    assert response.json()["first_name"] == "Новое имя"
    assert response.json()["learning_start_date"] == "2026-07-15"
    assert [track["slug"] for track in response.json()["tracks"]] == ["go"]
    assert roadmaps.status_code == 200
    assert roadmaps.json() == []

    async with TestSession() as session:
        enrollment = await session.get(RoadmapEnrollment, (seeded.student_id, seeded.roadmap_id))
        student = await session.get(User, seeded.student_id)
        assert enrollment is not None
        assert student is not None
        assert enrollment.started_at.date().isoformat() == "2026-07-15"
        assert student.session_version == 2


async def test_admin_can_hide_student_public_identity(
    client: AsyncClient, seeded: SeededData
) -> None:
    hidden = await client.patch(
        f"/api/v1/admin/students/{seeded.student_id}/public-identity",
        headers=auth(seeded.admin_id),
        json={"hidden": True, "reason": "Запрос ученика"},
    )
    forbidden = await client.patch(
        f"/api/v1/admin/students/{seeded.student_id}/public-identity",
        headers=auth(seeded.mentor_id),
        json={"hidden": False, "reason": None},
    )
    restored = await client.patch(
        f"/api/v1/admin/students/{seeded.student_id}/public-identity",
        headers=auth(seeded.admin_id),
        json={"hidden": False, "reason": None},
    )

    assert hidden.status_code == 200
    assert hidden.json()["public_identity_hidden_at"] is not None
    assert hidden.json()["public_identity_hidden_reason"] == "Запрос ученика"
    assert forbidden.status_code == 403
    assert restored.status_code == 200
    assert restored.json()["public_identity_hidden_at"] is None


async def test_admin_can_inspect_and_retry_failed_media_anonymization(
    client: AsyncClient, seeded: SeededData, monkeypatch: MonkeyPatch
) -> None:
    company_id = uuid4()
    process_id = uuid4()
    stage_id = uuid4()
    async with TestSession() as session:
        student = await session.get(User, seeded.student_id)
        assert student is not None
        student.public_identity_hidden_at = datetime.now(UTC)
        company = Company(
            id=company_id,
            name="Example",
            normalized_name=f"example-{company_id}",
            transliterated_name="example",
        )
        process = InterviewProcess(
            id=process_id,
            user_id=seeded.student_id,
            track_id=seeded.python_track_id,
            company_id=company_id,
            company_name="Example",
        )
        stage = InterviewProcessStage(
            id=stage_id,
            process_id=process_id,
            stage_type=InterviewStageType.TECHNICAL_INTERVIEW,
            scheduled_at=datetime.now(UTC),
            media_storage_key="interviews/source.mp4",
            media_filename="source.mp4",
            media_content_type="video/mp4",
            media_size=1024,
            media_anonymization_status=InterviewMediaAnonymizationStatus.FAILED,
            media_anonymization_error="ANONYMIZATION_FAILED: invalid media",
        )
        session.add_all([company, process, stage])
        await session.commit()

    enqueued: list[tuple[str, bool]] = []

    async def fake_enqueue(stage_id: str, *, force: bool = False) -> str:
        enqueued.append((stage_id, force))
        return stage_id

    monkeypatch.setattr(
        student_service,
        "enqueue_interview_media_anonymization",
        fake_enqueue,
    )

    forbidden = await client.get(
        f"/api/v1/admin/students/{seeded.student_id}/media-anonymization",
        headers=auth(seeded.student_id),
    )
    status_response = await client.get(
        f"/api/v1/admin/students/{seeded.student_id}/media-anonymization",
        headers=auth(seeded.admin_id),
    )
    retry = await client.post(
        f"/api/v1/admin/students/{seeded.student_id}/media-anonymization/retry",
        headers=auth(seeded.admin_id),
    )

    assert forbidden.status_code == 403
    assert status_response.status_code == 200
    assert status_response.json()["failed"] == 1
    assert status_response.json()["items"][0]["error"].startswith("ANONYMIZATION_FAILED")
    assert retry.status_code == 200
    assert retry.json()["queued"] == 1
    assert enqueued == [(str(stage_id), True)]


async def test_personal_data_erasure_is_irreversible_and_preserves_artifacts(
    client: AsyncClient, seeded: SeededData
) -> None:
    async with TestSession() as session:
        student = await session.get(User, seeded.student_id)
        assert student is not None
        student.telegram_id = 777000333
        student.telegram_username = "privacy_student"
        student.email = "privacy@example.com"
        student.first_name = "Настоящее имя"
        await session.commit()

    erased = await client.post(
        f"/api/v1/admin/students/{seeded.student_id}/erase-personal-data",
        headers=auth(seeded.admin_id),
        json={"reason": "Запрос субъекта", "confirmation": "УДАЛИТЬ"},
    )
    restore_access = await client.patch(
        f"/api/v1/admin/students/{seeded.student_id}/access",
        headers=auth(seeded.admin_id),
        json={"is_active": True},
    )
    edit = await client.put(
        f"/api/v1/admin/students/{seeded.student_id}",
        headers=auth(seeded.admin_id),
        json=student_payload(seeded, telegram_id=777000444),
    )

    assert erased.status_code == 200
    body = erased.json()
    assert body["telegram_id"] is None
    assert body["telegram_username"] is None
    assert body["email"] is None
    assert body["first_name"] == "Удалённый ученик"
    assert body["personal_data_erased_at"] is not None
    assert body["is_active"] is False
    assert restore_access.status_code == 409
    assert edit.status_code == 409

    async with TestSession() as session:
        track_count = await session.scalar(
            select(func.count(LearningTrackEnrollment.user_id)).where(
                LearningTrackEnrollment.user_id == seeded.student_id
            )
        )
        assert track_count == 1


async def test_admin_suspends_and_restores_student_without_losing_tracks(
    client: AsyncClient, seeded: SeededData
) -> None:
    suspended = await client.patch(
        f"/api/v1/admin/students/{seeded.student_id}/access",
        headers=auth(seeded.admin_id),
        json={"is_active": False},
    )
    denied = await client.get("/api/v1/me", headers=auth(seeded.student_id))

    async with TestSession() as session:
        track_count = await session.scalar(
            select(func.count(LearningTrackEnrollment.user_id)).where(
                LearningTrackEnrollment.user_id == seeded.student_id
            )
        )

    restored = await client.patch(
        f"/api/v1/admin/students/{seeded.student_id}/access",
        headers=auth(seeded.admin_id),
        json={"is_active": True},
    )
    available = await client.get("/api/v1/roadmaps", headers=auth(seeded.student_id))

    assert suspended.status_code == 200
    assert suspended.json()["is_active"] is False
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "student_access_suspended"
    assert track_count == 1
    assert restored.json()["is_active"] is True
    assert [roadmap["slug"] for roadmap in available.json()] == ["python-backend"]


async def test_suspend_and_reactivate_does_not_revive_an_issued_browser_session(
    client: AsyncClient,
    seeded: SeededData,
    monkeypatch: MonkeyPatch,
) -> None:
    secret = "student-session-revocation-test-secret"
    issued_session = create_browser_session(seeded.student_id, 1, secret, 3_600)

    suspended = await client.patch(
        f"/api/v1/admin/students/{seeded.student_id}/access",
        headers=auth(seeded.admin_id),
        json={"is_active": False},
    )
    restored = await client.patch(
        f"/api/v1/admin/students/{seeded.student_id}/access",
        headers=auth(seeded.admin_id),
        json={"is_active": True},
    )
    assert suspended.status_code == restored.status_code == 200

    monkeypatch.setattr(auth_dependencies.settings, "app_env", "production")
    monkeypatch.setattr(
        auth_dependencies.settings,
        "web_session_secret",
        SecretStr(secret),
    )
    client.cookies.set("mentoring_session", issued_session)
    replayed = await client.get("/api/v1/me")

    assert replayed.status_code == 401
    assert replayed.json()["detail"]["code"] == "unauthorized"


async def test_admin_student_list_supports_search_access_filter_and_options(
    client: AsyncClient, seeded: SeededData
) -> None:
    created = await client.post(
        "/api/v1/admin/students",
        headers=auth(seeded.admin_id),
        json=student_payload(seeded),
    )
    await client.patch(
        f"/api/v1/admin/students/{created.json()['id']}/access",
        headers=auth(seeded.admin_id),
        json={"is_active": False},
    )
    probation_id = uuid4()
    async with TestSession() as session:
        session.add(
            User(
                id=probation_id,
                telegram_id=777000222,
                telegram_username="sergey_go",
                first_name="Сергей",
                role=UserRole.STUDENT,
                is_active=True,
            )
        )
        await session.flush()
        session.add_all(
            [
                MentorStudent(
                    mentor_id=seeded.other_mentor_id,
                    student_id=probation_id,
                    learning_status=StudentLearningStatus.PROBATION,
                ),
                LearningTrackEnrollment(
                    user_id=probation_id,
                    track_id=seeded.go_track_id,
                ),
            ]
        )
        await session.commit()

    search = await client.get(
        "/api/v1/admin/students?q=777000111",
        headers=auth(seeded.admin_id),
    )
    inactive = await client.get(
        "/api/v1/admin/students?is_active=false",
        headers=auth(seeded.admin_id),
    )
    combined = await client.get(
        "/api/v1/admin/students",
        headers=auth(seeded.admin_id),
        params=[
            ("q", "sergey_go"),
            ("track_id", str(seeded.go_track_id)),
            ("learning_status", "learning"),
            ("learning_status", "probation"),
            ("mentor_id", str(seeded.other_mentor_id)),
            ("is_active", "true"),
            ("limit", "1"),
        ],
    )
    learning = await client.get(
        "/api/v1/admin/students",
        headers=auth(seeded.admin_id),
        params=[("learning_status", "learning")],
    )
    options = await client.get(
        "/api/v1/admin/students/options",
        headers=auth(seeded.admin_id),
    )
    assigned_to_mentor = await client.get(
        "/api/v1/admin/students",
        headers=auth(seeded.admin_id),
        params={"mentor_id": str(seeded.mentor_id)},
    )
    without_mentor = await client.get(
        "/api/v1/admin/students?without_mentor=true",
        headers=auth(seeded.admin_id),
    )

    assert search.json()["total"] == 1
    assert search.json()["items"][0]["first_name"] == "Мария"
    assert inactive.json()["total"] == 1
    assert inactive.json()["items"][0]["is_active"] is False
    assert combined.json()["total"] == 1
    assert combined.json()["items"][0]["id"] == str(probation_id)
    assert combined.json()["items"][0]["learning_status"] == "probation"
    assert combined.json()["limit"] == 1
    assert learning.json()["total"] == 2
    assert [track["slug"] for track in options.json()["tracks"]] == ["python", "go"]
    assert [track["slug"] for track in combined.json()["tracks"]] == ["python", "go"]
    assert assigned_to_mentor.json()["total"] == 1
    assert assigned_to_mentor.json()["items"][0]["id"] == str(seeded.student_id)
    assert without_mentor.json()["total"] == 1
    assert without_mentor.json()["items"][0]["id"] == created.json()["id"]
    mentor_options = {mentor["id"]: mentor for mentor in without_mentor.json()["mentors"]}
    assert set(mentor_options) == {
        str(seeded.mentor_id),
        str(seeded.other_mentor_id),
        str(seeded.admin_id),
    }
    assert mentor_options[str(seeded.admin_id)]["role"] == "admin"


async def test_admin_rejects_duplicate_student_identifiers(
    client: AsyncClient, seeded: SeededData
) -> None:
    first = await client.post(
        "/api/v1/admin/students",
        headers=auth(seeded.admin_id),
        json=student_payload(seeded),
    )
    duplicate = await client.post(
        "/api/v1/admin/students",
        headers=auth(seeded.admin_id),
        json=student_payload(seeded, first_name="Дубликат"),
    )

    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "telegram_id_already_used"


async def test_admin_validates_and_can_clear_student_telegram_username(
    client: AsyncClient, seeded: SeededData
) -> None:
    invalid = await client.put(
        f"/api/v1/admin/students/{seeded.student_id}",
        headers=auth(seeded.admin_id),
        json=student_payload(seeded, telegram_username="bad username"),
    )
    too_short = await client.put(
        f"/api/v1/admin/students/{seeded.student_id}",
        headers=auth(seeded.admin_id),
        json=student_payload(seeded, telegram_username="abcd"),
    )
    updated = await client.put(
        f"/api/v1/admin/students/{seeded.student_id}",
        headers=auth(seeded.admin_id),
        json=student_payload(seeded, telegram_username="  @Ivan_Python  "),
    )
    cleared = await client.put(
        f"/api/v1/admin/students/{seeded.student_id}",
        headers=auth(seeded.admin_id),
        json=student_payload(seeded, telegram_username="  @  "),
    )

    assert invalid.status_code == 422
    assert too_short.status_code == 422
    assert updated.status_code == 200, updated.text
    assert updated.json()["telegram_username"] == "Ivan_Python"
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["telegram_username"] is None
