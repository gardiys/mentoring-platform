from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from httpx import AsyncClient
from pytest import MonkeyPatch

from app.interviews import journal_router
from app.interviews.models import InterviewProcessStage, InterviewProcessStageAttachment
from app.interviews.upload_cleanup import delete_upload_if_unreferenced
from app.interviews.uploads import (
    MultipartUploadIntent,
    MultipartUploadPartIntent,
    StoredUpload,
    UploadIntent,
)
from app.tracks.models import LearningTrackEnrollment
from app.users.models import User, UserRole
from tests.conftest import SeededData, TestSession, auth


def process_payload(
    company_name: str,
    track_id: UUID,
    recruiter_usernames: list[str] | None = None,
) -> dict[str, object]:
    return {
        "company_name": company_name,
        "track_id": str(track_id),
        "recruiter_telegram_usernames": recruiter_usernames or [],
    }


def stage_payload(stage_type: str = "technical_interview") -> dict[str, str]:
    return {
        "stage_type": stage_type,
        "scheduled_at": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
        "description": "Обсудить Python, базы данных и архитектуру",
    }


class FakeInterviewUploadStore:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    def create_upload_intent(self, **kwargs: object) -> UploadIntent:
        user_id = kwargs["user_id"]
        category = kwargs["category"]
        storage_key = f"pending/{category}/{user_id}/{uuid4().hex}"
        return UploadIntent(
            upload_url="https://s3.example.test/upload",
            fields={"key": storage_key, "policy": "signed"},
            storage_key=storage_key,
            filename=str(kwargs["filename"]),
            content_type=str(kwargs["content_type"]),
            size=int(kwargs["size"]),
            expires_in=900,
        )

    async def complete_upload(self, **kwargs: object) -> StoredUpload:
        return StoredUpload(
            storage_key=str(kwargs["storage_key"]).replace("pending/", "", 1),
            filename=str(kwargs["filename"]),
            content_type=str(kwargs["content_type"]),
            size=int(kwargs["expected_size"]),
        )

    async def create_multipart_upload_intent(self, **kwargs: object) -> MultipartUploadIntent:
        user_id = kwargs["user_id"]
        category = kwargs["category"]
        storage_key = f"{category}/{user_id}/{uuid4().hex}"
        return MultipartUploadIntent(
            upload_protocol="multipart-v1",
            upload_id="provider-upload-id",
            upload_token="signed-upload-token",
            abort_url="/api/v1/uploads/multipart/abort",
            storage_key=storage_key,
            filename=str(kwargs["filename"]),
            content_type=str(kwargs["content_type"]),
            size=int(kwargs["size"]),
            part_size=64 * 1024 * 1024,
            part_count=1,
            parts=(
                MultipartUploadPartIntent(
                    part_number=1,
                    upload_url="https://s3.example.test/part/1",
                    headers={},
                ),
            ),
            expires_in=21_600,
        )

    async def complete_multipart_upload(self, **kwargs: object) -> StoredUpload:
        return StoredUpload(
            storage_key=str(kwargs["storage_key"]),
            filename=str(kwargs["filename"]),
            content_type=str(kwargs["content_type"]),
            size=int(kwargs["expected_size"]),
        )

    def download_url(self, upload: StoredUpload, *, inline: bool = False) -> str:
        mode = "inline" if inline else "download"
        return f"https://s3.example.test/{upload.storage_key}?mode={mode}"

    async def delete(self, storage_key: str | None) -> None:
        if storage_key:
            self.deleted.append(storage_key)


async def create_process(
    client: AsyncClient, seeded: SeededData, company_name: str = "Яндекс"
) -> dict[str, object]:
    response = await client.post(
        "/api/v1/interviews/journal/tracks",
        headers=auth(seeded.student_id),
        json=process_payload(company_name, seeded.python_track_id),
    )
    assert response.status_code == 201
    return response.json()


