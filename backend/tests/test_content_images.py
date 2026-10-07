from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from pytest import MonkeyPatch

from app.media import router as media_router
from tests.conftest import SeededData, auth
from tests.test_content_media import FakePrivateMediaStore, create_knowledge_entry


@pytest.mark.parametrize("scope", ["knowledge", "roadmap"])
@pytest.mark.parametrize(
    "content_type", ["image/png", "image/jpeg", "image/webp", "image/gif", "image/avif"]
)
async def test_image_upload_and_access_follow_content_permissions(
    client: AsyncClient,
    seeded: SeededData,
    monkeypatch: MonkeyPatch,
    scope: str,
    content_type: str,
) -> None:
    store = FakePrivateMediaStore()
    enqueue = AsyncMock()
    monkeypatch.setattr(media_router, "store", store)
    monkeypatch.setattr(media_router, "enqueue_content_media_normalization", enqueue)
    if scope == "knowledge":
        topic_id, entry_id, slug = await create_knowledge_entry(client, seeded)
        base = f"/api/v1/admin/knowledge/topics/{topic_id}/entries/{entry_id}/media"
        public = f"/api/v1/knowledge/entries/{slug}/media"
    else:
        roadmap = await client.get(
            f"/api/v1/admin/roadmaps/{seeded.roadmap_id}",
            headers=auth(seeded.admin_id),
        )
        section_id = roadmap.json()["sections"][0]["id"]
        topic_id = str(seeded.topic_ids[0])
        base = (
            f"/api/v1/admin/roadmaps/{seeded.roadmap_id}"
            f"/sections/{section_id}/topics/{topic_id}/media"
        )
        public = f"/api/v1/topics/{topic_id}/media"
    payload = {"filename": "diagram.png", "content_type": content_type, "size": 1024}
    denied_upload = await client.post(
        f"{base}/upload-url", headers=auth(seeded.student_id), json=payload
    )
    assert denied_upload.status_code == 403
    intent = await client.post(f"{base}/upload-url", headers=auth(seeded.admin_id), json=payload)
    assert intent.status_code == 200, intent.text
    uploaded = await client.post(
        f"{base}/finalize",
        headers=auth(seeded.admin_id),
        json={**payload, "storage_key": intent.json()["storage_key"]},
    )
    assert uploaded.status_code == 201, uploaded.text
    assert uploaded.json()["kind"] == "image"
    assert uploaded.json()["processing_status"] == "ready"
    assert uploaded.json()["playback_available"] is True
    enqueue.assert_not_awaited()
    media_id = uploaded.json()["id"]
    missing_ticket = await client.get(
        f"{public}/{media_id}/stream", headers={"Sec-Fetch-Dest": "image"}
    )
    assert missing_ticket.status_code == 401
    denied = await client.get(f"{public}/{media_id}/playback", headers=auth(seeded.other_mentor_id))
    assert denied.status_code == 404
    playback = await client.get(f"{public}/{media_id}/playback", headers=auth(seeded.student_id))
    assert playback.status_code == 200, playback.text
    viewed = await client.get(playback.json()["url"], headers={"Sec-Fetch-Dest": "image"})
    assert viewed.status_code == 307, viewed.text
    assert store.playback_urls[-1][0].content_type == content_type
    wrong_destination = await client.get(
        playback.json()["url"], headers={"Sec-Fetch-Dest": "video"}
    )
    assert wrong_destination.status_code == 403
    wrong_browser = await client.get(
        playback.json()["url"],
        headers={"Sec-Fetch-Dest": "image", "User-Agent": "another-browser"},
    )
    assert wrong_browser.status_code == 401


async def test_image_limits_and_svg_rejection(client: AsyncClient, seeded: SeededData) -> None:
    topic_id, entry_id, _slug = await create_knowledge_entry(client, seeded)
    path = f"/api/v1/admin/knowledge/topics/{topic_id}/entries/{entry_id}/media/upload-url"
    payload = {
        "filename": "large.png",
        "content_type": "image/png",
        "size": media_router.settings.content_image_max_bytes + 1,
    }
    oversized = await client.post(path, headers=auth(seeded.admin_id), json=payload)
    assert oversized.status_code == 413
    svg = await client.post(
        path,
        headers=auth(seeded.admin_id),
        json={**payload, "filename": "image.svg", "content_type": "image/svg+xml", "size": 1024},
    )
    assert svg.status_code == 415
