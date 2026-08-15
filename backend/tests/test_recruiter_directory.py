from uuid import uuid4

from httpx import AsyncClient

from app.tracks.models import LearningTrackEnrollment
from app.users.models import User, UserRole
from tests.conftest import SeededData, TestSession, auth


async def test_recruiter_directory_counts_student_contacts_and_feedback(
    client: AsyncClient, seeded: SeededData
) -> None:
    second_student_id = uuid4()
    async with TestSession() as session:
        session.add(
            User(
                id=second_student_id,
                first_name="Мария",
                role=UserRole.STUDENT,
            )
        )
        await session.flush()
        session.add(
            LearningTrackEnrollment(
                user_id=second_student_id,
                track_id=seeded.python_track_id,
            )
        )
        await session.commit()

    created = await client.post(
        "/api/v1/interviews/journal/tracks",
        headers=auth(seeded.student_id),
        json={
            "company_name": "ООО Яндекс",
            "track_id": str(seeded.python_track_id),
            "recruiter_telegram_usernames": [
                "@Yandex_Recruiter",
                "@quiet_recruiter",
            ],
        },
    )
    assert created.status_code == 201

    listing = await client.get(
        "/api/v1/interviews/recruiters?q=яндекс",
        headers=auth(second_student_id),
    )
    transliterated_listing = await client.get(
        "/api/v1/interviews/recruiters?q=Yandex",
        headers=auth(second_student_id),
    )
    assert listing.status_code == 200
    company_group = listing.json()["items"][0]
    assert company_group["company"]["name"] == "Яндекс"
    recruiter = next(
        item
        for item in company_group["recruiters"]
        if item["telegram_username"] == "yandex_recruiter"
    )
    recruiter_id = recruiter["id"]
    assert recruiter["telegram_username"] == "yandex_recruiter"
    assert recruiter["companies"][0]["name"] == "Яндекс"
    assert recruiter["tracks"][0]["slug"] == "python"
    assert recruiter["total_contact_opens"] == 0
    assert any(
        item["id"] == recruiter_id
        for item in transliterated_listing.json()["items"][0]["recruiters"]
    )
    contacted_before = await client.get(
        "/api/v1/interviews/recruiters?contacted=true",
        headers=auth(second_student_id),
    )
    not_contacted_before = await client.get(
        "/api/v1/interviews/recruiters?contacted=false",
        headers=auth(second_student_id),
    )
    assert contacted_before.json()["items"] == []
    assert len(not_contacted_before.json()["items"][0]["recruiters"]) == 2

    first_open = await client.post(
        f"/api/v1/interviews/recruiters/{recruiter_id}/contact",
        headers=auth(second_student_id),
    )
    second_open = await client.post(
        f"/api/v1/interviews/recruiters/{recruiter_id}/contact",
        headers=auth(second_student_id),
    )
    admin_preview = await client.post(
        f"/api/v1/interviews/recruiters/{recruiter_id}/contact",
        headers=auth(seeded.admin_id),
    )
    assert first_open.json()["url"] == "https://t.me/yandex_recruiter"
    assert first_open.json()["total_contact_opens"] == 1
    assert first_open.json()["my_contact_opens"] == 1
    assert second_open.status_code == 200
    assert second_open.json()["total_contact_opens"] == 1
    assert second_open.json()["my_contact_opens"] == 1
    assert admin_preview.status_code == 200
    assert admin_preview.json()["total_contact_opens"] == 2
    assert admin_preview.json()["students_contacted_count"] == 1
    assert admin_preview.json()["my_contact_opens"] == 1

    issue = await client.put(
        f"/api/v1/interviews/recruiters/{recruiter_id}/feedback",
        headers=auth(second_student_id),
        json={"kind": "ignores", "reason": "Не ответила за две недели"},
    )
    helpful = await client.put(
        f"/api/v1/interviews/recruiters/{recruiter_id}/feedback",
        headers=auth(seeded.student_id),
        json={"kind": "helpful", "reason": None},
    )
    admin_helpful = await client.put(
        f"/api/v1/interviews/recruiters/{recruiter_id}/feedback",
        headers=auth(seeded.admin_id),
        json={"kind": "helpful", "reason": None},
    )
    admin_issue = await client.put(
        f"/api/v1/interviews/recruiters/{recruiter_id}/feedback",
        headers=auth(seeded.admin_id),
        json={"kind": "no_longer_works", "reason": "Сменила компанию"},
    )
    mentor_helpful = await client.put(
        f"/api/v1/interviews/recruiters/{recruiter_id}/feedback",
        headers=auth(seeded.mentor_id),
        json={"kind": "helpful", "reason": None},
    )
    assert issue.status_code == 200
    assert helpful.status_code == 200
    assert admin_helpful.status_code == 200
    assert admin_issue.status_code == 200
    assert mentor_helpful.status_code == 200

    updated = await client.get(
        "/api/v1/interviews/recruiters",
        headers=auth(second_student_id),
    )
    group = updated.json()["items"][0]
    item = next(recruiter for recruiter in group["recruiters"] if recruiter["id"] == recruiter_id)
    assert item["total_contact_opens"] == 2
    assert item["students_contacted_count"] == 1
    assert item["last_contacted_at"] is not None
    assert item["helpful_count"] == 2
    assert item["ignores_count"] == 1
    assert item["no_longer_works_count"] == 1
    assert item["issue_comments_total"] == 2
    assert {comment["reason"] for comment in item["issue_comments"]} == {
        "Не ответила за две недели",
        "Сменила компанию",
    }
    admin_comment = next(
        comment for comment in item["issue_comments"] if comment["reason"] == "Сменила компанию"
    )
    assert admin_comment["author_role"] == "admin"
    assert item["my_feedback"]["kind"] == "ignores"
    assert item["my_feedback"]["reason"] == "Не ответила за две недели"
    assert item["has_contacted"] is True
    assert item["my_contact_opens"] == 1
    assert item["my_last_contacted_at"] is not None
    assert group["recruiters"][0]["id"] == recruiter_id
    contacted_after = await client.get(
        "/api/v1/interviews/recruiters?contacted=true",
        headers=auth(second_student_id),
    )
    not_contacted_after = await client.get(
        "/api/v1/interviews/recruiters?contacted=false",
        headers=auth(second_student_id),
    )
    assert [recruiter["id"] for recruiter in contacted_after.json()["items"][0]["recruiters"]] == [
        recruiter_id
    ]
    assert [
        recruiter["telegram_username"]
        for recruiter in not_contacted_after.json()["items"][0]["recruiters"]
    ] == ["quiet_recruiter"]

    deleted = await client.delete(
        f"/api/v1/interviews/recruiters/{recruiter_id}/feedback",
        headers=auth(second_student_id),
    )
    assert deleted.status_code == 204
    after_delete = await client.get(
        "/api/v1/interviews/recruiters",
        headers=auth(second_student_id),
    )
    deleted_item = next(
        recruiter
        for recruiter in after_delete.json()["items"][0]["recruiters"]
        if recruiter["id"] == recruiter_id
    )
    assert deleted_item["ignores_count"] == 0
    assert deleted_item["my_feedback"] is None