async def test_students_mentors_and_admins_can_use_personal_interview_journal(
    client: AsyncClient, seeded: SeededData
) -> None:
    student = await client.get("/api/v1/interviews/journal/tracks", headers=auth(seeded.student_id))
    mentor = await client.get("/api/v1/interviews/journal/tracks", headers=auth(seeded.mentor_id))
    admin = await client.get("/api/v1/interviews/journal/tracks", headers=auth(seeded.admin_id))

    assert student.status_code == 200
    assert student.json() == []
    assert mentor.status_code == 200
    assert mentor.json() == []
    assert admin.status_code == 200
    assert admin.json() == []


async def test_admin_creates_and_opens_own_interview_track(
    client: AsyncClient, seeded: SeededData
) -> None:
    created = await client.post(
        "/api/v1/interviews/journal/tracks",
        headers=auth(seeded.admin_id),
        json=process_payload("AcmeTech", seeded.go_track_id),
    )
    detail = await client.get(
        f"/api/v1/interviews/journal/tracks/{created.json()['id']}",
        headers=auth(seeded.admin_id),
    )

    assert created.status_code == 201
    assert detail.status_code == 200
    assert detail.json()["company_name"] == "AcmeTech"
    assert detail.json()["track_slug"] == "go"


async def test_mentor_creates_own_track_only_in_assigned_direction_and_publishes_to_catalog(
    client: AsyncClient, seeded: SeededData
) -> None:
    directions = await client.get(
        "/api/v1/interviews/journal/directions",
        headers=auth(seeded.mentor_id),
    )
    unavailable = await client.post(
        "/api/v1/interviews/journal/tracks",
        headers=auth(seeded.mentor_id),
        json=process_payload("Mentor Go Company", seeded.go_track_id),
    )
    created = await client.post(
        "/api/v1/interviews/journal/tracks",
        headers=auth(seeded.mentor_id),
        json=process_payload("Mentor Catalog Company", seeded.python_track_id),
    )
    process_id = created.json()["id"]
    stage = await client.post(
        f"/api/v1/interviews/journal/tracks/{process_id}/stages",
        headers=auth(seeded.mentor_id),
        json=stage_payload(),
    )
    student_cannot_edit = await client.put(
        f"/api/v1/interviews/journal/tracks/{process_id}",
        headers=auth(seeded.student_id),
        json=process_payload("Чужое изменение", seeded.python_track_id),
    )
    companies = await client.get(
        "/api/v1/interviews/catalog/companies?q=Mentor Catalog Company",
        headers=auth(seeded.student_id),
    )
    company_id = companies.json()["items"][0]["id"]
    catalog = await client.get(
        f"/api/v1/interviews/catalog/companies/{company_id}",
        headers=auth(seeded.student_id),
    )

    assert [item["slug"] for item in directions.json()] == ["python"]
    assert unavailable.status_code == 422
    assert unavailable.json()["detail"]["code"] == "interview_direction_not_available"
    assert created.status_code == 201
    assert stage.status_code == 200
    assert student_cannot_edit.status_code == 404
    assert companies.status_code == 200
    assert companies.json()["total"] == 1
    assert catalog.json()["tracks"][0]["id"] == process_id
    assert catalog.json()["tracks"][0]["author"] == {
        "id": str(seeded.mentor_id),
        "name": "Антон",
        "telegram_username": None,
    }


async def test_student_creates_process_and_multiple_interview_stages(
    client: AsyncClient, seeded: SeededData
) -> None:
    directions = await client.get(
        "/api/v1/interviews/journal/directions",
        headers=auth(seeded.student_id),
    )
    process = await create_process(client, seeded)
    first = await client.post(
        f"/api/v1/interviews/journal/tracks/{process['id']}/stages",
        headers=auth(seeded.student_id),
        json=stage_payload("screening"),
    )
    second = await client.post(
        f"/api/v1/interviews/journal/tracks/{process['id']}/stages",
        headers=auth(seeded.student_id),
        json=stage_payload("system_design"),
    )
    listing = await client.get(
        "/api/v1/interviews/journal/tracks?status=active",
        headers=auth(seeded.student_id),
    )

    assert [item["slug"] for item in directions.json()] == ["python"]
    assert process["track_id"] == str(seeded.python_track_id)
    assert process["track_title"] == "Python"
    assert first.status_code == second.status_code == 200
    assert [stage["stage_type"] for stage in second.json()["stages"]] == [
        "screening",
        "system_design",
    ]
    assert second.json()["stages"][0]["description"].startswith("Обсудить Python")
    assert listing.json()[0]["company_name"] == "Яндекс"
    assert listing.json()[0]["stage_count"] == 2
    assert listing.json()[0]["next_stage_at"] is not None


