from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy import delete
from starlette.requests import Request

from app.auth.desktop import desktop_scope
from app.mentors.models import MentorDocumentKind, MentorStudentDocument
from app.users.models import User, UserRole
from tests.conftest import SeededData, TestSession, auth


async def test_preparation_only_reads_own_sources_and_versions_change(
    client: AsyncClient, seeded: SeededData
):
    other_id, own_doc, other_doc = uuid4(), uuid4(), uuid4()
    async with TestSession() as session:
        session.add(User(id=other_id, first_name="Other", role=UserRole.STUDENT))
        await session.flush()
        session.add_all(
            [
                MentorStudentDocument(
                    id=own_doc,
                    student_id=seeded.student_id,
                    mentor_id=seeded.mentor_id,
                    kind=MentorDocumentKind.RESUME,
                    text_content="Я разработал сервис.",
                ),
                MentorStudentDocument(
                    id=other_doc,
                    student_id=other_id,
                    mentor_id=seeded.mentor_id,
                    kind=MentorDocumentKind.RESUME,
                    text_content="PRIVATE OTHER STUDENT",
                ),
            ]
        )
        await session.commit()
    base = "/api/v1/copilot/preparation"
    headers = auth(seeded.student_id)
    listing = await client.get(base + "/options", headers=headers)
    assert listing.status_code == 200
    assert {item["id"] for item in listing.json()["sources"]} == {str(own_doc)}
    assert "PRIVATE" not in listing.text
    path = base + f"/sources/document/{own_doc}"
    first = await client.get(path, headers=headers)
    assert first.status_code == 200 and first.json()["mentor_review"] == "not_reviewed"
    assert "no-store" in first.headers["cache-control"]
    assert (
        await client.get(base + f"/sources/document/{other_doc}", headers=headers)
    ).status_code == 404
    assert (
        await client.get(base + f"/sources/profile/{other_id}", headers=headers)
    ).status_code == 404
    async with TestSession() as session:
        doc = await session.get(MentorStudentDocument, own_doc)
        doc.text_content = "Я разработал другой сервис."
        await session.commit()
    second = await client.get(path, headers=headers)
    assert second.json()["version"] != first.json()["version"]
    async with TestSession() as session:
        await session.execute(
            delete(MentorStudentDocument).where(MentorStudentDocument.id == own_doc)
        )
        await session.commit()
    assert (await client.get(path, headers=headers)).status_code == 404
    assert (await client.get(base + "/options")).status_code == 401
    assert (await client.get(base + "/options", headers=auth(seeded.mentor_id))).status_code == 403


def test_desktop_scope_adds_only_read_only_preparation():
    def permitted(method, path):
        return desktop_scope(
            Request({"type": "http", "method": method, "path": path, "headers": []})
        )

    valid = "/api/v1/copilot/preparation/sources/document/" + str(uuid4())
    assert permitted("GET", valid)
    assert permitted("GET", "/api/v1/copilot/preparation/options")
    assert not permitted("DELETE", valid)
    assert not permitted("GET", "/api/v1/copilot/releases")
    assert not permitted("GET", "/api/v1/copilot/preparation/sources/document/../../me")


async def test_disabled_career_packages_are_not_available_through_copilot(
    client: AsyncClient, seeded: SeededData, monkeypatch
):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "career_package_enabled", False)
    for kind in ["resume", "conditions"]:
        result = await client.get(
            f"/api/v1/copilot/preparation/sources/{kind}/{uuid4()}", headers=auth(seeded.student_id)
        )
        assert result.status_code == 404
        assert "career_package_disabled" in result.text
