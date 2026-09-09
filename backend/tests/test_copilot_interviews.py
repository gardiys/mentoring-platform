from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import select, update

from app.copilot.models import CopilotSession
from app.core.config import get_settings
from app.interviews import journal_router
from app.interviews.models import InterviewProcess, InterviewProcessStage
from app.mentors.models import MentorStudent, StudentLearningStatus, StudentMentorshipState
from app.tracks.models import LearningTrackEnrollment
from app.users.models import User, UserRole
from tests.conftest import TestSession, auth
from tests.test_interview_journal import FakeInterviewUploadStore

SECRET = "synthetic-copilot-integration-test-secret"


@pytest.fixture
async def enabled(seeded, monkeypatch):
    monkeypatch.setattr(get_settings(), "copilot_students_enabled", True)
    monkeypatch.setattr(get_settings(), "copilot_integration_token", SecretStr(SECRET))
    async with TestSession() as session:
        await session.execute(
            update(MentorStudent)
            .where(MentorStudent.student_id == seeded.student_id)
            .values(learning_status=StudentLearningStatus.INTERVIEWING)
        )
        await session.commit()
    return seeded


async def track(client, seeded, **extra):
    response = await client.post(
        "/api/v1/copilot/tracks",
        headers=auth(seeded.student_id),
        json={
            "company_name": "Example Company",
            "track_id": str(seeded.python_track_id),
            **extra,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def snapshot(seeded, process_id=None, **extra):
    now = datetime.now(UTC)
    return dict(
        tenant_id="copilot",
        session_id=str(uuid4()),
        student_id=str(seeded.student_id),
        process_id=process_id,
        mode="real" if process_id else "mock",
        track="python",
        state="completed",
        started_at=(now - timedelta(minutes=10)).isoformat(),
        finished_at=now.isoformat(),
        active_ms=180000,
        revision=2,
        **extra,
    )


async def sync(client, data):
    return await client.post(
        "/api/v1/copilot/internal/sessions",
        headers={"Authorization": "Bearer " + SECRET},
        json=data,
    )


async def test_access_requires_rollout_and_canonical_interviewing_status(
    client, enabled, monkeypatch
):
    seeded = enabled
    headers = auth(seeded.student_id)
    assert (await client.get("/api/v1/copilot/access", headers=headers)).json()["student_allowed"]
    async with TestSession() as session:
        session.add(
            StudentMentorshipState(
                student_id=seeded.student_id, learning_status=StudentLearningStatus.LEARNING
            )
        )
        await session.commit()
    assert not (await client.get("/api/v1/copilot/access", headers=headers)).json()[
        "student_allowed"
    ]
    assert (await client.get("/api/v1/copilot/tracks", headers=headers)).status_code == 403
    assert (await client.get("/api/v1/copilot/usage", headers=headers)).status_code == 403
    monkeypatch.setattr(get_settings(), "copilot_students_enabled", False)
    assert not (await client.get("/api/v1/copilot/access", headers=headers)).json()["allowed"]
    assert (await client.get("/api/v1/copilot/access", headers=auth(seeded.admin_id))).json()[
        "allowed"
    ]


async def test_context_respects_team_role_direction_and_anonymous_catalog(client, enabled):
    seeded = enabled
    process = await track(
        client, seeded, team_name="Payments", position_name="Backend", company_notes="B2B products"
    )
    own_stage = InterviewProcessStage(
        process_id=UUID(process["id"]),
        stage_type="screening",
        scheduled_at=datetime.now(UTC) - timedelta(days=1),
        description="My previous interview",
    )
    async with TestSession() as session:
        session.add(own_stage)
        company_id = (await session.get(InterviewProcess, UUID(process["id"]))).company_id
        for team, role, hidden, description in [
            (" payments ", "Backend", False, "Relevant experience"),
            ("Search", "Backend", False, "Different team"),
            ("Payments", "Backend", True, "Private identity"),
            ("Payments", "Manager", False, "Other vacancy"),
            (None, "Backend", False, "Unknown team"),
        ]:
            user = User(
                first_name="Peer",
                role=UserRole.STUDENT,
                public_identity_hidden_at=datetime.now(UTC) if hidden else None,
            )
            session.add(user)
            await session.flush()
            session.add(LearningTrackEnrollment(user_id=user.id, track_id=seeded.python_track_id))
            other = InterviewProcess(
                user_id=user.id,
                company_id=company_id,
                company_name=process["company_name"],
                track_id=seeded.python_track_id,
                team_name=team,
                position_name=role,
            )
            session.add(other)
            await session.flush()
            session.add(
                InterviewProcessStage(
                    process_id=other.id,
                    stage_type="technical_interview",
                    scheduled_at=datetime.now(UTC) - timedelta(hours=1),
                    description=description,
                )
            )
        await session.commit()
    response = await client.get(
        f"/api/v1/copilot/tracks/{process['id']}/context", headers=auth(seeded.student_id)
    )
    assert response.status_code == 200, response.text
    context = response.json()["context"]
    assert context["company_notes"] == "B2B products"
    assert context["previous_interviews"][0]["description"] == "My previous interview"
    assert [p["description"] for p in context["peer_examples"]] == ["Relevant experience"]
    async with TestSession() as session:
        await session.execute(
            update(InterviewProcess)
            .where(InterviewProcess.id == UUID(process["id"]))
            .values(team_name=None)
        )
        await session.commit()
    assert not (
        await client.get(
            f"/api/v1/copilot/tracks/{process['id']}/context", headers=auth(seeded.student_id)
        )
    ).json()["context"]["peer_examples"]


async def test_usage_is_server_attested_monotonic_and_admin_only(client, enabled):
    seeded = enabled
    data = snapshot(seeded)
    assert (
        await client.post(
            "/api/v1/copilot/internal/sessions",
            headers={"Authorization": "Bearer wrong-service-secret"},
            json=data,
        )
    ).status_code == 403
    assert (await sync(client, data)).status_code == 200
    assert (
        await sync(client, {**data, "revision": 1, "active_ms": 60000, "state": "active"})
    ).status_code == 200
    assert (await sync(client, {**data, "revision": 3, "active_ms": 100})).status_code == 200
    usage = await client.get("/api/v1/copilot/usage", headers=auth(seeded.admin_id))
    row = next(r for r in usage.json()["students"] if r["student_id"] == str(seeded.student_id))
    assert (
        row["active_ms"] == 180000
        and row["interviews_completed"] == 1
        and row["mock_completed"] == 1
    )
    assert (await sync(client, {**data, "revision": 4, "active_ms": 999999999})).status_code == 422


async def test_upload_retries_reuse_stage_and_media_and_deny_cross_user(
    client, enabled, monkeypatch
):
    seeded = enabled
    monkeypatch.setattr(journal_router, "store", FakeInterviewUploadStore())
    process = await track(client, seeded)
    data = snapshot(seeded, process["id"])
    assert (await sync(client, data)).status_code == 200
    path = f"/api/v1/copilot/sessions/{data['session_id']}"
    headers = {**auth(seeded.student_id), "X-Copilot-Tenant": "copilot"}
    fields = dict(
        stage_type="screening", scheduled_at=data["started_at"], description="Recorded from Copilot"
    )
    first = await client.post(path + "/stage", headers=headers, json=fields)
    assert first.status_code == 200, first.text
    second = await client.post(path + "/stage", headers=headers, json=fields)
    assert first.json()["stage_id"] == second.json()["stage_id"]
    assert (
        await client.post(
            path + "/stage", headers={**headers, "X-Copilot-Tenant": "other"}, json=fields
        )
    ).status_code == 404
    media = dict(
        filename="interview.mp4",
        content_type="video/mp4",
        size=2048,
        upload_protocol="multipart-v1",
    )
    intent = await client.post(path + "/media/upload", headers=headers, json=media)
    assert intent.status_code == 200, intent.text
    plan = intent.json()
    body = {
        **media,
        "storage_key": plan["storage_key"],
        "upload_id": plan["upload_id"],
        "upload_token": plan["upload_token"],
        "parts": [{"part_number": 1, "etag": "synthetic"}],
    }
    complete = await client.post(path + "/media/complete", headers=headers, json=body)
    assert complete.status_code == 200, complete.text
    assert (
        await client.post(path + "/media/complete", headers=headers, json=body)
    ).status_code == 200
    assert (await client.post(path + "/stage", headers=headers, json=fields)).json()["uploaded"]
    async with TestSession() as session:
        stages = (
            await session.scalars(
                select(InterviewProcessStage).where(
                    InterviewProcessStage.process_id == UUID(process["id"])
                )
            )
        ).all()
        assert len(stages) == 1 and stages[0].media_storage_key == plan["storage_key"]
        record = await session.get(CopilotSession, ("copilot", UUID(data["session_id"])))
        assert record.stage_id == stages[0].id


async def test_issued_desktop_token_loses_access_when_progress_changes(
    client, enabled, monkeypatch
):
    from app.auth.desktop import DesktopGrant, token_hash

    seeded = enabled
    monkeypatch.setattr(get_settings(), "desktop_auth_enabled", True)
    token = "copilot_" + "synthetic-access-token-" * 3
    now = datetime.now(UTC)
    async with TestSession() as session:
        user = await session.get(User, seeded.student_id)
        session.add(
            DesktopGrant(
                device_hash="a" * 64,
                user_code="TEST-CODE",
                status="issued",
                requester_hash="b" * 64,
                created_at=now,
                expires_at=now + timedelta(minutes=10),
                user_id=user.id,
                session_version=user.session_version,
                token_hash=token_hash(token),
                token_expires_at=now + timedelta(hours=1),
            )
        )
        await session.commit()
    headers = {"Authorization": "Bearer " + token}
    assert (await client.get("/api/v1/copilot/access", headers=headers)).status_code == 200
    assert (
        await client.post(
            "/api/v1/copilot/tracks",
            headers=headers,
            json={"company_name": "Desktop Company", "track_id": str(seeded.python_track_id)},
        )
    ).status_code == 201
    assert (await client.get("/api/v1/copilot/usage", headers=headers)).status_code == 403
    async with TestSession() as session:
        session.add(
            StudentMentorshipState(
                student_id=seeded.student_id, learning_status=StudentLearningStatus.PROBATION
            )
        )
        await session.commit()
    assert (await client.get("/api/v1/copilot/access", headers=headers)).status_code == 403
    assert (await client.get("/api/v1/copilot/tracks", headers=headers)).status_code == 403
    assert (await client.post("/api/v1/auth/desktop/logout", headers=headers)).status_code == 204
