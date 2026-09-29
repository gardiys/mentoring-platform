from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import delete, select

from app.interviews.models import InterviewProcess, InterviewProcessStage, InterviewProcessStatus
from app.mentors.models import MentorStudent, MentorTrackAssignment
from app.notifications.models import NotificationKind, PlatformNotification
from tests.conftest import TestSession, auth


@pytest.fixture
async def process_id(client, seeded):
    result = await client.post(
        "/api/v1/interviews/journal/tracks",
        headers=auth(seeded.student_id),
        json={"company_name": "Offer Test", "track_id": str(seeded.python_track_id)},
    )
    assert result.status_code == 201
    return UUID(result.json()["id"])


def offer_url(student_id, process_id):
    return f"/api/v1/mentor/students/{student_id}/interviews/{process_id}/offer"


@pytest.mark.parametrize("role", ["student_id", "mentor_id", "admin_id"])
async def test_active_track_accepts_new_stages_despite_old_locked_stages(client, seeded, role):
    owner_id = getattr(seeded, role)
    created = await client.post(
        "/api/v1/interviews/journal/tracks",
        headers=auth(owner_id),
        json={"company_name": "Active Track", "track_id": str(seeded.python_track_id)},
    )
    assert created.status_code == 201
    process_id = UUID(created.json()["id"])
    old_date = datetime.now(UTC) - timedelta(days=90)
    async with TestSession() as session:
        process = await session.get_one(InterviewProcess, process_id)
        process.created_at = old_date
        session.add(
            InterviewProcessStage(
                process_id=process_id,
                stage_type="screening",
                scheduled_at=old_date,
                created_at=old_date,
                ai_analysis_requested_at=old_date,
            )
        )
        await session.commit()
    for stage_type, count in [("technical_interview", 2), ("final_interview", 3)]:
        result = await client.post(
            f"/api/v1/interviews/journal/tracks/{process_id}/stages",
            headers=auth(owner_id),
            json={"stage_type": stage_type, "scheduled_at": datetime.now(UTC).isoformat()},
        )
        assert result.status_code == 200
        assert result.json()["status"] == "active"
        assert result.json()["stage_count"] == count
        assert result.json()["stages"][0]["can_edit"] is False


@pytest.mark.parametrize("role", ["mentor_id", "admin_id"])
@pytest.mark.parametrize(
    "initial_status", [InterviewProcessStatus.ACTIVE, InterviewProcessStatus.CLOSED]
)
async def test_offer_is_recorded_once_with_real_actor_and_in_statistics(
    client, seeded, process_id, role, initial_status
):
    actor_id = getattr(seeded, role)
    closed_at = datetime.now(UTC) - timedelta(days=1)
    async with TestSession() as session:
        process = await session.get_one(InterviewProcess, process_id)
        process.status = initial_status
        if initial_status == InterviewProcessStatus.CLOSED:
            process.close_reason = "Предыдущий отказ"
            process.closed_at = closed_at
        await session.commit()
    response = await client.post(offer_url(seeded.student_id, process_id), headers=auth(actor_id))
    assert response.status_code == 200
    assert response.json()["process"]["status"] == "offer"
    assert response.json()["process"]["offer"] is None
    async with TestSession() as session:
        process = await session.get_one(InterviewProcess, process_id)
        received_at = process.offer_received_at
        assert received_at is not None
        if initial_status == InterviewProcessStatus.CLOSED:
            assert process.close_reason == "Предыдущий отказ"
            assert process.closed_at == closed_at
    again = await client.post(offer_url(seeded.student_id, process_id), headers=auth(actor_id))
    assert again.status_code == 200
    async with TestSession() as session:
        assert (
            await session.get_one(InterviewProcess, process_id)
        ).offer_received_at == received_at
        notices = list(
            await session.scalars(
                select(PlatformNotification).where(
                    PlatformNotification.user_id == seeded.student_id,
                    PlatformNotification.kind == NotificationKind.OFFER,
                )
            )
        )
        assert len(notices) == 1
        assert notices[0].actor_user_id == actor_id
    analytics = await client.get(
        "/api/v1/mentor/students/analytics", headers=auth(seeded.mentor_id)
    )
    assert analytics.status_code == 200
    assert analytics.json()["offers_received"] == 1