async def test_student_adds_and_edits_recruiter_telegram_usernames(
    client: AsyncClient, seeded: SeededData
) -> None:
    created = await client.post(
        "/api/v1/interviews/journal/tracks",
        headers=auth(seeded.student_id),
        json=process_payload(
            "Авито",
            seeded.python_track_id,
            ["@Recruiter_One", "https://t.me/recruiter_two", "@recruiter_one"],
        ),
    )
    updated_without_recruiters = await client.put(
        f"/api/v1/interviews/journal/tracks/{created.json()['id']}",
        headers=auth(seeded.student_id),
        json={"company_name": "Авито", "track_id": str(seeded.python_track_id)},
    )
    updated = await client.patch(
        f"/api/v1/interviews/journal/tracks/{created.json()['id']}/recruiters",
        headers=auth(seeded.student_id),
        json={"recruiter_telegram_usernames": ["@new_recruiter"]},
    )
    invalid = await client.patch(
        f"/api/v1/interviews/journal/tracks/{created.json()['id']}/recruiters",
        headers=auth(seeded.student_id),
        json={"recruiter_telegram_usernames": ["not a username"]},
    )

    assert created.status_code == 201
    assert created.json()["recruiter_telegram_usernames"] == [
        "recruiter_one",
        "recruiter_two",
    ]
    assert updated_without_recruiters.json()["recruiter_telegram_usernames"] == [
        "recruiter_one",
        "recruiter_two",
    ]
    assert updated.status_code == 200
    assert updated.json()["recruiter_telegram_usernames"] == ["new_recruiter"]
    assert invalid.status_code == 422


async def test_company_directory_normalizes_and_ranks_existing_names(
    client: AsyncClient, seeded: SeededData
) -> None:
    first = await create_process(client, seeded, "ООО «Яндекс»")
    await create_process(client, seeded, "Яндекс")
    await create_process(client, seeded, "Тбанк")
    await create_process(client, seeded, "Ярмарка")
    await create_process(client, seeded, "Yota")

    exact = await client.get(
        "/api/v1/interviews/journal/companies?q=Яндекс",
        headers=auth(seeded.student_id),
    )
    transliterated = await client.get(
        "/api/v1/interviews/journal/companies?q=Yandex",
        headers=auth(seeded.student_id),
    )
    punctuation_insensitive = await client.get(
        "/api/v1/interviews/journal/companies?q=Т-банк",
        headers=auth(seeded.student_id),
    )

    assert first["company_name"] == "Яндекс"
    assert [item["name"] for item in exact.json()].count("Яндекс") == 1
    assert exact.json()[0]["name"] == "Яндекс"
    assert transliterated.json()[0]["name"] == "Яндекс"
    assert punctuation_insensitive.json()[0]["name"] == "Тбанк"


async def test_only_admin_can_merge_companies_when_learning_an_existing_alias(
    client: AsyncClient, seeded: SeededData
) -> None:
    canonical_process = await create_process(client, seeded, "Wildberries")
    duplicate_process = await create_process(client, seeded, "WB")
    canonical = await client.get(
        "/api/v1/interviews/journal/companies?q=Wildberries",
        headers=auth(seeded.student_id),
    )
    canonical_id = canonical.json()[0]["id"]

    student_merge = await client.post(
        "/api/v1/interviews/journal/tracks",
        headers=auth(seeded.student_id),
        json={
            "company_name": "Wildberries",
            "track_id": str(seeded.python_track_id),
            "company_id": canonical_id,
            "company_alias": "WB",
        },
    )
    duplicate_before_admin_merge = await client.get(
        f"/api/v1/interviews/journal/tracks/{duplicate_process['id']}",
        headers=auth(seeded.student_id),
    )

    linked = await client.post(
        "/api/v1/interviews/journal/tracks",
        headers=auth(seeded.admin_id),
        json={
            "company_name": "Wildberries",
            "track_id": str(seeded.python_track_id),
            "company_id": canonical_id,
            "company_alias": "WB",
        },
    )
    alias_search = await client.get(
        "/api/v1/interviews/journal/companies?q=WB",
        headers=auth(seeded.student_id),
    )
    merged_process = await client.get(
        f"/api/v1/interviews/journal/tracks/{duplicate_process['id']}",
        headers=auth(seeded.student_id),
    )

    assert student_merge.status_code == 409
    assert student_merge.json()["detail"]["code"] == "company_alias_conflict"
    assert duplicate_before_admin_merge.json()["company_name"] == "WB"
    assert linked.status_code == 201
    assert linked.json()["company_name"] == "Wildberries"
    assert alias_search.json()[0]["name"] == "Wildberries"
    assert [item["name"] for item in alias_search.json()].count("Wildberries") == 1
    assert merged_process.json()["company_name"] == "Wildberries"
    assert canonical_process["company_name"] == "Wildberries"