async def test_recruiter_directory_respects_direction_and_syncs_edits(
    client: AsyncClient, seeded: SeededData
) -> None:
    go_student_id = uuid4()
    async with TestSession() as session:
        session.add(User(id=go_student_id, first_name="Go", role=UserRole.STUDENT))
        await session.flush()
        session.add(
            LearningTrackEnrollment(
                user_id=go_student_id,
                track_id=seeded.go_track_id,
            )
        )
        await session.commit()

    created = await client.post(
        "/api/v1/interviews/journal/tracks",
        headers=auth(seeded.student_id),
        json={
            "company_name": "Python Company",
            "track_id": str(seeded.python_track_id),
            "recruiter_telegram_usernames": ["first_recruiter"],
        },
    )
    process_id = created.json()["id"]
    python_listing = await client.get(
        "/api/v1/interviews/recruiters", headers=auth(seeded.student_id)
    )
    go_listing = await client.get("/api/v1/interviews/recruiters", headers=auth(go_student_id))
    assert [
        item["telegram_username"] for item in python_listing.json()["items"][0]["recruiters"]
    ] == ["first_recruiter"]
    assert go_listing.json()["items"] == []

    updated = await client.patch(
        f"/api/v1/interviews/journal/tracks/{process_id}/recruiters",
        headers=auth(seeded.student_id),
        json={"recruiter_telegram_usernames": ["second_recruiter"]},
    )
    assert updated.status_code == 200
    after_update = await client.get(
        "/api/v1/interviews/recruiters", headers=auth(seeded.student_id)
    )
    assert [
        item["telegram_username"] for item in after_update.json()["items"][0]["recruiters"]
    ] == ["second_recruiter"]
