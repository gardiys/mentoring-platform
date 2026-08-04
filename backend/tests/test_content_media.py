from uuid import UUID, uuid4

from httpx import AsyncClient
from pytest import MonkeyPatch

from app.core.errors import api_error
from app.interviews.uploads import OpenedDownload, StoredUpload, UploadIntent
from app.media import router as media_router
from tests.conftest import SeededData, auth


class FakeStreamingBody:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def iter_chunks(self, chunk_size: int) -> list[bytes]:
        del chunk_size
        return [self.content]

    def close(self) -> None:
        return None


class FakePrivateMediaStore:
    def __init__(self) -> None:
        self.pending: dict[str, tuple[UUID, str, str, str, int]] = {}
        self.deleted: list[str] = []

    def create_upload_intent(self, **kwargs: object) -> UploadIntent:
        user_id = UUID(str(kwargs["user_id"]))
        category = str(kwargs["category"])
        storage_key = f"pending/{category}/{user_id}/{uuid4().hex}"
        filename = str(kwargs["filename"])
        content_type = str(kwargs["content_type"])
        size = int(kwargs["size"])
        self.pending[storage_key] = (
            user_id,
            category,
            filename,
            content_type,
            size,
        )
        return UploadIntent(
            upload_url="https://s3.example.test/private-upload",
            fields={"key": storage_key, "policy": "signed"},
            storage_key=storage_key,
            filename=filename,
            content_type=content_type,
            size=size,
            expires_in=900,
        )

    async def complete_upload(self, **kwargs: object) -> StoredUpload:
        storage_key = str(kwargs["storage_key"])
        user_id = UUID(str(kwargs["user_id"]))
        category = str(kwargs["category"])
        expected = self.pending.get(storage_key)
        supplied = (
            user_id,
            category,
            str(kwargs["filename"]),
            str(kwargs["content_type"]),
            int(kwargs["expected_size"]),
        )
        if expected is None or expected != supplied:
            api_error(
                404,
                "content_media_upload_not_found",
                "Media upload was not found",
            )
        del self.pending[storage_key]
        return StoredUpload(
            storage_key=storage_key.removeprefix("pending/"),
            filename=supplied[2],
            content_type=supplied[3],
            size=supplied[4],
        )

    async def open_download(
        self,
        upload: StoredUpload,
        *,
        range_header: str | None,
    ) -> OpenedDownload:
        del upload
        return OpenedDownload(
            body=FakeStreamingBody(b"media"),
            content_length=5,
            content_range="bytes 0-4/5" if range_header else None,
            etag='"protected-media"',
        )

    async def delete(self, storage_key: str | None) -> None:
        if storage_key is not None:
            self.deleted.append(storage_key)


async def create_knowledge_entry(
    client: AsyncClient,
    seeded: SeededData,
) -> tuple[str, str, str]:
    created = await client.post(
        "/api/v1/admin/knowledge/topics",
        headers=auth(seeded.admin_id),
        json={
            "slug": "private-media",
            "title": "Приватные материалы",
            "description": None,
            "position": 0,
            "is_published": True,
            "track_ids": [str(seeded.python_track_id)],
            "entries": [
                {
                    "kind": "article",
                    "slug": "private-media-video",
                    "title": "Видео по Python",
                    "summary": None,
                    "content_markdown": "# Видео",
                    "position": 0,
                    "is_published": True,
                }
            ],
        },
    )
    assert created.status_code == 201, created.text
    payload = created.json()
    return payload["id"], payload["entries"][0]["id"], payload["entries"][0]["slug"]