async def test_other_student_cannot_read_or_mutate_personal_journal_track(
    client: AsyncClient, seeded: SeededData
) -> None:
    process = await create_process(client, seeded)
    stage_response = await client.post(
        f"/api/v1/interviews/journal/tracks/{process['id']}/stages",
        headers=auth(seeded.student_id),
        json=stage_payload(),
    )
    stage_id = stage_response.json()["stages"][0]["id"]
    other_student_id = uuid4()
    async with TestSession() as session:
        session.add(User(id=other_student_id, first_name="Другой", role=UserRole.STUDENT))
        await session.flush()
        session.add(
            LearningTrackEnrollment(
                user_id=other_student_id,
                track_id=seeded.python_track_id,
            )
        )
        await session.commit()
    other_headers = auth(other_student_id)

    attempts = [
        await client.get(
            f"/api/v1/interviews/journal/tracks/{process['id']}",
            headers=other_headers,
        ),
        await client.put(
            f"/api/v1/interviews/journal/tracks/{process['id']}",
            headers=other_headers,
            json=process_payload("Чужая компания", seeded.go_track_id),
        ),
        await client.patch(
            f"/api/v1/interviews/journal/tracks/{process['id']}/outcome",
            headers=other_headers,
            json={"status": "closed", "close_reason": "Не владелец"},
        ),
        await client.patch(
            f"/api/v1/interviews/journal/tracks/{process['id']}/recruiters",
            headers=other_headers,
            json={"recruiter_telegram_usernames": ["other_recruiter"]},
        ),
        await client.post(
            f"/api/v1/interviews/journal/tracks/{process['id']}/stages",
            headers=other_headers,
            json=stage_payload("screening"),
        ),
        await client.put(
            f"/api/v1/interviews/journal/tracks/{process['id']}/stages/{stage_id}",
            headers=other_headers,
            json=stage_payload("system_design"),
        ),
        await client.post(
            f"/api/v1/interviews/journal/tracks/{process['id']}/stages/{stage_id}/media/upload",
            headers=other_headers,
            json={"filename": "copy.mp4", "content_type": "video/mp4", "size": 10},
        ),
        await client.post(
            f"/api/v1/interviews/journal/tracks/{process['id']}/stages/{stage_id}/attachments/upload",
            headers=other_headers,
            json={"filename": "copy.txt", "content_type": "text/plain", "size": 10},
        ),
        await client.post(
            f"/api/v1/interviews/journal/tracks/{process['id']}/offer/upload",
            headers=other_headers,
            json={"filename": "offer.pdf", "content_type": "application/pdf", "size": 10},
        ),
    ]
    personal_listing = await client.get("/api/v1/interviews/journal/tracks", headers=other_headers)
    catalog_listing = await client.get(
        "/api/v1/interviews/catalog/companies?q=Яндекс", headers=other_headers
    )
    catalog_detail = await client.get(
        f"/api/v1/interviews/catalog/companies/{catalog_listing.json()['items'][0]['id']}",
        headers=other_headers,
    )

    assert all(response.status_code == 404 for response in attempts)
    assert personal_listing.json() == []
    assert catalog_detail.status_code == 200
    assert catalog_detail.json()["tracks"][0]["id"] == process["id"]
    assert catalog_detail.json()["tracks"][0]["track_title"] == "Python"