@pytest.mark.parametrize("assignment", ["other", "none"])
async def test_admin_can_mark_offer_without_own_assignment(client, seeded, process_id, assignment):
    async with TestSession() as session:
        relation = await session.scalar(
            select(MentorStudent).where(MentorStudent.student_id == seeded.student_id)
        )
        if assignment == "none":
            await session.delete(relation)
        else:
            relation.mentor_id = seeded.other_mentor_id
        await session.commit()
    response = await client.post(
        offer_url(seeded.student_id, process_id), headers=auth(seeded.admin_id)
    )
    assert response.status_code == 200
    assert response.json()["process"]["status"] == "offer"


@pytest.mark.parametrize(
    "role,expected", [("other_mentor_id", 403), ("student_id", 403), (None, 401)]
)
async def test_unauthorized_offer_does_not_change_process(
    client, seeded, process_id, role, expected
):
    headers = auth(getattr(seeded, role)) if role else {}
    response = await client.post(offer_url(seeded.student_id, process_id), headers=headers)
    assert response.status_code == expected
    async with TestSession() as session:
        process = await session.get_one(InterviewProcess, process_id)
        assert process.status == InterviewProcessStatus.ACTIVE
        assert process.offer_received_at is None
        assert (
            await session.scalar(
                select(PlatformNotification.id).where(
                    PlatformNotification.kind == NotificationKind.OFFER
                )
            )
            is None
        )


async def test_mentor_cannot_use_own_students_url_for_someone_elses_track(
    client, seeded, process_id
):
    async with TestSession() as session:
        process = await session.get_one(InterviewProcess, process_id)
        process.user_id = seeded.other_mentor_id
        await session.commit()
    response = await client.post(
        offer_url(seeded.student_id, process_id), headers=auth(seeded.mentor_id)
    )
    assert response.status_code == 404
    async with TestSession() as session:
        assert (
            await session.get_one(InterviewProcess, process_id)
        ).status == InterviewProcessStatus.ACTIVE


async def test_mentor_cannot_mark_track_outside_accessible_direction(client, seeded, process_id):
    async with TestSession() as session:
        await session.execute(
            delete(MentorTrackAssignment).where(MentorTrackAssignment.mentor_id == seeded.mentor_id)
        )
        await session.commit()
    response = await client.post(
        offer_url(seeded.student_id, process_id), headers=auth(seeded.mentor_id)
    )
    assert response.status_code == 404
    async with TestSession() as session:
        assert (
            await session.get_one(InterviewProcess, process_id)
        ).status == InterviewProcessStatus.ACTIVE


async def test_existing_offer_file_and_date_are_preserved(client, seeded, process_id):
    received_at = datetime.now(UTC) - timedelta(days=10)
    async with TestSession() as session:
        process = await session.get_one(InterviewProcess, process_id)
        process.status = InterviewProcessStatus.OFFER
        process.offer_received_at = received_at
        process.offer_storage_key = "offers/existing.pdf"
        process.offer_filename = "offer.pdf"
        process.offer_content_type = "application/pdf"
        process.offer_size = 100
        await session.commit()
    response = await client.post(
        offer_url(seeded.student_id, process_id), headers=auth(seeded.mentor_id)
    )
    assert response.status_code == 200
    assert response.json()["process"]["offer"]["filename"] == "offer.pdf"
    async with TestSession() as session:
        process = await session.get_one(InterviewProcess, process_id)
        assert process.offer_received_at == received_at
        assert process.offer_storage_key == "offers/existing.pdf"
