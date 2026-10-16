import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.auth import dependencies as auth_dependencies
from app.core.config import get_settings
from app.db.base import Base
from app.db.models import (
    LearningTrack,
    LearningTrackEnrollment,
    LearningTrackRoadmap,
    MentorStudent,
    MentorTrackAssignment,
    Roadmap,
    RoadmapEnrollment,
    RoadmapSection,
    Topic,
    User,
)
from app.db.session import get_db_session
from app.legal import service as legal_service
from app.main import app
from app.opportunities import python_repeat_service
from app.opportunities import service as opportunity_service
from app.payments import router as payment_router
from app.payments import service as payment_service
from app.users.models import UserRole

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://mentoring:mentoring@localhost:5432/mentoring_test",
)
if not TEST_DATABASE_URL.rstrip("/").split("/")[-1].split("?")[0].endswith("_test"):
    raise RuntimeError("TEST_DATABASE_URL must point to a database ending with '_test'")
test_engine = create_async_engine(
    TEST_DATABASE_URL,
    poolclass=NullPool,
    connect_args={
        "timeout": 10,
        "command_timeout": 35,
        "server_settings": {"lock_timeout": "5000", "statement_timeout": "30000"},
    },
)
TestSession = async_sessionmaker(test_engine, expire_on_commit=False)


@pytest.fixture(autouse=True)
def isolate_payment_provider_from_local_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests must never contact a real bank because a developer has a populated .env."""

    local_settings = get_settings().model_copy(
        update={
            "app_env": "development",
            "web_frontend_url": "http://test",
            "tochka_client_id": None,
            "tochka_jwt_token": None,
            "tochka_proxy_url": None,
            "tochka_public_key": None,
        }
    )
    monkeypatch.setattr(payment_service, "get_settings", lambda: local_settings)
    monkeypatch.setattr(legal_service, "get_settings", lambda: local_settings)
    monkeypatch.setattr(opportunity_service, "get_settings", lambda: local_settings)
    monkeypatch.setattr(python_repeat_service, "get_settings", lambda: local_settings)
    monkeypatch.setattr(payment_router, "settings", local_settings)


@dataclass(frozen=True)
class SeededData:
    student_id: UUID
    mentor_id: UUID
    other_mentor_id: UUID
    admin_id: UUID
    roadmap_id: UUID
    hidden_roadmap_id: UUID
    python_track_id: UUID
    go_track_id: UUID
    topic_ids: tuple[UUID, UUID]


async def recreate_database_schema() -> None:
    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)


@pytest.fixture(scope="session")
async def database_schema() -> AsyncIterator[None]:
    # Keep concurrent test runs from dropping/truncating each other's data.
    async with test_engine.connect() as lock_connection:
        await lock_connection.execute(text("SELECT pg_advisory_lock(714202610)"))
        await lock_connection.commit()
        try:
            await recreate_database_schema()
            yield
        finally:
            await lock_connection.execute(text("SELECT pg_advisory_unlock(714202610)"))
            await lock_connection.commit()
    await test_engine.dispose()


@pytest.fixture(autouse=True)
async def reset_database(
    database_schema: None, request: pytest.FixtureRequest
) -> AsyncIterator[None]:
    async with test_engine.begin() as connection:
        tables = ", ".join(
            connection.dialect.identifier_preparer.format_table(table)
            for table in Base.metadata.tables.values()
        )
        await connection.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))
    try:
        yield
    finally:
        # Migration tests may recreate tables without later model columns.
        if request.node.get_closest_marker("schema_change") is not None:
            await recreate_database_schema()


@pytest.fixture
async def seeded() -> SeededData:
    data = SeededData(
        student_id=uuid4(),
        mentor_id=uuid4(),
        other_mentor_id=uuid4(),
        admin_id=uuid4(),
        roadmap_id=uuid4(),
        hidden_roadmap_id=uuid4(),
        python_track_id=uuid4(),
        go_track_id=uuid4(),
        topic_ids=(uuid4(), uuid4()),
    )
    async with TestSession() as session:
        session.add_all(
            [
                User(id=data.student_id, first_name="Иван", role=UserRole.STUDENT),
                User(id=data.mentor_id, first_name="Антон", role=UserRole.MENTOR),
                User(id=data.other_mentor_id, first_name="Другой", role=UserRole.MENTOR),
                User(id=data.admin_id, first_name="Администратор", role=UserRole.ADMIN),
            ]
        )
        await session.flush()
        session.add(MentorStudent(mentor_id=data.mentor_id, student_id=data.student_id))
        session.add_all(
            [
                LearningTrack(
                    id=data.python_track_id,
                    slug="python",
                    title="Python",
                    position=0,
                    is_published=True,
                ),
                LearningTrack(
                    id=data.go_track_id,
                    slug="go",
                    title="Go",
                    position=1,
                    is_published=True,
                ),
            ]
        )
        published = Roadmap(
            id=data.roadmap_id,
            slug="python-backend",
            title="Python Backend",
            position=0,
            is_published=True,
        )
        hidden = Roadmap(
            id=data.hidden_roadmap_id,
            slug="hidden",
            title="Hidden",
            position=1,
            is_published=False,
        )
        session.add_all([published, hidden])
        await session.flush()
        section = RoadmapSection(
            roadmap_id=data.roadmap_id,
            title="Python",
            position=0,
            duration_days=2,
        )
        session.add(section)
        await session.flush()
        session.add_all(
            [
                Topic(
                    id=data.topic_ids[0],
                    section_id=section.id,
                    slug="types",
                    title="Типы",
                    content_markdown="# Типы",
                    position=0,
                    is_published=True,
                ),
                Topic(
                    id=data.topic_ids[1],
                    section_id=section.id,
                    slug="functions",
                    title="Функции",
                    content_markdown="# Функции",
                    position=1,
                    is_published=True,
                ),
            ]
        )
        session.add(RoadmapEnrollment(user_id=data.student_id, roadmap_id=data.roadmap_id))
        session.add_all(
            [
                LearningTrackRoadmap(
                    track_id=data.python_track_id,
                    roadmap_id=data.roadmap_id,
                    position=0,
                ),
                LearningTrackEnrollment(
                    user_id=data.student_id,
                    track_id=data.python_track_id,
                ),
                MentorTrackAssignment(
                    mentor_id=data.mentor_id,
                    track_id=data.python_track_id,
                ),
                MentorTrackAssignment(
                    mentor_id=data.other_mentor_id,
                    track_id=data.go_track_id,
                ),
            ]
        )
        await session.commit()
    return data


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async def override_session() -> AsyncIterator[AsyncSession]:
        async with TestSession() as session:
            yield session

    previous_dev_auth = auth_dependencies.settings.dev_auth_enabled
    auth_dependencies.settings.dev_auth_enabled = True
    app.dependency_overrides[get_db_session] = override_session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as async_client:
            yield async_client
    finally:
        auth_dependencies.settings.dev_auth_enabled = previous_dev_auth
        app.dependency_overrides.clear()


def auth(user_id: UUID) -> dict[str, str]:
    return {"X-Dev-User-Id": str(user_id)}