async def test_student_closes_process_with_required_reason(
    client: AsyncClient, seeded: SeededData
) -> None:
    process = await create_process(client, seeded)
    invalid = await client.patch(
        f"/api/v1/interviews/journal/tracks/{process['id']}/outcome",
        headers=auth(seeded.student_id),
        json={"status": "closed", "close_reason": ""},
    )
    closed = await client.patch(
        f"/api/v1/interviews/journal/tracks/{process['id']}/outcome",
        headers=auth(seeded.student_id),
        json={"status": "closed", "close_reason": "Не прошёл технический этап"},
    )
    add_after_close = await client.post(
        f"/api/v1/interviews/journal/tracks/{process['id']}/stages",
        headers=auth(seeded.student_id),
        json=stage_payload(),
    )
    active = await client.get(
        "/api/v1/interviews/journal/tracks?status=active",
        headers=auth(seeded.student_id),
    )
    history = await client.get(
        "/api/v1/interviews/journal/tracks?status=closed",
        headers=auth(seeded.student_id),
    )
    restored = await client.patch(
        f"/api/v1/interviews/journal/tracks/{process['id']}/outcome",
        headers=auth(seeded.student_id),
        json={"status": "active"},
    )
    add_after_restore = await client.post(
        f"/api/v1/interviews/journal/tracks/{process['id']}/stages",
        headers=auth(seeded.student_id),
        json=stage_payload(),
    )
    offer_after_restore = await client.patch(
        f"/api/v1/interviews/journal/tracks/{process['id']}/outcome",
        headers=auth(seeded.student_id),
        json={"status": "offer"},
    )

    assert invalid.status_code == 422
    assert closed.status_code == 200
    assert closed.json()["close_reason"] == "Не прошёл технический этап"
    assert closed.json()["closed_at"] is not None
    assert add_after_close.status_code == 409
    assert active.json() == []
    assert history.json()[0]["id"] == process["id"]
    assert restored.status_code == 200
    assert restored.json()["status"] == "active"
    assert restored.json()["close_reason"] == "Не прошёл технический этап"
    assert restored.json()["closed_at"] == closed.json()["closed_at"]
    assert add_after_restore.status_code == 200
    assert offer_after_restore.status_code == 200
    assert offer_after_restore.json()["status"] == "offer"
    assert offer_after_restore.json()["close_reason"] == "Не прошёл технический этап"


async def test_student_uploads_protected_stage_media(
    client: AsyncClient,
    seeded: SeededData,
    monkeypatch: MonkeyPatch,
) -> None:
    store = FakeInterviewUploadStore()
    monkeypatch.setattr(journal_router, "store", store)
    process = await create_process(client, seeded)
    stage_response = await client.post(
        f"/api/v1/interviews/journal/tracks/{process['id']}/stages",
        headers=auth(seeded.student_id),
        json=stage_payload(),
    )
    stage_id = stage_response.json()["stages"][0]["id"]
    intent = await client.post(
        f"/api/v1/interviews/journal/tracks/{process['id']}/stages/{stage_id}/media/upload",
        headers=auth(seeded.student_id),
        json={"filename": "recording.mp3", "content_type": "audio/mpeg", "size": 23},
    )
    uploaded = await client.post(
        f"/api/v1/interviews/journal/tracks/{process['id']}/stages/{stage_id}/media/complete",
        headers=auth(seeded.student_id),
        json={
            "storage_key": intent.json()["storage_key"],
            "filename": "recording.mp3",
            "content_type": "audio/mpeg",
            "size": 23,
        },
    )
    downloaded = await client.get(
        f"/api/v1/interviews/journal/tracks/{process['id']}/stages/{stage_id}/media",
        headers=auth(seeded.student_id),
    )
    viewed = await client.get(
        f"/api/v1/interviews/journal/tracks/{process['id']}/stages/{stage_id}/media?inline=true",
        headers=auth(seeded.student_id),
    )
    wrong_type = await client.post(
        f"/api/v1/interviews/journal/tracks/{process['id']}/stages/{stage_id}/media/upload",
        headers=auth(seeded.student_id),
        json={"filename": "notes.txt", "content_type": "text/plain", "size": 10},
    )

    assert intent.status_code == 200
    assert uploaded.status_code == 200
    assert uploaded.json()["stages"][0]["media"] == {
        "filename": "recording.mp3",
        "content_type": "audio/mpeg",
        "size": 23,
    }
    assert downloaded.status_code == 200
    assert downloaded.json()["url"].endswith("?mode=download")
    assert viewed.json()["url"].endswith("?mode=inline")
    assert wrong_type.status_code == 415


