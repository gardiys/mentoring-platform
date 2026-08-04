from datetime import UTC, datetime, timedelta
from uuid import uuid4

from httpx import AsyncClient
from pytest import MonkeyPatch

from app.interviews import catalog_router
from app.interviews.models import (
    InterviewProcess,
    InterviewProcessStage,
    InterviewProcessStageAttachment,
    InterviewProcessStatus,
)
from app.interviews.uploads import StoredUpload
from app.tracks.models import LearningTrackEnrollment
from app.users.models import User, UserRole
from tests.conftest import SeededData, TestSession, auth


class FakeCatalogStore:
    def __init__(self) -> None:
        self.playback_urls: list[tuple[StoredUpload, bool, int | None]] = []

    def download_url(
        self,
        upload: StoredUpload,
        *,
        inline: bool = False,
        expires_in: int | None = None,
    ) -> str:
        self.playback_urls.append((upload, inline, expires_in))
        mode = "inline" if inline else "download"
        ttl = f"&ttl={expires_in}" if expires_in is not None else ""
        return f"https://s3.example.test/{upload.storage_key}?mode={mode}{ttl}"


async def test_students_browse_company_tracks_files_and_comments(
    client: AsyncClient,
    seeded: SeededData,
    monkeypatch: MonkeyPatch,
) -> None:
    fake_store = FakeCatalogStore()
    monkeypatch.setattr(catalog_router, "store", fake_store)
    second_student_id = uuid4()
    async with TestSession() as session:
        owner = await session.get(User, seeded.student_id)
        assert owner is not None
        owner.last_name = "СкрытаяФамилия"
        owner.telegram_username = "ivan_backend"
        session.add(
            User(
                id=second_student_id,
                first_name="Мария",
                last_name="Петрова",
                telegram_username="maria_go",
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

    process = await client.post(
        "/api/v1/interviews/journal/tracks",
        headers=auth(seeded.student_id),
        json={
            "company_name": "ООО Яндекс",
            "track_id": str(seeded.python_track_id),
            "recruiter_telegram_usernames": ["@yandex_recruiter"],
        },
    )
    stage = await client.post(
        f"/api/v1/interviews/journal/tracks/{process.json()['id']}/stages",
        headers=auth(seeded.student_id),
        json={
            "stage_type": "technical_interview",
            "scheduled_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
            "description": "Алгоритмы, Python и проектирование API",
        },
    )
    stage_id = stage.json()["stages"][0]["id"]
    attachment_id = uuid4()
    async with TestSession() as session:
        stage_model = await session.get(InterviewProcessStage, stage_id)
        assert stage_model is not None
        process_model = await session.get(InterviewProcess, process.json()["id"])
        assert process_model is not None
        process_model.status = InterviewProcessStatus.OFFER
        stage_model.media_storage_key = f"media/{seeded.student_id}/recording"
        stage_model.media_filename = "interview.mp4"
        stage_model.media_content_type = "video/mp4"
        stage_model.media_size = 1024
        session.add(
            InterviewProcessStageAttachment(
                id=attachment_id,
                stage_id=stage_model.id,
                storage_key=f"attachments/{seeded.student_id}/diagram",
                filename="diagram.png",
                content_type="image/png",
                size=512,
            )
        )
        await session.commit()

    listing = await client.get(
        "/api/v1/interviews/catalog/companies?q=Yandex",
        headers=auth(second_student_id),
    )
    authors = await client.get(
        "/api/v1/interviews/catalog/authors",
        headers=auth(second_student_id),
    )
    company_id = listing.json()["items"][0]["id"]
    author_listing = await client.get(
        f"/api/v1/interviews/catalog/companies?author_id={seeded.student_id}",
        headers=auth(second_student_id),
    )
    other_author_listing = await client.get(
        f"/api/v1/interviews/catalog/companies?author_id={second_student_id}",
        headers=auth(second_student_id),
    )
    filtered_listing = await client.get(
        "/api/v1/interviews/catalog/companies"
        "?stage_type=technical_interview&has_offer=true&media_kind=video",
        headers=auth(second_student_id),
    )
    wrong_media_listing = await client.get(
        "/api/v1/interviews/catalog/companies?media_kind=audio",
        headers=auth(second_student_id),
    )
    any_recording_listing = await client.get(
        "/api/v1/interviews/catalog/companies?media_kind=any",
        headers=auth(second_student_id),
    )
    wrong_stage_listing = await client.get(
        "/api/v1/interviews/catalog/companies?stage_type=screening&media_kind=video",
        headers=auth(second_student_id),
    )
    comment = await client.post(
        f"/api/v1/interviews/catalog/stages/{stage_id}/comments",
        headers=auth(second_student_id),
        json={"body": "Стоит отдельно повторить оценку сложности алгоритмов"},
    )
    detail = await client.get(
        f"/api/v1/interviews/catalog/companies/{company_id}",
        headers=auth(second_student_id),
    )
    author_detail = await client.get(
        f"/api/v1/interviews/catalog/companies/{company_id}?author_id={seeded.student_id}",
        headers=auth(second_student_id),
    )
    other_author_detail = await client.get(
        f"/api/v1/interviews/catalog/companies/{company_id}?author_id={second_student_id}",
        headers=auth(second_student_id),
    )
    filtered_detail = await client.get(
        f"/api/v1/interviews/catalog/companies/{company_id}"
        "?stage_type=technical_interview&has_offer=true&media_kind=video",
        headers=auth(second_student_id),
    )
    missing_ticket = await client.get(
        f"/api/v1/interviews/catalog/stages/{stage_id}/media/stream",
        headers={"Range": "bytes=0-"},
    )
    media = await client.get(
        f"/api/v1/interviews/catalog/stages/{stage_id}/media",
        headers=auth(second_student_id),
    )
    stream = await client.get(
        media.json()["url"],
        headers={"Range": "bytes=0-", "Sec-Fetch-Dest": "video"},
    )
    copied_to_another_browser = await client.get(
        media.json()["url"],
        headers={
            "Range": "bytes=0-",
            "Sec-Fetch-Dest": "video",
            "User-Agent": "another-browser",
        },
    )
    attachment = await client.get(
        f"/api/v1/interviews/catalog/stages/{stage_id}/attachments/{attachment_id}?inline=true",
        headers=auth(second_student_id),
    )
    mentor_listing = await client.get(
        "/api/v1/interviews/catalog/companies",
        headers=auth(seeded.mentor_id),
    )
    cannot_delete_other_comment = await client.delete(
        f"/api/v1/interviews/catalog/comments/{comment.json()['id']}",
        headers=auth(seeded.student_id),
    )
    deleted = await client.delete(
        f"/api/v1/interviews/catalog/comments/{comment.json()['id']}",
        headers=auth(second_student_id),
    )

    assert listing.status_code == 200
    assert listing.json()["items"][0]["name"] == "Яндекс"
    assert listing.json()["items"][0]["track_count"] == 1
    assert listing.json()["items"][0]["interview_count"] == 1
    assert authors.json() == [
        {
            "id": str(seeded.student_id),
            "name": "Иван",
            "telegram_username": "ivan_backend",
        }
    ]
    assert "СкрытаяФамилия" not in authors.text
    assert author_listing.json()["items"][0]["id"] == company_id
    assert other_author_listing.json()["items"] == []
    assert len(author_detail.json()["tracks"]) == 1
    assert other_author_detail.json()["tracks"] == []
    assert filtered_listing.status_code == 200
    assert filtered_listing.json()["items"][0]["id"] == company_id
    assert wrong_media_listing.json()["items"] == []
    assert any_recording_listing.json()["items"][0]["id"] == company_id
    assert wrong_stage_listing.json()["items"] == []
    assert detail.status_code == 200
    catalog_stage = detail.json()["tracks"][0]["stages"][0]
    author = detail.json()["tracks"][0]["author"]
    assert author == {
        "id": str(seeded.student_id),
        "name": "Иван",
        "telegram_username": "ivan_backend",
    }
    assert detail.json()["tracks"][0]["recruiter_telegram_usernames"] == ["yandex_recruiter"]
    assert "СкрытаяФамилия" not in detail.text
    comment_author = catalog_stage["comments"][0]["author"]
    assert comment_author["name"] == "Мария"
    assert comment_author["telegram_username"] == "maria_go"
    assert "Петрова" not in detail.text
    assert catalog_stage["description"].startswith("Алгоритмы")
    assert catalog_stage["attachments"][0]["filename"] == "diagram.png"
    assert catalog_stage["comments"][0]["is_own"] is True
    assert len(filtered_detail.json()["tracks"]) == 1
    assert missing_ticket.status_code == 401
    assert media.json()["url"].endswith(f"/{stage_id}/media/stream")
    assert "s3.example.test" not in media.json()["url"]
    assert "httponly" in media.headers["set-cookie"].lower()
    assert stream.status_code == 307
    assert stream.headers["location"].startswith("https://s3.example.test/")
    assert stream.headers["location"].endswith("?mode=inline&ttl=60")
    assert stream.headers["cache-control"] == "private, no-store, max-age=0"
    assert any(
        inline is True and expires_in == 60
        for _upload, inline, expires_in in fake_store.playback_urls
    )
    assert copied_to_another_browser.status_code == 401
    assert attachment.json()["url"].endswith("?mode=inline")
    assert mentor_listing.status_code == 200
    assert mentor_listing.json()["items"][0]["id"] == company_id
    assert cannot_delete_other_comment.status_code == 404
    assert deleted.status_code == 204


async def test_catalog_is_scoped_and_filtered_by_student_directions(
    client: AsyncClient,
    seeded: SeededData,
) -> None:
    go_student_id = uuid4()
    dual_student_id = uuid4()
    student_without_direction_id = uuid4()
    async with TestSession() as session:
        session.add_all(
            [
                User(id=go_student_id, first_name="Go", role=UserRole.STUDENT),
                User(id=dual_student_id, first_name="Fullstack", role=UserRole.STUDENT),
                User(
                    id=student_without_direction_id,
                    first_name="Без направления",
                    role=UserRole.STUDENT,
                ),
            ]
        )
        await session.flush()
        session.add_all(
            [
                LearningTrackEnrollment(
                    user_id=go_student_id,
                    track_id=seeded.go_track_id,
                ),
                LearningTrackEnrollment(
                    user_id=dual_student_id,
                    track_id=seeded.python_track_id,
                ),
                LearningTrackEnrollment(
                    user_id=dual_student_id,
                    track_id=seeded.go_track_id,
                ),
            ]
        )
        await session.commit()

    python_process = await client.post(
        "/api/v1/interviews/journal/tracks",
        headers=auth(seeded.student_id),
        json={"company_name": "ООО Авито", "track_id": str(seeded.python_track_id)},
    )
    go_process = await client.post(
        "/api/v1/interviews/journal/tracks",
        headers=auth(seeded.admin_id),
        json={"company_name": "Авито", "track_id": str(seeded.go_track_id)},
    )
    python_stage = await client.post(
        f"/api/v1/interviews/journal/tracks/{python_process.json()['id']}/stages",
        headers=auth(seeded.student_id),
        json={
            "stage_type": "technical_interview",
            "scheduled_at": datetime.now(UTC).isoformat(),
            "description": "Python interview",
        },
    )
    await client.post(
        f"/api/v1/interviews/journal/tracks/{go_process.json()['id']}/stages",
        headers=auth(seeded.admin_id),
        json={
            "stage_type": "technical_interview",
            "scheduled_at": datetime.now(UTC).isoformat(),
            "description": "Go interview",
        },
    )
    python_stage_id = python_stage.json()["stages"][0]["id"]

    python_directions = await client.get(
        "/api/v1/interviews/catalog/directions",
        headers=auth(seeded.student_id),
    )
    go_directions = await client.get(
        "/api/v1/interviews/catalog/directions", headers=auth(go_student_id)
    )
    dual_directions = await client.get(
        "/api/v1/interviews/catalog/directions", headers=auth(dual_student_id)
    )
    python_listing = await client.get(
        "/api/v1/interviews/catalog/companies?q=Avito",
        headers=auth(seeded.student_id),
    )
    go_listing = await client.get(
        "/api/v1/interviews/catalog/companies?q=Avito", headers=auth(go_student_id)
    )
    dual_listing = await client.get(
        "/api/v1/interviews/catalog/companies?q=Avito", headers=auth(dual_student_id)
    )
    no_direction_listing = await client.get(
        "/api/v1/interviews/catalog/companies?q=Avito",
        headers=auth(student_without_direction_id),
    )

    assert python_process.status_code == 201
    assert go_process.status_code == 201
    assert [item["slug"] for item in python_directions.json()] == ["python"]
    assert [item["slug"] for item in go_directions.json()] == ["go"]
    assert [item["slug"] for item in dual_directions.json()] == ["python", "go"]
    assert python_listing.json()["items"][0]["track_count"] == 1
    assert go_listing.json()["items"][0]["track_count"] == 1
    assert dual_listing.json()["items"][0]["track_count"] == 2
    assert no_direction_listing.json()["items"] == []

    company_id = dual_listing.json()["items"][0]["id"]
    python_detail = await client.get(
        f"/api/v1/interviews/catalog/companies/{company_id}",
        headers=auth(seeded.student_id),
    )
    go_detail = await client.get(
        f"/api/v1/interviews/catalog/companies/{company_id}",
        headers=auth(go_student_id),
    )
    dual_python_filter = await client.get(
        f"/api/v1/interviews/catalog/companies/{company_id}?track_id={seeded.python_track_id}",
        headers=auth(dual_student_id),
    )
    hidden_python_stage = await client.post(
        f"/api/v1/interviews/catalog/stages/{python_stage_id}/comments",
        headers=auth(go_student_id),
        json={"body": "Should not be visible"},
    )
    unavailable_company = await client.get(
        f"/api/v1/interviews/catalog/companies/{company_id}",
        headers=auth(student_without_direction_id),
    )

    assert {track["track_slug"] for track in python_detail.json()["tracks"]} == {"python"}
    assert {track["track_slug"] for track in go_detail.json()["tracks"]} == {"go"}
    assert {track["track_slug"] for track in dual_python_filter.json()["tracks"]} == {"python"}
    assert hidden_python_stage.status_code == 404
    assert unavailable_company.status_code == 404


async def test_admin_sees_all_catalog_directions_and_interview_tracks(
    client: AsyncClient, seeded: SeededData
) -> None:
    created = await client.post(
        "/api/v1/interviews/journal/tracks",
        headers=auth(seeded.student_id),
        json={
            "company_name": "Admin Catalog Company",
            "track_id": str(seeded.python_track_id),
        },
    )

    directions = await client.get(
        "/api/v1/interviews/catalog/directions", headers=auth(seeded.admin_id)
    )
    companies = await client.get(
        "/api/v1/interviews/catalog/companies?q=Admin Catalog Company",
        headers=auth(seeded.admin_id),
    )
    processes = await client.get(
        "/api/v1/admin/interviews/processes", headers=auth(seeded.admin_id)
    )

    assert created.status_code == 201
    assert {item["slug"] for item in directions.json()} == {"python", "go"}
    assert companies.status_code == 200
    assert companies.json()["total"] == 1
    assert companies.json()["limit"] == 24
    assert companies.json()["items"][0]["name"] == created.json()["company_name"]
    assert processes.status_code == 200
    assert processes.json()["total"] == 1
    assert processes.json()["items"][0]["id"] == created.json()["id"]
    assert processes.json()["items"][0]["author"]["id"] == str(seeded.student_id)
    assert processes.json()["items"][0]["company_id"] == companies.json()["items"][0]["id"]
