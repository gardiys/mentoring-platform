from httpx import AsyncClient

from tests.conftest import SeededData, auth


def knowledge_payload(
    *, slug: str = "backend-practice", is_published: bool = True
) -> dict[str, object]:
    return {
        "slug": slug,
        "title": "Backend-практика",
        "description": "Статьи и вопросы для подготовки",
        "position": 0,
        "is_published": is_published,
        "entries": [
            {
                "kind": "article",
                "slug": f"{slug}-postgres-search",
                "title": "Полнотекстовый поиск PostgreSQL",
                "summary": "Как устроены tsvector и GIN-индексы",
                "content_markdown": (
                    "# Поиск\n\nПолнотекстовый поиск использует **tsvector** и быстрый GIN-индекс."
                ),
                "position": 0,
                "is_published": True,
            },
            {
                "kind": "question",
                "slug": f"{slug}-async-question",
                "title": "Как работает event loop?",
                "summary": "Вопрос для собеседования",
                "content_markdown": (
                    "# Ответ\n\nАсинхронность позволяет конкурентно ожидать операции ввода-вывода."
                ),
                "position": 1,
                "is_published": True,
            },
            {
                "kind": "article",
                "slug": f"{slug}-draft",
                "title": "Черновик",
                "summary": None,
                "content_markdown": "Скрытый материал про транзакции.",
                "position": 2,
                "is_published": False,
            },
        ],
    }


async def create_topic(client: AsyncClient, seeded: SeededData, **changes: object):
    payload = knowledge_payload()
    payload.update(changes)
    return await client.post(
        "/api/v1/admin/knowledge/topics",
        headers=auth(seeded.admin_id),
        json=payload,
    )


async def test_only_admin_can_manage_knowledge_base(
    client: AsyncClient, seeded: SeededData
) -> None:
    student = await client.get("/api/v1/admin/knowledge/topics", headers=auth(seeded.student_id))
    mentor = await client.get("/api/v1/admin/knowledge/topics", headers=auth(seeded.mentor_id))
    admin = await client.get("/api/v1/admin/knowledge/topics", headers=auth(seeded.admin_id))

    assert student.status_code == mentor.status_code == 403
    assert admin.status_code == 200


async def test_public_knowledge_shows_published_topics_articles_and_questions(
    client: AsyncClient, seeded: SeededData
) -> None:
    created = await create_topic(client, seeded)
    topics = await client.get("/api/v1/knowledge/topics", headers=auth(seeded.student_id))
    detail = await client.get(
        "/api/v1/knowledge/topics/backend-practice",
        headers=auth(seeded.student_id),
    )
    entry = await client.get(
        "/api/v1/knowledge/entries/backend-practice-postgres-search",
        headers=auth(seeded.student_id),
    )

    assert created.status_code == 201
    assert topics.json()[0]["article_count"] == 1
    assert topics.json()[0]["question_count"] == 1
    assert [item["kind"] for item in detail.json()["entries"]] == [
        "article",
        "question",
    ]
    assert "tsvector" in entry.json()["content_markdown"]
    assert entry.json()["topic"]["slug"] == "backend-practice"


async def test_full_text_search_uses_article_content_and_ignores_drafts(
    client: AsyncClient, seeded: SeededData
) -> None:
    await create_topic(client, seeded)

    by_content = await client.get(
        "/api/v1/knowledge/search",
        params={"q": "полнотекстовый GIN"},
        headers=auth(seeded.student_id),
    )
    by_question = await client.get(
        "/api/v1/knowledge/search",
        params={"q": "асинхронность"},
        headers=auth(seeded.student_id),
    )
    hidden = await client.get(
        "/api/v1/knowledge/search",
        params={"q": "транзакции"},
        headers=auth(seeded.student_id),
    )

    assert by_content.status_code == 200
    assert [item["slug"] for item in by_content.json()] == ["backend-practice-postgres-search"]
    assert by_question.json()[0]["kind"] == "question"
    assert hidden.json() == []


async def test_admin_updates_content_and_can_remove_entry(
    client: AsyncClient, seeded: SeededData
) -> None:
    created = await create_topic(client, seeded)
    payload = created.json()
    topic_id = payload.pop("id")
    removed_slug = payload["entries"][1]["slug"]
    payload["entries"] = payload["entries"][:1]
    payload["entries"][0]["content_markdown"] += "\n\nКонкурентность и ранжирование."

    updated = await client.put(
        f"/api/v1/admin/knowledge/topics/{topic_id}",
        headers=auth(seeded.admin_id),
        json=payload,
    )
    search = await client.get(
        "/api/v1/knowledge/search",
        params={"q": "конкурентность"},
        headers=auth(seeded.student_id),
    )
    removed = await client.get(
        f"/api/v1/knowledge/entries/{removed_slug}",
        headers=auth(seeded.student_id),
    )

    assert updated.status_code == 200
    assert len(updated.json()["entries"]) == 1
    assert search.json()[0]["slug"] == "backend-practice-postgres-search"
    assert removed.status_code == 404