async def test_student_multipart_stage_media_complete_is_idempotent(
    client: AsyncClient,
    seeded: SeededData,
    monkeypatch: MonkeyPatch,
) -> None:
    store = FakeInterviewUploadStore()
    monkeypatch.setattr(journal_router, "store", store)
    process = await create_process(client, seeded)
    stage_response = await client.post(
        f"/api/v1/interviews/journal/tracks/{process['id']}/stages",
        headers=auth(seeded.student_id),
        json=stage_payload(),
    )
    stage_id = stage_response.json()["stages"][0]["id"]
    intent = await client.post(
        f"/api/v1/interviews/journal/tracks/{process['id']}/stages/{stage_id}/media/upload",
        headers=auth(seeded.student_id),
        json={
            "filename": "recording.mp4",
            "content_type": "video/mp4",
            "size": 1_024,
            "upload_protocol": "multipart-v1",
        },
    )
    complete_payload = {
        "storage_key": intent.json()["storage_key"],
        "filename": "recording.mp4",
        "content_type": "video/mp4",
        "size": 1_024,
        "upload_protocol": "multipart-v1",
        "upload_id": intent.json()["upload_id"],
        "upload_token": intent.json()["upload_token"],
        "parts": [{"part_number": 1, "etag": '"part-etag"'}],
    }
    first = await client.post(
        f"/api/v1/interviews/journal/tracks/{process['id']}/stages/{stage_id}/media/complete",
        headers=auth(seeded.student_id),
        json=complete_payload,
    )
    async with TestSession() as session:
        stage = await session.get(InterviewProcessStage, UUID(stage_id))
        assert stage is not None
        stage.ai_analysis_requested_at = datetime.now(UTC)
        await session.commit()
    retried = await client.post(
        f"/api/v1/interviews/journal/tracks/{process['id']}/stages/{stage_id}/media/complete",
        headers=auth(seeded.student_id),
        json=complete_payload,
    )

    assert intent.status_code == 200
    assert intent.json()["upload_protocol"] == "multipart-v1"
    assert intent.json()["part_count"] == 1
    assert first.status_code == 200
    assert retried.status_code == 200
    assert first.json()["stages"][0]["media"] == retried.json()["stages"][0]["media"]
    assert store.deleted == []


async def test_failed_response_cleanup_preserves_referenced_upload(
    client: AsyncClient,
    seeded: SeededData,
) -> None:
    store = FakeInterviewUploadStore()
    process = await create_process(client, seeded)
    stage_response = await client.post(
        f"/api/v1/interviews/journal/tracks/{process['id']}/stages",
        headers=auth(seeded.student_id),
        json=stage_payload(),
    )
    stage_id = UUID(stage_response.json()["stages"][0]["id"])
    referenced_key = f"media/{seeded.student_id}/{uuid4().hex}"

    async with TestSession() as session:
        stage = await session.get(InterviewProcessStage, stage_id)
        assert stage is not None
        stage.media_storage_key = referenced_key
        stage.media_filename = "recording.mp4"
        stage.media_content_type = "video/mp4"
        stage.media_size = 1_024
        await session.commit()

        referenced_deleted = await delete_upload_if_unreferenced(
            session,
            store,
            referenced_key,
        )
        orphan_key = f"media/{seeded.student_id}/{uuid4().hex}"
        orphan_deleted = await delete_upload_if_unreferenced(
            session,
            store,
            orphan_key,
        )

    assert referenced_deleted is False
    assert orphan_deleted is True
    assert store.deleted == [orphan_key]


