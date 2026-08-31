import asyncio
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, func, select

from app.db.models import (
    ConsultationMentorSetting,
    InterviewCard,
    InterviewCardFrequency,
    InterviewDeck,
    KnowledgeEntry,
    KnowledgeEntryKind,
    KnowledgeTopic,
    LearningTrack,
    LearningTrackEnrollment,
    LearningTrackRoadmap,
    MentorStudent,
    MentorTrackAssignment,
    ProgramCompletion,
    Roadmap,
    RoadmapEnrollment,
    RoadmapSection,
    StudentLearningStatus,
    StudentMentorshipState,
    Topic,
    User,
)
from app.db.session import async_session_factory
from app.users.models import UserRole

MENTOR_ID = UUID("10000000-0000-4000-8000-000000000001")
STUDENT_ID = UUID("20000000-0000-4000-8000-000000000001")
ALUMNI_ID = UUID("20000000-0000-4000-8000-000000000002")
ADMIN_ID = UUID("90000000-0000-4000-8000-000000000001")
ROADMAP_ID = UUID("30000000-0000-4000-8000-000000000001")
PYTHON_TRACK_ID = UUID("40000000-0000-4000-8000-000000000001")
GO_TRACK_ID = UUID("40000000-0000-4000-8000-000000000002")
KNOWLEDGE_BACKEND_ID = UUID("50000000-0000-4000-8000-000000000001")
KNOWLEDGE_INTERVIEW_ID = UUID("50000000-0000-4000-8000-000000000002")
KNOWLEDGE_ENTRY_HTTP_ID = UUID("51000000-0000-4000-8000-000000000001")
KNOWLEDGE_ENTRY_ASYNC_ID = UUID("51000000-0000-4000-8000-000000000002")
KNOWLEDGE_ENTRY_INTERVIEW_ID = UUID("51000000-0000-4000-8000-000000000003")
PYTHON_INTERVIEW_DECK_ID = UUID("60000000-0000-4000-8000-000000000001")
GO_INTERVIEW_DECK_ID = UUID("60000000-0000-4000-8000-000000000002")
PYTHON_GIL_CARD_ID = UUID("61000000-0000-4000-8000-000000000001")
PYTHON_EVENT_LOOP_CARD_ID = UUID("61000000-0000-4000-8000-000000000002")
GO_GOROUTINE_CARD_ID = UUID("61000000-0000-4000-8000-000000000003")
GO_INTERFACE_CARD_ID = UUID("61000000-0000-4000-8000-000000000004")

TOPICS = (
    ("Основы Python", "python-basics", ("Типы данных", "Функции", "Исключения")),
    ("Backend", "backend", ("HTTP", "FastAPI", "PostgreSQL")),
)


