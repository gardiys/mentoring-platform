import hashlib
import json
from pathlib import Path

import pytest
from httpx import AsyncClient
from pytest import MonkeyPatch

from app.core.config import get_settings
from tests.conftest import SeededData, auth


@pytest.fixture
def releases(tmp_path: Path, monkeypatch: MonkeyPatch):
    root = tmp_path / "releases"
    root.mkdir()
    data = b"synthetic installer bytes"
    asset = dict(
        id="win-x64",
        os="windows",
        arch="x64",
        version="0.1.0",
        filename="Copilot-0.1.0-win-x64.exe",
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        signed=False,
    )
    (root / asset["filename"]).write_bytes(data)
    (root / "manifest.json").write_text(json.dumps({"releases": [asset]}))
    monkeypatch.setattr(get_settings(), "copilot_releases_dir", root)
    return root, asset, data


async def test_students_mentors_and_anonymous_cannot_list_or_download(
    client: AsyncClient, seeded: SeededData, releases
):
    for path in ["/api/v1/copilot/releases", "/api/v1/copilot/releases/win-x64/download"]:
        assert (await client.get(path)).status_code == 401
        for user in [seeded.student_id, seeded.mentor_id]:
            response = await client.get(path, headers=auth(user))
            assert response.status_code == 403
            assert "synthetic installer" not in response.text
            assert "sha256" not in response.text


async def test_admin_downloads_actual_bytes_and_range(
    client: AsyncClient, seeded: SeededData, releases
):
    _, asset, data = releases
    headers = auth(seeded.admin_id)
    listing = await client.get("/api/v1/copilot/releases", headers=headers)
    assert listing.status_code == 200
    assert listing.json()["releases"] == [asset]
    assert "no-store" in listing.headers["cache-control"]
    path = "/api/v1/copilot/releases/win-x64/download"
    response = await client.get(path, headers=headers)
    assert response.status_code == 200 and response.content == data
    assert asset["filename"] in response.headers["content-disposition"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "no-store" in response.headers["cache-control"]
    part = await client.get(path, headers={**headers, "Range": "bytes=0-8"})
    assert part.status_code == 206 and part.content == data[:9]


async def test_missing_build_has_no_dead_download_link(
    client: AsyncClient, seeded: SeededData, releases
):
    root, asset, _ = releases
    (root / asset["filename"]).unlink()
    headers = auth(seeded.admin_id)
    assert (await client.get("/api/v1/copilot/releases", headers=headers)).json() == {
        "releases": []
    }
    assert (
        await client.get("/api/v1/copilot/releases/win-x64/download", headers=headers)
    ).status_code == 404
    (root / "manifest.json").unlink()
    assert (await client.get("/api/v1/copilot/releases", headers=headers)).json() == {
        "releases": []
    }


async def test_release_storage_cannot_serve_outside_files(
    client: AsyncClient, seeded: SeededData, releases
):
    root, asset, data = releases
    outside = root.parent / "private.exe"
    outside.write_bytes(data)
    target = root / asset["filename"]
    target.unlink()
    target.symlink_to(outside)
    headers = auth(seeded.admin_id)
    assert (await client.get("/api/v1/copilot/releases", headers=headers)).json() == {
        "releases": []
    }
    assert (
        await client.get("/api/v1/copilot/releases/win-x64/download", headers=headers)
    ).status_code == 404
    asset["filename"] = "../private.exe"
    (root / "manifest.json").write_text(json.dumps({"releases": [asset]}))
    assert (await client.get("/api/v1/copilot/releases", headers=headers)).status_code == 503