async def test_student_adds_opens_and_deletes_stage_attachments(
    client: AsyncClient,
    seeded: SeededData,
    monkeypatch: MonkeyPatch,
) -> None:
    store = FakeInterviewUploadStore()
    monkeypatch.setattr(journal_router, "store", store)
    process = await create_process(client, seeded)
    stage_response = await client.post(
        f"/api/v1/interviews/journal/tracks/{process['id']}/stages",
        headers=auth(seeded.student_id),
        json=stage_payload(),
    )
    stage_id = stage_response.json()["stages"][0]["id"]
    intent = await client.post(
        f"/api/v1/interviews/journal/tracks/{process['id']}/stages/{stage_id}/attachments/upload",
        headers=auth(seeded.student_id),
        json={"filename": "diagram.png", "content_type": "image/png", "size": 42},
    )
    uploaded = await client.post(
        f"/api/v1/interviews/journal/tracks/{process['id']}/stages/{stage_id}/attachments/complete",
        headers=auth(seeded.student_id),
        json={
            "storage_key": intent.json()["storage_key"],
            "filename": "diagram.png",
            "content_type": "image/png",
            "size": 42,
        },
    )
    retried = await client.post(
        f"/api/v1/interviews/journal/tracks/{process['id']}/stages/{stage_id}/attachments/complete",
        headers=auth(seeded.student_id),
        json={
            "storage_key": intent.json()["storage_key"],
            "filename": "diagram.png",
            "content_type": "image/png",
            "size": 42,
        },
    )
    attachment = uploaded.json()["stages"][0]["attachments"][0]
    viewed = await client.get(
        f"/api/v1/interviews/journal/tracks/{process['id']}/stages/{stage_id}/attachments/{attachment['id']}?inline=true",
        headers=auth(seeded.student_id),
    )
    downloaded = await client.get(
        f"/api/v1/interviews/journal/tracks/{process['id']}/stages/{stage_id}/attachments/{attachment['id']}",
        headers=auth(seeded.student_id),
    )
    deleted = await client.delete(
        f"/api/v1/interviews/journal/tracks/{process['id']}/stages/{stage_id}/attachments/{attachment['id']}",
        headers=auth(seeded.student_id),
    )

    assert intent.status_code == 200
    assert uploaded.status_code == 200
    assert retried.status_code == 200
    assert len(retried.json()["stages"][0]["attachments"]) == 1
    assert attachment["filename"] == "diagram.png"
    assert attachment["content_type"] == "image/png"
    assert viewed.json()["url"].endswith("?mode=inline")
    assert downloaded.json()["url"].endswith("?mode=download")
    assert deleted.status_code == 204
    assert any(key.startswith("attachments/") for key in store.deleted)


async def test_attachment_complete_retry_succeeds_at_capacity(
    client: AsyncClient,
    seeded: SeededData,
    monkeypatch: MonkeyPatch,
) -> None:
    store = FakeInterviewUploadStore()
    monkeypatch.setattr(journal_router, "store", store)
    process = await create_process(client, seeded)
    stage_response = await client.post(
        f"/api/v1/interviews/journal/tracks/{process['id']}/stages",
        headers=auth(seeded.student_id),
        json=stage_payload(),
    )
    stage_id = UUID(stage_response.json()["stages"][0]["id"])
    existing_key = f"attachments/{seeded.student_id}/{uuid4().hex}"
    async with TestSession() as session:
        session.add_all(
            [
                InterviewProcessStageAttachment(
                    stage_id=stage_id,
                    storage_key=existing_key if index == 0 else f"attachments/{uuid4().hex}",
                    filename=f"attachment-{index}.txt",
                    content_type="text/plain",
                    size=42,
                )
                for index in range(20)
            ]
        )
        await session.commit()

    response = await client.post(
        f"/api/v1/interviews/journal/tracks/{process['id']}/stages/{stage_id}/attachments/complete",
        headers=auth(seeded.student_id),
        json={
            "storage_key": f"pending/{existing_key}",
            "filename": "attachment-0.txt",
            "content_type": "text/plain",
            "size": 42,
        },
    )

    assert response.status_code == 200
    assert len(response.json()["stages"][0]["attachments"]) == 20
    assert store.deleted == []


