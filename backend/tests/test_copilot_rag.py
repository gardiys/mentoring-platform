import hashlib
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import delete
from starlette.requests import Request

from app.auth.desktop import desktop_scope
from app.interviews.card_automation_models import AutomationDecision
from app.interviews.card_automation_types import (
    AutomationDecisionSource,
    AutomationDecisionType,
    AutomationReviewResult,
)
from app.interviews.models import InterviewCard, InterviewCardFrequency, InterviewDeck
from app.knowledge.models import KnowledgeEntry
from app.tracks.models import LearningTrackEnrollment
from app.users.models import User, UserRole
from tests.conftest import TestSession, auth
from tests.test_knowledge import create_topic

BASE = "/api/v1/copilot/rag"


async def test_manifest_and_direct_source_respect_track_publication_and_revocation(client, seeded):
    created = await create_topic(client, seeded)
    assert created.status_code == 201
    headers = auth(seeded.student_id)
    first = await client.get(BASE + "/manifest?track=python", headers=headers)
    assert first.status_code == 200
    items = first.json()["items"]
    assert len(items) == 2 and "content" not in first.text
    assert first.json()["complete"] is True
    assert not (await client.get(BASE + "/manifest?track=go", headers=headers)).json()["items"]
    key = items[0]["key"]
    source_path = BASE + "/sources/" + key.replace(":", "/") + "?track=python"
    source = await client.get(source_path, headers=headers)
    assert source.status_code == 200 and source.json()["version"] == items[0]["version"]
    async with TestSession() as db:
        entry = await db.get(KnowledgeEntry, key.split(":")[1])
        entry.content_markdown = "Обновлённый исходный текст"
        await db.commit()
    updated = await client.get(source_path, headers=headers)
    assert updated.json()["version"] != source.json()["version"]
    async with TestSession() as db:
        await db.execute(
            delete(LearningTrackEnrollment).where(
                LearningTrackEnrollment.user_id == seeded.student_id
            )
        )
        await db.commit()
    assert (await client.get(source_path, headers=headers)).status_code == 404
    assert not (await client.get(BASE + "/manifest?track=python", headers=headers)).json()["items"]
    assert (
        await client.get(BASE + "/manifest?track=python", headers=auth(seeded.mentor_id))
    ).status_code == 403


async def test_only_human_review_for_exact_card_version_qualifies(client, seeded):
    deck_id, card_id = uuid4(), uuid4()
    question, answer = "Что такое Python GIL?", "GIL ограничивает исполнение байткода потоками."
    async with TestSession() as db:
        db.add(
            InterviewDeck(
                id=deck_id,
                track_id=seeded.python_track_id,
                slug="copilot-test",
                title="Python",
                is_published=True,
            )
        )
        await db.flush()
        db.add(
            InterviewCard(
                id=card_id,
                deck_id=deck_id,
                slug="gil",
                category="Python",
                question_markdown=question,
                answer_markdown=answer,
                frequency=InterviewCardFrequency.FREQUENT,
                is_published=True,
            )
        )
        await db.commit()
    path = f"{BASE}/sources/card/{card_id}?track=python"
    headers = auth(seeded.student_id)
    assert (await client.get(path, headers=headers)).json()["review_status"] == "published"
    decision_id = uuid4()
    async with TestSession() as db:
        db.add(
            AutomationDecision(
                id=decision_id,
                entity_type="cluster",
                entity_id=uuid4(),
                idempotency_key="copilot-review",
                decision_type=AutomationDecisionType.CARD_CREATED,
                decision_source=AutomationDecisionSource.HUMAN,
                selected_card_id=card_id,
                reviewed_at=datetime.now(UTC),
                reviewed_by_user_id=seeded.admin_id,
                review_result=AutomationReviewResult.CORRECT,
                reason="Checked",
                retrieval_scores={
                    "question_sha256": hashlib.sha256(question.encode()).hexdigest(),
                    "answer_sha256": hashlib.sha256(answer.encode()).hexdigest(),
                },
            )
        )
        await db.commit()
    reviewed = (await client.get(path, headers=headers)).json()
    assert reviewed["review_status"] == "human_reviewed" and reviewed["cluster_id"]
    async with TestSession() as db:
        card = await db.get(InterviewCard, card_id)
        card.answer_markdown += " New content"
        await db.commit()
    changed = (await client.get(path, headers=headers)).json()
    assert changed["review_status"] == "published" and changed["version"] != reviewed["version"]
    async with TestSession() as db:
        card = await db.get(InterviewCard, card_id)
        card.is_published = False
        await db.commit()
    assert (await client.get(path, headers=headers)).status_code == 404


