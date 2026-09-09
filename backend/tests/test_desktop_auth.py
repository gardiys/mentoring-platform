import re
from datetime import UTC, datetime, timedelta
from html import unescape

from httpx import AsyncClient
from pydantic import SecretStr
from pytest import MonkeyPatch
from sqlalchemy import select, update

from app.auth import dependencies, desktop_router
from app.auth.desktop import DesktopGrant
from app.auth.web_session import create_browser_session
from app.core.config import get_settings
from app.mentors.models import MentorStudent, StudentLearningStatus
from app.users.models import User
from tests.conftest import SeededData, TestSession

SECRET = "synthetic-desktop-session-secret-at-least-32-bytes"


async def configure(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "copilot_students_enabled", True)
    async with TestSession() as session:
        await session.execute(
            update(MentorStudent).values(learning_status=StudentLearningStatus.INTERVIEWING)
        )
        await session.commit()
    for cfg in (desktop_router.settings, dependencies.settings):
        monkeypatch.setattr(cfg, "desktop_auth_enabled", True)
        monkeypatch.setattr(cfg, "web_session_secret", SecretStr(SECRET))
        monkeypatch.setattr(cfg, "web_frontend_url", "http://localhost:5173")


async def approve(client, seeded, grant):
    client.cookies.set(
        "mentoring_session", create_browser_session(seeded.student_id, 1, SECRET, 3600)
    )
    page = await client.get(
        "/api/v1/auth/desktop/authorize", params={"request_id": grant["request_id"]}
    )
    assert page.status_code == 200
    assert grant["user_code"] in page.text
    csrf = unescape(re.search(r'name="csrf" value="([^"]+)"', page.text)[1])
    response = await client.post(
        "/api/v1/auth/desktop/authorize",
        data={"csrf": csrf, "decision": "approve"},
        headers={"Origin": "http://localhost:5173"},
    )
    assert response.status_code == 200
    client.cookies.clear()
    return csrf


async def test_desktop_login_scope_one_time_and_logout(
    client: AsyncClient, seeded: SeededData, monkeypatch: MonkeyPatch
):
    await configure(monkeypatch)
    grant = (await client.post("/api/v1/auth/desktop/start")).json()
    poll = {"request_id": grant["request_id"], "device_code": grant["device_code"]}
    pending = await client.post("/api/v1/auth/desktop/token", json=poll)
    assert pending.json()["status"] == "pending"
    again = await client.post("/api/v1/auth/desktop/token", json=poll)
    assert again.status_code == 429
    redirect = await client.get(
        "/api/v1/auth/desktop/authorize", params={"request_id": grant["request_id"]}
    )
    assert redirect.status_code == 302
    assert redirect.headers["location"].startswith("/api/v1/auth/web/telegram/start?")
    csrf = await approve(client, seeded, grant)
    wrong = await client.post("/api/v1/auth/desktop/token", json={**poll, "device_code": "x" * 40})
    assert wrong.json()["status"] == "expired"
    result = await client.post("/api/v1/auth/desktop/token", json=poll)
    assert result.headers["cache-control"] == "no-store"
    token = result.json()["access_token"]
    assert result.json()["status"] == "approved"
    assert (await client.post("/api/v1/auth/desktop/token", json=poll)).json()[
        "status"
    ] == "expired"
    headers = {"Authorization": "Bearer " + token}
    me = await client.get("/api/v1/me", headers=headers)
    assert me.status_code == 200 and me.json()["id"] == str(seeded.student_id)
    assert (await client.get("/api/v1/knowledge/topics", headers=headers)).status_code == 200
    denied = await client.get("/api/v1/roadmaps", headers=headers)
    assert denied.status_code == 403
    client.cookies.set(
        "mentoring_session", create_browser_session(seeded.student_id, 1, SECRET, 3600)
    )
    replay = await client.post(
        "/api/v1/auth/desktop/authorize",
        data={"csrf": csrf, "decision": "approve"},
        headers={"Origin": "http://localhost:5173"},
    )
    assert replay.status_code == 409
    client.cookies.clear()
    assert (await client.post("/api/v1/auth/desktop/logout", headers=headers)).status_code == 204
    assert (await client.get("/api/v1/me", headers=headers)).status_code == 401
    async with TestSession() as session:
        row = await session.scalar(select(DesktopGrant))
        assert row.token_hash is None
        assert grant["device_code"] != row.device_hash


async def test_desktop_denies_csrf_expiry_and_suspended_student(
    client: AsyncClient, seeded: SeededData, monkeypatch: MonkeyPatch
):
    await configure(monkeypatch)
    grant = (await client.post("/api/v1/auth/desktop/start")).json()
    client.cookies.set(
        "mentoring_session", create_browser_session(seeded.student_id, 1, SECRET, 3600)
    )
    assert (
        await client.post(
            "/api/v1/auth/desktop/authorize",
            data={"csrf": "forged", "decision": "approve"},
            headers={"Origin": "http://localhost:5173"},
        )
    ).status_code == 403
    assert (
        await client.post(
            "/api/v1/auth/desktop/authorize", data={}, headers={"Origin": "https://evil.example"}
        )
    ).status_code == 403
    client.cookies.clear()
    await approve(client, seeded, grant)
    async with TestSession() as session:
        user = await session.get(User, seeded.student_id)
        user.is_active = False
        await session.commit()
    assert (
        await client.post(
            "/api/v1/auth/desktop/token",
            json={"request_id": grant["request_id"], "device_code": grant["device_code"]},
        )
    ).json()["status"] == "denied"
    async with TestSession() as session:
        row = await session.scalar(select(DesktopGrant))
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
    assert (
        await client.post(
            "/api/v1/auth/desktop/token",
            json={"request_id": grant["request_id"], "device_code": grant["device_code"]},
        )
    ).json()["status"] == "expired"


async def test_desktop_token_respects_global_session_revocation(
    client: AsyncClient, seeded: SeededData, monkeypatch: MonkeyPatch
):
    await configure(monkeypatch)
    grant = (await client.post("/api/v1/auth/desktop/start")).json()
    await approve(client, seeded, grant)
    result = await client.post(
        "/api/v1/auth/desktop/token",
        json={"request_id": grant["request_id"], "device_code": grant["device_code"]},
    )
    headers = {"Authorization": "Bearer " + result.json()["access_token"]}
    async with TestSession() as session:
        user = await session.get(User, seeded.student_id)
        user.session_version += 1
        await session.commit()
    assert (await client.get("/api/v1/me", headers=headers)).status_code == 401