async def test_video_upload_is_limited_to_two_gibibytes(
    client: AsyncClient, seeded: SeededData
) -> None:
    process = await create_process(client, seeded)
    stage_response = await client.post(
        f"/api/v1/interviews/journal/tracks/{process['id']}/stages",
        headers=auth(seeded.student_id),
        json=stage_payload(),
    )
    stage_id = stage_response.json()["stages"][0]["id"]
    allowed = await client.post(
        f"/api/v1/interviews/journal/tracks/{process['id']}/stages/{stage_id}/media/upload",
        headers=auth(seeded.student_id),
        json={
            "filename": "recording.mp4",
            "content_type": "video/mp4",
            "size": 2 * 1024 * 1024 * 1024,
        },
    )
    rejected = await client.post(
        f"/api/v1/interviews/journal/tracks/{process['id']}/stages/{stage_id}/media/upload",
        headers=auth(seeded.student_id),
        json={
            "filename": "too-large.mp4",
            "content_type": "video/mp4",
            "size": 2 * 1024 * 1024 * 1024 + 1,
        },
    )
    oversized_attachment = await client.post(
        f"/api/v1/interviews/journal/tracks/{process['id']}/stages/{stage_id}/attachments/upload",
        headers=auth(seeded.student_id),
        json={
            "filename": "notes.txt",
            "content_type": "text/plain",
            "size": 50 * 1024 * 1024 + 1,
        },
    )

    assert allowed.status_code == 200
    assert rejected.status_code == 413
    assert rejected.json()["detail"]["code"] == "interview_file_too_large"
    assert oversized_attachment.status_code == 413


async def test_offer_file_is_private_and_owned_by_student(
    client: AsyncClient,
    seeded: SeededData,
    monkeypatch: MonkeyPatch,
) -> None:
    store = FakeInterviewUploadStore()
    monkeypatch.setattr(journal_router, "store", store)
    process = await create_process(client, seeded, "Ozon")
    marked = await client.patch(
        f"/api/v1/interviews/journal/tracks/{process['id']}/outcome",
        headers=auth(seeded.student_id),
        json={"status": "offer"},
    )
    intent = await client.post(
        f"/api/v1/interviews/journal/tracks/{process['id']}/offer/upload",
        headers=auth(seeded.student_id),
        json={"filename": "offer.pdf", "content_type": "application/pdf", "size": 18},
    )
    uploaded = await client.post(
        f"/api/v1/interviews/journal/tracks/{process['id']}/offer/complete",
        headers=auth(seeded.student_id),
        json={
            "storage_key": intent.json()["storage_key"],
            "filename": "offer.pdf",
            "content_type": "application/pdf",
            "size": 18,
        },
    )
    downloaded = await client.get(
        f"/api/v1/interviews/journal/tracks/{process['id']}/offer",
        headers=auth(seeded.student_id),
    )

    other_student_id = uuid4()
    async with TestSession() as session:
        session.add(User(id=other_student_id, first_name="Чужой", role=UserRole.STUDENT))
        await session.commit()
    forbidden_file = await client.get(
        f"/api/v1/interviews/journal/tracks/{process['id']}/offer",
        headers=auth(other_student_id),
    )
    cancelled = await client.delete(
        f"/api/v1/interviews/journal/tracks/{process['id']}/offer",
        headers=auth(seeded.student_id),
    )
    reopened = await client.get(
        f"/api/v1/interviews/journal/tracks/{process['id']}",
        headers=auth(seeded.student_id),
    )
    cancelled_twice = await client.delete(
        f"/api/v1/interviews/journal/tracks/{process['id']}/offer",
        headers=auth(seeded.student_id),
    )

    assert marked.json()["status"] == "offer"
    assert uploaded.status_code == 200
    assert uploaded.json()["offer"]["filename"] == "offer.pdf"
    assert downloaded.status_code == 200
    assert forbidden_file.status_code == 404
    assert cancelled.status_code == 204
    assert reopened.json()["status"] == "active"
    assert reopened.json()["offer"] is None
    assert store.deleted == [intent.json()["storage_key"].replace("pending/", "", 1)]
    assert cancelled_twice.status_code == 409