async def test_foreign_student_cannot_read_sources_without_enrollment(client, seeded):
    await create_topic(client, seeded)
    own = (
        await client.get(BASE + "/manifest?track=python", headers=auth(seeded.student_id))
    ).json()
    key = own["items"][0]["key"]
    other = uuid4()
    async with TestSession() as db:
        db.add(User(id=other, first_name="Other", role=UserRole.STUDENT))
        await db.commit()
    assert (
        await client.get(
            BASE + "/sources/" + key.replace(":", "/") + "?track=python", headers=auth(other)
        )
    ).status_code == 404
    assert (await client.get(BASE + "/manifest?track=python")).status_code == 401


def test_desktop_scope_only_adds_exact_read_only_material_endpoints():
    good = [
        BASE + "/manifest",
        BASE + "/sources/kb/" + str(uuid4()),
        BASE + "/sources/card/" + str(uuid4()),
        BASE + "/sources/resume/" + str(uuid4()),
    ]
    bad = [
        "/api/v1/copilot/releases",
        "/api/v1/admin/interviews/decks",
        BASE + "/sources/profile/" + str(uuid4()),
        BASE + "/sources/kb/../../me",
        BASE + "/manifest/extra",
        BASE + "/sources/card/not-a-uuid",
    ]
    for method in ["GET", "POST", "PATCH", "DELETE", "PUT"]:
        for path in good + bad:
            allowed = desktop_scope(
                Request({"type": "http", "method": method, "path": path, "headers": []})
            )
            assert allowed == (method == "GET" and path in good)


async def test_resume_requires_owner_delivery_track_and_enabled_module(client, seeded, monkeypatch):
    from app.career_packages.models import CareerPackage, CareerPackageVersion, CareerResumeVersion
    from app.core.config import get_settings
    from app.mentors.models import MentorDocumentKind, MentorStudentDocument

    monkeypatch.setattr(get_settings(), "career_package_enabled", True)
    ids = [uuid4() for _ in range(5)]
    other, doc_id, resume_id, package_id, version_id = ids
    async with TestSession() as db:
        db.add(User(id=other, first_name="Other", role=UserRole.STUDENT))
        db.add(
            MentorStudentDocument(
                id=doc_id,
                student_id=seeded.student_id,
                mentor_id=seeded.mentor_id,
                kind=MentorDocumentKind.RESUME,
                text_content="Private resume",
            )
        )
        await db.flush()
        db.add(
            CareerResumeVersion(
                id=resume_id,
                student_id=seeded.student_id,
                source_document_id=doc_id,
                version_number=1,
                text_content="Private resume",
                content_sha256="a" * 64,
            )
        )
        db.add(
            CareerPackage(
                id=package_id, student_id=seeded.student_id, track_id=seeded.python_track_id
            )
        )
        await db.flush()
        db.add(
            CareerPackageVersion(
                id=version_id,
                package_id=package_id,
                version_number=1,
                source_resume_version_id=resume_id,
                snapshot={"resume": {"text_content": "Private resume"}},
                rendered_html="",
                pdf_object_key="synthetic",
                pdf_size=0,
                pdf_sha256="b" * 64,
                snapshot_sha256="c" * 64,
                published_at=datetime.now(UTC),
                provided_at=None,
            )
        )
        await db.commit()
    path = f"{BASE}/sources/resume/{version_id}?track=python"
    headers = auth(seeded.student_id)
    assert (await client.get(path, headers=headers)).status_code == 404
    async with TestSession() as db:
        version = await db.get(CareerPackageVersion, version_id)
        version.provided_at = datetime.now(UTC)
        await db.commit()
    assert (await client.get(path, headers=headers)).json()["content"] == "Private resume"
    assert (await client.get(path, headers=auth(other))).status_code == 404
    assert not (await client.get(BASE + "/manifest?track=python", headers=headers)).json()["items"]
    assert (await client.get(BASE + "/manifest?track=python&resume=true", headers=headers)).json()[
        "items"
    ]
    monkeypatch.setattr(get_settings(), "career_package_enabled", False)
    assert (await client.get(path, headers=headers)).status_code == 404