async def test_knowledge_media_private_upload_playback_scope_and_delete(
    client: AsyncClient,
    seeded: SeededData,
    monkeypatch: MonkeyPatch,
) -> None:
    fake_store = FakePrivateMediaStore()
    monkeypatch.setattr(media_router, "store", fake_store)
    topic_id, entry_id, entry_slug = await create_knowledge_entry(client, seeded)
    upload_path = f"/api/v1/admin/knowledge/topics/{topic_id}/entries/{entry_id}/media/upload-url"
    finalize_path = f"/api/v1/admin/knowledge/topics/{topic_id}/entries/{entry_id}/media/finalize"
    upload_payload = {
        "filename": "lesson.mp4",
        "content_type": "video/mp4",
        "size": 1_024,
    }

    student_upload = await client.post(
        upload_path,
        headers=auth(seeded.student_id),
        json=upload_payload,
    )
    invalid_type = await client.post(
        upload_path,
        headers=auth(seeded.admin_id),
        json={**upload_payload, "filename": "notes.pdf", "content_type": "application/pdf"},
    )
    larger_than_interview_limit = await client.post(
        upload_path,
        headers=auth(seeded.admin_id),
        json={
            **upload_payload,
            "filename": "long-lesson.mp4",
            "size": media_router.settings.interview_video_max_bytes + 1,
        },
    )
    too_large = await client.post(
        upload_path,
        headers=auth(seeded.admin_id),
        json={**upload_payload, "size": media_router.settings.content_video_max_bytes + 1},
    )
    intent = await client.post(
        upload_path,
        headers=auth(seeded.admin_id),
        json=upload_payload,
    )

    assert student_upload.status_code == 403
    assert invalid_type.status_code == 415
    assert invalid_type.json()["detail"]["code"] == "unsupported_content_media_type"
    assert (
        media_router.settings.content_video_max_bytes
        > media_router.settings.interview_video_max_bytes
    )
    assert larger_than_interview_limit.status_code == 200
    assert too_large.status_code == 413
    assert too_large.json()["detail"]["code"] == "content_media_too_large"
    assert intent.status_code == 200, intent.text
    assert intent.json()["storage_key"].startswith(f"pending/knowledge-media/{seeded.admin_id}/")

    foreign_finalize = await client.post(
        finalize_path,
        headers=auth(seeded.admin_id),
        json={
            **upload_payload,
            "storage_key": f"pending/knowledge-media/{seeded.student_id}/{uuid4().hex}",
            "position": 0,
        },
    )
    overflowing_position = await client.post(
        finalize_path,
        headers=auth(seeded.admin_id),
        json={
            **upload_payload,
            "storage_key": intent.json()["storage_key"],
            "position": 2_147_483_648,
        },
    )
    finalized = await client.post(
        finalize_path,
        headers=auth(seeded.admin_id),
        json={
            **upload_payload,
            "storage_key": intent.json()["storage_key"],
            "title": "Разбор event loop",
            "position": 2,
        },
    )

    assert foreign_finalize.status_code == 404
    assert overflowing_position.status_code == 422
    assert finalized.status_code == 201, finalized.text
    media_id = finalized.json()["id"]
    assert finalized.json()["kind"] == "video"
    assert finalized.json()["title"] == "Разбор event loop"
    assert "storage_key" not in finalized.json()
    assert "url" not in finalized.json()

    admin_entry = await client.get(
        f"/api/v1/admin/knowledge/topics/{topic_id}/entries/{entry_id}",
        headers=auth(seeded.admin_id),
    )
    public_entry = await client.get(
        f"/api/v1/knowledge/entries/{entry_slug}",
        headers=auth(seeded.student_id),
    )
    missing_ticket = await client.get(
        f"/api/v1/knowledge/entries/{entry_slug}/media/{media_id}/stream",
        headers={"Range": "bytes=0-"},
    )
    wrong_direction = await client.get(
        f"/api/v1/knowledge/entries/{entry_slug}/media/{media_id}/playback",
        headers=auth(seeded.other_mentor_id),
    )
    playback = await client.get(
        f"/api/v1/knowledge/entries/{entry_slug}/media/{media_id}/playback",
        headers=auth(seeded.student_id),
    )
    stream = await client.get(
        playback.json()["url"],
        headers={"Range": "bytes=0-", "Sec-Fetch-Dest": "video"},
    )
    copied_ticket = await client.get(
        playback.json()["url"],
        headers={
            "Range": "bytes=0-",
            "Sec-Fetch-Dest": "video",
            "User-Agent": "another-browser",
        },
    )
    browser_fetch = await client.get(
        playback.json()["url"],
        headers={"Range": "bytes=0-", "Sec-Fetch-Dest": "document"},
    )
    invalid_range = await client.get(
        playback.json()["url"],
        headers={"Range": "items=0-1", "Sec-Fetch-Dest": "video"},
    )

    assert admin_entry.status_code == public_entry.status_code == 200
    assert admin_entry.json()["media"][0]["id"] == media_id
    assert public_entry.json()["media"][0]["filename"] == "lesson.mp4"
    assert missing_ticket.status_code == 401
    assert wrong_direction.status_code == 404
    assert playback.status_code == 200, playback.text
    assert playback.json()["url"].startswith("/api/v1/")
    assert (
        playback.json()["expires_in"] == media_router.settings.interview_stream_ticket_ttl_seconds
    )
    assert "s3.example.test" not in playback.json()["url"]
    assert "httponly" in playback.headers["set-cookie"].lower()
    assert stream.status_code == 206
    assert stream.content == b"media"
    assert stream.headers["content-range"] == "bytes 0-4/5"
    assert stream.headers["cache-control"] == "private, no-store, max-age=0"
    assert copied_ticket.status_code == 401
    assert browser_fetch.status_code == 403
    assert browser_fetch.json()["detail"]["code"] == "content_media_player_required"
    assert invalid_range.status_code == 416

    topic_editor = await client.get(
        f"/api/v1/admin/knowledge/topics/{topic_id}",
        headers=auth(seeded.admin_id),
    )
    bulk_payload = topic_editor.json()
    bulk_payload.pop("id")
    bulk_payload["entries"] = []
    protected_bulk_removal = await client.put(
        f"/api/v1/admin/knowledge/topics/{topic_id}",
        headers=auth(seeded.admin_id),
        json=bulk_payload,
    )
    assert protected_bulk_removal.status_code == 409
    assert protected_bulk_removal.json()["detail"]["code"] == "knowledge_entry_has_media"

    student_delete = await client.delete(
        f"/api/v1/admin/knowledge/topics/{topic_id}/entries/{entry_id}/media/{media_id}",
        headers=auth(seeded.student_id),
    )
    wrong_parent_delete = await client.delete(
        f"/api/v1/admin/knowledge/topics/{topic_id}/entries/{uuid4()}/media/{media_id}",
        headers=auth(seeded.admin_id),
    )
    deleted = await client.delete(
        f"/api/v1/admin/knowledge/topics/{topic_id}/entries/{entry_id}/media/{media_id}",
        headers=auth(seeded.admin_id),
    )
    after_delete = await client.get(
        f"/api/v1/knowledge/entries/{entry_slug}",
        headers=auth(seeded.student_id),
    )

    assert student_delete.status_code == 403
    assert wrong_parent_delete.status_code == 404
    assert deleted.status_code == 204
    assert after_delete.json()["media"] == []
    assert fake_store.deleted == [intent.json()["storage_key"].removeprefix("pending/")]