async def seed() -> None:
    async with async_session_factory() as session:
        mentor = await session.get(User, MENTOR_ID)
        if mentor is None:
            mentor = User(
                id=MENTOR_ID,
                first_name="Антон",
                email="mentor@example.com",
                role=UserRole.MENTOR,
            )
            session.add(mentor)
        mentor.onboarding_completed_at = mentor.onboarding_completed_at or datetime.now(UTC)
        student = await session.get(User, STUDENT_ID)
        if student is None:
            student = User(
                id=STUDENT_ID,
                first_name="Иван",
                email="student@example.com",
                role=UserRole.STUDENT,
            )
            session.add(student)
        student.onboarding_completed_at = student.onboarding_completed_at or datetime.now(UTC)
        student.learning_start_date = student.learning_start_date or datetime.now(UTC).date()
        alumni = await session.get(User, ALUMNI_ID)
        if alumni is None:
            alumni = User(
                id=ALUMNI_ID,
                first_name="Пётр",
                last_name="Выпускник",
                email="alumni@example.com",
                role=UserRole.STUDENT,
            )
            session.add(alumni)
        alumni.is_active = True
        alumni.onboarding_completed_at = alumni.onboarding_completed_at or datetime.now(UTC)
        alumni.learning_start_date = alumni.learning_start_date or datetime.now(UTC).date()
        admin = await session.get(User, ADMIN_ID)
        if admin is None:
            admin = User(
                id=ADMIN_ID,
                first_name="Администратор",
                email="admin@example.com",
                role=UserRole.ADMIN,
            )
            session.add(admin)
        admin.onboarding_completed_at = admin.onboarding_completed_at or datetime.now(UTC)
        await session.flush()

        relation = await session.get(MentorStudent, (MENTOR_ID, STUDENT_ID))
        if relation is None:
            session.add(MentorStudent(mentor_id=MENTOR_ID, student_id=STUDENT_ID))

        roadmap = await session.get(Roadmap, ROADMAP_ID)
        if roadmap is None:
            roadmap = Roadmap(
                id=ROADMAP_ID,
                slug="python-backend",
                title="Python Backend Developer",
                description="Практический роадмап для подготовки Python Backend разработчика.",
                position=0,
                is_published=True,
            )
            session.add(roadmap)
            await session.flush()

        existing_sections = list(
            await session.scalars(
                select(RoadmapSection).where(RoadmapSection.roadmap_id == ROADMAP_ID)
            )
        )
        if not existing_sections:
            for section_position, (section_title, section_slug, topic_titles) in enumerate(TOPICS):
                section = RoadmapSection(
                    roadmap_id=ROADMAP_ID,
                    title=section_title,
                    description=f"Материалы раздела «{section_title}».",
                    position=section_position,
                )
                session.add(section)
                await session.flush()
                for topic_position, topic_title in enumerate(topic_titles):
                    slug = f"{section_slug}-{topic_position + 1}"
                    session.add(
                        Topic(
                            section_id=section.id,
                            slug=slug,
                            title=topic_title,
                            description=f"Краткое введение в тему «{topic_title}».",
                            content_markdown=(
                                f"# {topic_title}\n\n"
                                f"Это базовый материал по теме **{topic_title}**.\n\n"
                                "## Что запомнить\n\n"
                                "- изучите основные понятия;\n"
                                "- попробуйте небольшой пример;\n"
                                "- сформулируйте вопросы ментору.\n\n"
                                '```python\nprint("Практика важнее чтения")\n```'
                            ),
                            position=topic_position,
                            estimated_minutes=15,
                            is_published=True,
                        )
                    )

        enrollment = await session.get(RoadmapEnrollment, (STUDENT_ID, ROADMAP_ID))
        if enrollment is None:
            session.add(
                RoadmapEnrollment(
                    user_id=STUDENT_ID,
                    roadmap_id=ROADMAP_ID,
                )
            )

        python_track = await session.get(LearningTrack, PYTHON_TRACK_ID)
        if python_track is None:
            python_track = LearningTrack(
                id=PYTHON_TRACK_ID,
                slug="python",
                title="Python",
                description="Трек Python Backend",
                position=0,
                is_published=True,
            )
            session.add(python_track)
        go_track = await session.get(LearningTrack, GO_TRACK_ID)
        if go_track is None:
            session.add(
                LearningTrack(
                    id=GO_TRACK_ID,
                    slug="go",
                    title="Go",
                    description="Трек Go Backend",
                    position=1,
                    is_published=True,
                )
            )
        await session.flush()
        if await session.get(LearningTrackRoadmap, (PYTHON_TRACK_ID, ROADMAP_ID)) is None:
            session.add(
                LearningTrackRoadmap(
                    track_id=PYTHON_TRACK_ID,
                    roadmap_id=ROADMAP_ID,
                    position=0,
                )
            )
        if await session.get(MentorTrackAssignment, (MENTOR_ID, PYTHON_TRACK_ID)) is None:
            session.add(
                MentorTrackAssignment(
                    mentor_id=MENTOR_ID,
                    track_id=PYTHON_TRACK_ID,
                )
            )
        consultant_setting = await session.get(ConsultationMentorSetting, MENTOR_ID)
        if consultant_setting is None:
            session.add(
                ConsultationMentorSetting(
                    mentor_id=MENTOR_ID,
                    is_enabled=True,
                    updated_by_user_id=ADMIN_ID,
                )
            )
        if await session.get(LearningTrackEnrollment, (STUDENT_ID, PYTHON_TRACK_ID)) is None:
            session.add(LearningTrackEnrollment(user_id=STUDENT_ID, track_id=PYTHON_TRACK_ID))
        if await session.get(LearningTrackEnrollment, (ALUMNI_ID, PYTHON_TRACK_ID)) is None:
            session.add(LearningTrackEnrollment(user_id=ALUMNI_ID, track_id=PYTHON_TRACK_ID))
        if await session.get(ProgramCompletion, (ALUMNI_ID, PYTHON_TRACK_ID)) is None:
            session.add(
                ProgramCompletion(
                    user_id=ALUMNI_ID,
                    track_id=PYTHON_TRACK_ID,
                    completed_at=datetime.now(UTC),
                    recorded_by_user_id=ADMIN_ID,
                )
            )
        alumni_state = await session.get(StudentMentorshipState, ALUMNI_ID)
        if alumni_state is None:
            session.add(
                StudentMentorshipState(
                    student_id=ALUMNI_ID,
                    learning_status=StudentLearningStatus.FINISHED,
                    status_updated_at=datetime.now(UTC),
                )
            )
        else:
            alumni_state.learning_status = StudentLearningStatus.FINISHED

        backend_knowledge = await session.get(KnowledgeTopic, KNOWLEDGE_BACKEND_ID)
        if backend_knowledge is None:
            backend_knowledge = KnowledgeTopic(
                id=KNOWLEDGE_BACKEND_ID,
                slug="backend-foundations",
                title="Основы Backend",
                description="Базовые концепции, к которым мы возвращаемся на менторстве.",
                position=0,
                is_published=True,
            )
            session.add(backend_knowledge)
            await session.flush()
        if await session.get(KnowledgeEntry, KNOWLEDGE_ENTRY_HTTP_ID) is None:
            session.add(
                KnowledgeEntry(
                    id=KNOWLEDGE_ENTRY_HTTP_ID,
                    topic_id=backend_knowledge.id,
                    kind=KnowledgeEntryKind.ARTICLE,
                    slug="http-request-lifecycle",
                    title="Жизненный цикл HTTP-запроса",
                    summary="От TCP-соединения до ответа приложения.",
                    content_markdown=(
                        "# Жизненный цикл HTTP-запроса\n\n"
                        "Клиент устанавливает соединение, отправляет HTTP-запрос, а сервер "
                        "передаёт его приложению. Важно понимать границы ответственности "
                        "reverse proxy, ASGI-сервера и обработчика FastAPI.\n\n"
                        "## Что обсудить\n\n- keep-alive;\n- заголовки;\n"
                        "- коды ответа;\n- таймауты."
                    ),
                    position=0,
                    is_published=True,
                )
            )
        if await session.get(KnowledgeEntry, KNOWLEDGE_ENTRY_ASYNC_ID) is None:
            session.add(
                KnowledgeEntry(
                    id=KNOWLEDGE_ENTRY_ASYNC_ID,
                    topic_id=backend_knowledge.id,
                    kind=KnowledgeEntryKind.QUESTION,
                    slug="asyncio-event-loop-question",
                    title="Как работает event loop?",
                    summary="Вопрос про конкурентность и операции ввода-вывода.",
                    content_markdown=(
                        "# Краткий ответ\n\nEvent loop планирует корутины и переключается "
                        "между ними в точках ожидания `await`. Это даёт конкурентность без "
                        "создания отдельного потока на каждый запрос."
                    ),
                    position=1,
                    is_published=True,
                )
            )

        # This exact demo question used to live in the knowledge base. It now belongs
        # to the standalone interview module; user-created knowledge entries are untouched.
        await session.execute(
            delete(KnowledgeEntry).where(KnowledgeEntry.id == KNOWLEDGE_ENTRY_INTERVIEW_ID)
        )
        legacy_entries = await session.scalar(
            select(func.count(KnowledgeEntry.id)).where(
                KnowledgeEntry.topic_id == KNOWLEDGE_INTERVIEW_ID
            )
        )
        if not legacy_entries:
            legacy_topic = await session.get(KnowledgeTopic, KNOWLEDGE_INTERVIEW_ID)
            if legacy_topic is not None:
                await session.delete(legacy_topic)

        python_interviews = await session.get(InterviewDeck, PYTHON_INTERVIEW_DECK_ID)
        if python_interviews is None:
            python_interviews = InterviewDeck(
                id=PYTHON_INTERVIEW_DECK_ID,
                track_id=PYTHON_TRACK_ID,
                slug="python-interview",
                title="Python · вопросы с собеседований",
                description="Карточки по Python и устройству асинхронного backend.",
                position=0,
                is_published=True,
            )
            session.add(python_interviews)
            await session.flush()
        python_cards = (
            (
                PYTHON_GIL_CARD_ID,
                "python-gil",
                "## Что такое GIL и на что он влияет?",
                (
                    "**GIL** — блокировка интерпретатора CPython, которая позволяет только "
                    "одному потоку одновременно исполнять Python-байткод. Потоки всё ещё "
                    "полезны для I/O, а для CPU-bound задач обычно используют процессы, "
                    "нативные расширения или другой runtime."
                ),
                InterviewCardFrequency.FREQUENT,
            ),
            (
                PYTHON_EVENT_LOOP_CARD_ID,
                "python-event-loop",
                "## Как работает event loop в asyncio?",
                (
                    "Event loop запускает готовые корутины и переключается между ними в "
                    "точках `await`. Пока одна задача ждёт I/O, цикл может продолжить другую. "
                    "Это конкурентность, но не автоматический параллелизм Python-кода."
                ),
                InterviewCardFrequency.FREQUENT,
            ),
        )
        for position, (card_id, slug, question, answer, frequency) in enumerate(python_cards):
            if await session.get(InterviewCard, card_id) is None:
                session.add(
                    InterviewCard(
                        id=card_id,
                        deck_id=python_interviews.id,
                        slug=slug,
                        category="Конкурентность в Python",
                        question_markdown=question,
                        answer_markdown=answer,
                        frequency=frequency,
                        frequency_override=frequency,
                        position=position,
                        is_published=True,
                    )
                )

        go_interviews = await session.get(InterviewDeck, GO_INTERVIEW_DECK_ID)
        if go_interviews is None:
            go_interviews = InterviewDeck(
                id=GO_INTERVIEW_DECK_ID,
                track_id=GO_TRACK_ID,
                slug="go-interview",
                title="Go · вопросы с собеседований",
                description="Карточки по Go, конкурентности и типовой системе.",
                position=1,
                is_published=True,
            )
            session.add(go_interviews)
            await session.flush()
        go_cards = (
            (
                GO_GOROUTINE_CARD_ID,
                "go-goroutine",
                "## Чем goroutine отличается от системного потока?",
                (
                    "Goroutine — лёгкая конкурентная задача, которой управляет runtime Go. "
                    "Планировщик мультиплексирует множество goroutine на меньшее число "
                    "системных потоков, а их стек начинается небольшим и растёт по мере нужды."
                ),
                InterviewCardFrequency.FREQUENT,
            ),
            (
                GO_INTERFACE_CARD_ID,
                "go-interface",
                "## Как тип реализует interface в Go?",
                (
                    "Неявно: тип реализует interface, если его method set содержит все "
                    "методы интерфейса. Отдельное объявление `implements` не требуется, что "
                    "позволяет определять небольшие интерфейсы на стороне потребителя."
                ),
                InterviewCardFrequency.OCCASIONAL,
            ),
        )
        for position, (card_id, slug, question, answer, frequency) in enumerate(go_cards):
            if await session.get(InterviewCard, card_id) is None:
                session.add(
                    InterviewCard(
                        id=card_id,
                        deck_id=go_interviews.id,
                        slug=slug,
                        category="Основы Go",
                        question_markdown=question,
                        answer_markdown=answer,
                        frequency=frequency,
                        frequency_override=frequency,
                        position=position,
                        is_published=True,
                    )
                )
        await session.commit()
    print(f"Mentor UUID: {MENTOR_ID}")
    print(f"Student UUID: {STUDENT_ID}")
    print(f"Alumni UUID: {ALUMNI_ID}")
    print(f"Admin UUID: {ADMIN_ID}")


if __name__ == "__main__":
    asyncio.run(seed())