async def test_roadmap_media_private_upload_and_track_scoped_playback(
    client: AsyncClient,
    seeded: SeededData,
    monkeypatch: MonkeyPatch,
) -> None:
    fake_store = FakePrivateMediaStore()
    monkeypatch.setattr(media_router, "store", fake_store)
    roadmap = await client.get(
        f"/api/v1/admin/roadmaps/{seeded.roadmap_id}",
        headers=auth(seeded.admin_id),
    )
    assert roadmap.status_code == 200, roadmap.text
    section_id = roadmap.json()["sections"][0]["id"]
    topic_id = str(seeded.topic_ids[0])
    base_path = (
        f"/api/v1/admin/roadmaps/{seeded.roadmap_id}/sections/{section_id}/topics/{topic_id}/media"
    )
    upload_payload = {
        "filename": "lesson.mp3",
        "content_type": "audio/mpeg",
        "size": 2_048,
    }

    wrong_hierarchy = await client.post(
        (
            f"/api/v1/admin/roadmaps/{seeded.hidden_roadmap_id}/sections/{section_id}"
            f"/topics/{topic_id}/media/upload-url"
        ),
        headers=auth(seeded.admin_id),
        json=upload_payload,
    )
    larger_than_interview_limit = await client.post(
        f"{base_path}/upload-url",
        headers=auth(seeded.admin_id),
        json={
            "filename": "long-roadmap-lesson.mp4",
            "content_type": "video/mp4",
            "size": media_router.settings.interview_video_max_bytes + 1,
        },
    )
    too_large_video = await client.post(
        f"{base_path}/upload-url",
        headers=auth(seeded.admin_id),
        json={
            "filename": "too-large-roadmap-lesson.mp4",
            "content_type": "video/mp4",
            "size": media_router.settings.content_video_max_bytes + 1,
        },
    )
    intent = await client.post(
        f"{base_path}/upload-url",
        headers=auth(seeded.admin_id),
        json=upload_payload,
    )
    finalized = await client.post(
        f"{base_path}/finalize",
        headers=auth(seeded.admin_id),
        json={
            **upload_payload,
            "storage_key": intent.json()["storage_key"],
            "title": "Аудиолекция",
            "position": 0,
        },
    )

    assert wrong_hierarchy.status_code == 404
    assert larger_than_interview_limit.status_code == 200
    assert too_large_video.status_code == 413
    assert too_large_video.json()["detail"]["code"] == "content_media_too_large"
    assert intent.status_code == 200, intent.text
    assert finalized.status_code == 201, finalized.text
    media_id = finalized.json()["id"]
    assert finalized.json()["kind"] == "audio"

    topic = await client.get(
        f"/api/v1/topics/{topic_id}",
        headers=auth(seeded.student_id),
    )
    wrong_direction = await client.get(
        f"/api/v1/topics/{topic_id}/media/{media_id}/playback",
        headers=auth(seeded.other_mentor_id),
    )
    playback = await client.get(
        f"/api/v1/topics/{topic_id}/media/{media_id}/playback",
        headers=auth(seeded.student_id),
    )
    stream = await client.get(
        playback.json()["url"],
        headers={"Sec-Fetch-Dest": "audio"},
    )

    assert topic.status_code == 200, topic.text
    assert topic.json()["media"] == [finalized.json()]
    assert wrong_direction.status_code == 404
    assert playback.status_code == 200, playback.text
    assert stream.status_code == 200
    assert stream.content == b"media"
    assert stream.headers["content-type"].startswith("audio/mpeg")

    deleted = await client.delete(
        f"{base_path}/{media_id}",
        headers=auth(seeded.admin_id),
    )
    assert deleted.status_code == 204
    assert fake_store.deleted == [intent.json()["storage_key"].removeprefix("pending/")]
