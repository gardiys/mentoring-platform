import asyncio
import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import delete, func, literal, select

from app.interviews import recruiter_daily_service as daily
from app.interviews.models import (
    Company,
    InterviewProcess,
    RecruiterContact,
    RecruiterContactOpen,
    RecruiterContactProcess,
    RecruiterDailyAssignment,
    RecruiterDailyBatch,
    RecruiterFeedback,
    RecruiterFeedbackKind,
)
from app.mentors.models import MentorStudent, StudentLearningStatus, StudentMentorshipState
from app.tracks.models import LearningTrackEnrollment
from app.users.models import User, UserRole
from tests.conftest import TestSession, auth, test_engine

URL = "/api/v1/interviews/recruiters"


def ids(response):
    assert response.status_code == 200, response.text
    return [item["id"] for group in response.json()["items"] for item in group["recruiters"]]


@pytest.fixture
async def pool(seeded, monkeypatch):
    clock = [datetime(2026, 9, 21, 10, tzinfo=UTC)]
    monkeypatch.setattr(daily, "daily_now", lambda: clock[0])
    async with TestSession() as session:
        relation = await session.scalar(
            select(MentorStudent).where(MentorStudent.student_id == seeded.student_id)
        )
        relation.learning_status = StudentLearningStatus.INTERVIEWING
        companies = [
            Company(
                name=f"Компания {i:03d}",
                normalized_name=f"компания {i:03d}",
                transliterated_name=f"kompaniya {i:03d}",
            )
            for i in range(24)
        ]
        session.add_all(companies)
        await session.flush()
        processes = [
            InterviewProcess(
                user_id=seeded.student_id,
                track_id=seeded.python_track_id,
                company_id=c.id,
                company_name=c.name,
            )
            for c in companies
        ]
        session.add_all(processes)
        await session.flush()
        contacts = [
            RecruiterContact(
                telegram_username=f"recruiter_{i:03d}", normalized_username=f"recruiter_{i:03d}"
            )
            for i in range(24)
        ]
        session.add_all(contacts)
        await session.flush()
        session.add_all(
            [
                RecruiterContactProcess(recruiter_id=c.id, process_id=p.id)
                for c, p in zip(contacts, processes, strict=True)
            ]
        )
        await session.commit()
    return clock, [c.id for c in contacts], processes[0].id


async def another_student(seeded):
    uid = uuid4()
    async with TestSession() as session:
        session.add(User(id=uid, first_name="Другой", role=UserRole.STUDENT))
        await session.flush()
        session.add(
            StudentMentorshipState(
                student_id=uid, learning_status=StudentLearningStatus.INTERVIEWING
            )
        )
        session.add(LearningTrackEnrollment(user_id=uid, track_id=seeded.python_track_id))
        await session.commit()
    return uid


async def test_stable_daily_ten_concurrent_requests_and_next_day(client, seeded, pool):
    clock, _, _ = pool
    responses = await asyncio.gather(
        *[client.get(URL, headers=auth(seeded.student_id)) for _ in range(3)]
    )
    first = set(ids(responses[0]))
    assert len(first) == 10
    assert all(set(ids(r)) == first for r in responses)
    changed = await client.get(
        URL,
        headers=auth(seeded.student_id),
        params={"sort": "username", "limit": 100, "q": "recruiter"},
    )
    assert set(ids(changed)) == first
    opened = await client.post(
        f"{URL}/{next(iter(first))}/contact", headers=auth(seeded.student_id)
    )
    assert opened.status_code == 200
    same_day = await client.get(URL, headers=auth(seeded.student_id))
    assert set(ids(same_day)) == first
    assert same_day.json()["daily"]["contacted_count"] == 1
    clock[0] += timedelta(days=1)
    second = set(ids(await client.get(URL, headers=auth(seeded.student_id))))
    assert len(second) == 10 and not first & second
    clock[0] += timedelta(days=1)
    third = set(ids(await client.get(URL, headers=auth(seeded.student_id))))
    assert len(third) == 4 and not third & (first | second)
    clock[0] += timedelta(days=1)
    assert ids(await client.get(URL, headers=auth(seeded.student_id))) == []
    history = await client.get(URL, headers=auth(seeded.student_id), params={"view": "history"})
    assert set(ids(history)) == first | second | third
    feedback = await client.put(
        f"{URL}/{next(iter(first))}/feedback",
        headers=auth(seeded.student_id),
        json={"kind": "invited"},
    )
    assert feedback.status_code == 200
    async with TestSession() as session:
        assert await session.scalar(select(func.count()).select_from(RecruiterDailyBatch)) == 4
        assert (
            await session.scalar(select(func.count()).select_from(RecruiterDailyAssignment)) == 24
        )


async def test_weekends_and_moscow_midnight_preserve_history(client, seeded, pool):
    clock, _, _ = pool
    clock[0] = datetime(2026, 9, 25, 20, 59, tzinfo=UTC)  # Friday 23:59 Moscow.
    friday = await client.get(URL, headers=auth(seeded.student_id))
    friday_ids = set(ids(friday))
    assert len(friday_ids) == 10
    assert friday.json()["daily"]["next_batch_at"].startswith("2026-09-28")
    for now in (datetime(2026, 9, 25, 21, tzinfo=UTC), datetime(2026, 9, 27, 10, tzinfo=UTC)):
        clock[0] = now
        weekend = await client.get(URL, headers=auth(seeded.student_id))
        assert ids(weekend) == []
        assert not weekend.json()["daily"]["is_workday"]
        assert (
            set(
                ids(
                    await client.get(
                        URL, headers=auth(seeded.student_id), params={"view": "history"}
                    )
                )
            )
            == friday_ids
        )
    async with TestSession() as session:
        assert await session.scalar(select(func.count()).select_from(RecruiterDailyBatch)) == 1
    clock[0] = datetime(2026, 9, 27, 21, tzinfo=UTC)  # Monday midnight Moscow.
    monday = set(ids(await client.get(URL, headers=auth(seeded.student_id))))
    assert len(monday) == 10 and not monday & friday_ids


async def test_empty_batch_is_not_refilled_until_next_day(client, seeded, pool):
    clock, _, _ = pool
    async with TestSession() as session:
        links = (
            await session.execute(
                select(RecruiterContactProcess.recruiter_id, RecruiterContactProcess.process_id)
            )
        ).all()
        await session.execute(delete(RecruiterContactProcess))
        await session.commit()
    assert ids(await client.get(URL, headers=auth(seeded.student_id))) == []
    async with TestSession() as session:
        session.add_all(
            [
                RecruiterContactProcess(recruiter_id=contact, process_id=process)
                for contact, process in links
            ]
        )
        await session.commit()
    assert ids(await client.get(URL, headers=auth(seeded.student_id))) == []
    clock[0] += timedelta(days=1)
    assert len(ids(await client.get(URL, headers=auth(seeded.student_id)))) == 10


@pytest.mark.parametrize(
    "status",
    [
        StudentLearningStatus.LEARNING,
        StudentLearningStatus.PROBATION,
        StudentLearningStatus.FINISHED,
    ],
)
async def test_status_gates_only_daily_selection(client, seeded, pool, status):
    _, contacts, _ = pool
    async with TestSession() as session:
        session.add(StudentMentorshipState(student_id=seeded.student_id, learning_status=status))
        await session.commit()
    listing = await client.get(URL, headers=auth(seeded.student_id))
    assert ids(listing) == [] and not listing.json()["daily"]["eligible"]
    directory = await client.get(URL, headers=auth(seeded.student_id), params={"view": "all"})
    assert set(ids(directory)) == {str(c) for c in contacts}
    assert (
        await client.post(f"{URL}/{contacts[0]}/contact", headers=auth(seeded.student_id))
    ).status_code == 200
    assert (
        await client.put(
            f"{URL}/{contacts[0]}/feedback",
            headers=auth(seeded.student_id),
            json={"kind": "helpful"},
        )
    ).status_code == 200
    history = await client.get(URL, headers=auth(seeded.student_id), params={"view": "history"})
    assert ids(history) == [str(contacts[0])]
    assert (
        await client.delete(f"{URL}/{contacts[0]}/feedback", headers=auth(seeded.student_id))
    ).status_code == 204
    async with TestSession() as session:
        assert await session.scalar(select(func.count()).select_from(RecruiterDailyBatch)) == 0


async def test_contacts_outside_daily_selection_are_accessible_but_tracks_are_checked(
    client, seeded, pool
):
    _, contacts, _ = pool
    selected = set(ids(await client.get(URL, headers=auth(seeded.student_id))))
    unassigned = next(c for c in contacts if str(c) not in selected)
    assert (
        await client.post(f"{URL}/{unassigned}/contact", headers=auth(seeded.student_id))
    ).status_code == 200
    assert set(ids(await client.get(URL, headers=auth(seeded.student_id)))) == selected
    other_track = await client.get(
        URL, headers=auth(seeded.student_id), params={"track_id": str(seeded.go_track_id)}
    )
    assert ids(other_track) == []
    async with TestSession() as session:
        await session.execute(
            delete(LearningTrackEnrollment).where(
                LearningTrackEnrollment.user_id == seeded.student_id
            )
        )
        await session.commit()
    assert ids(await client.get(URL, headers=auth(seeded.student_id))) == []
    assert ids(await client.get(URL, headers=auth(seeded.student_id), params={"view": "all"})) == []
    assert (
        await client.post(f"{URL}/{next(iter(selected))}/contact", headers=auth(seeded.student_id))
    ).status_code == 404


async def test_full_directory_does_not_allocate_and_supports_search_and_weekends(
    client, seeded, pool
):
    clock, contacts, _ = pool
    for view in ("all", "history"):
        result = await client.get(URL, headers=auth(seeded.student_id), params={"view": view})
        assert len(ids(result)) == (24 if view == "all" else 0)
    async with TestSession() as session:
        assert await session.scalar(select(func.count()).select_from(RecruiterDailyBatch)) == 0
    matched = await client.get(
        URL, headers=auth(seeded.student_id), params={"view": "all", "q": "recruiter_023"}
    )
    assert ids(matched) == [str(contacts[23])]
    await client.post(f"{URL}/{contacts[23]}/contact", headers=auth(seeded.student_id))
    contacted = await client.get(
        URL, headers=auth(seeded.student_id), params={"view": "all", "contacted": "true"}
    )
    assert ids(contacted) == [str(contacts[23])]
    chosen = set(ids(await client.get(URL, headers=auth(seeded.student_id))))
    assert len(chosen) == 10 and str(contacts[23]) not in chosen
    clock[0] = datetime(2026, 9, 26, 10, tzinfo=UTC)
    assert ids(await client.get(URL, headers=auth(seeded.student_id))) == []
    assert (
        len(ids(await client.get(URL, headers=auth(seeded.student_id), params={"view": "all"})))
        == 24
    )
    async with TestSession() as session:
        assert await session.scalar(select(func.count()).select_from(RecruiterDailyBatch)) == 1


async def test_shared_contacts_are_allowed_but_exposure_spreads_allocations(
    client, seeded, pool, monkeypatch
):
    _, contacts, _ = pool
    monkeypatch.setattr(daily, "random_draw", lambda: literal(0.5))
    second_student = await another_student(seeded)
    first, second = await asyncio.gather(
        client.get(URL, headers=auth(seeded.student_id)),
        client.get(URL, headers=auth(second_student)),
    )
    assert len(ids(first)) == len(ids(second)) == 10
    assert not set(ids(first)) & set(ids(second))
    third_student = await another_student(seeded)
    third = set(ids(await client.get(URL, headers=auth(third_student))))
    assert len(third) == 10
    assert len(third & (set(ids(first)) | set(ids(second)))) == 6
    assert third <= {str(c) for c in contacts}


async def test_quality_rewards_invitations_penalizes_ignores_and_skips_broken_and_known(
    client, seeded, pool, monkeypatch
):
    _, contacts, _ = pool
    monkeypatch.setattr(daily, "random_draw", lambda: literal(0.5))
    async with TestSession() as session:
        for index, kind in [
            (0, RecruiterFeedbackKind.INVITED),
            (1, RecruiterFeedbackKind.HELPFUL),
            *[(i, RecruiterFeedbackKind.IGNORES) for i in range(2, 13)],
            (13, RecruiterFeedbackKind.ACCOUNT_MISSING),
        ]:
            session.add(
                RecruiterFeedback(user_id=seeded.admin_id, recruiter_id=contacts[index], kind=kind)
            )
        session.add(RecruiterContactOpen(user_id=seeded.student_id, recruiter_id=contacts[14]))
        session.add(
            RecruiterFeedback(
                user_id=seeded.student_id,
                recruiter_id=contacts[15],
                kind=RecruiterFeedbackKind.HELPFUL,
            )
        )
        await session.commit()
    result = await client.get(URL, headers=auth(seeded.student_id))
    selected = set(ids(result))
    assert selected == {str(contacts[i]) for i in [0, 1, *range(16, 24)]}
    item = next(
        r for g in result.json()["items"] for r in g["recruiters"] if r["id"] == str(contacts[0])
    )
    assert item["invited_count"] == 1 and item["issue_comments_total"] == 0


async def test_student_contact_is_shown_once_across_companies_and_staff_has_full_directory(
    client, seeded, pool
):
    _, contacts, _ = pool
    async with TestSession() as session:
        company = Company(
            name="Я другая", normalized_name="я другая", transliterated_name="ya drugaya"
        )
        session.add(company)
        await session.flush()
        process = InterviewProcess(
            user_id=seeded.student_id,
            track_id=seeded.python_track_id,
            company_id=company.id,
            company_name=company.name,
        )
        session.add(process)
        await session.flush()
        session.add_all(
            [RecruiterContactProcess(recruiter_id=c, process_id=process.id) for c in contacts]
        )
        await session.commit()
    listing = await client.get(URL, headers=auth(seeded.student_id))
    assert len(ids(listing)) == len(set(ids(listing))) == 10
    staff = await client.get(URL, headers=auth(seeded.admin_id))
    assert set(ids(staff)) == {str(c) for c in contacts}
    assert staff.json()["daily"] is None


async def group_companies(contacts, groups):
    async with TestSession() as session:
        rows = (
            await session.execute(
                select(RecruiterContactProcess.recruiter_id, InterviewProcess).join(
                    InterviewProcess, InterviewProcess.id == RecruiterContactProcess.process_id
                )
            )
        ).all()
        processes = dict(rows)
        for group in groups:
            company_id = processes[contacts[group[0]]].company_id
            company_name = processes[contacts[group[0]]].company_name
            for index in group:
                processes[contacts[index]].company_id = company_id
                processes[contacts[index]].company_name = company_name
        await session.commit()


async def test_daily_prefers_ten_different_companies_and_quality_within_company(
    client, seeded, pool, monkeypatch
):
    _, contacts, _ = pool
    await group_companies(contacts, [list(range(i, i + 2)) for i in range(0, 24, 2)])
    monkeypatch.setattr(daily, "random_draw", lambda: literal(0.5))
    async with TestSession() as session:
        session.add(
            RecruiterFeedback(
                user_id=seeded.admin_id,
                recruiter_id=contacts[0],
                kind=RecruiterFeedbackKind.INVITED,
            )
        )
        await session.commit()
    result = await client.get(URL, headers=auth(seeded.student_id))
    assert len(ids(result)) == 10
    assert len(result.json()["items"]) == 10
    assert all(len(group["recruiters"]) == 1 for group in result.json()["items"])
    assert str(contacts[0]) in ids(result) and str(contacts[1]) not in ids(result)


@pytest.mark.parametrize("company_size,expected_contacts", [(4, 10), (24, 2)])
async def test_company_shortage_fills_second_contacts_but_never_third(
    client, seeded, pool, company_size, expected_contacts
):
    _, contacts, _ = pool
    await group_companies(
        contacts, [list(range(i, i + company_size)) for i in range(0, 24, company_size)]
    )
    result = await client.get(URL, headers=auth(seeded.student_id))
    assert len(ids(result)) == expected_contacts
    assert len(result.json()["items"]) == 24 // company_size
    assert all(1 <= len(group["recruiters"]) <= 2 for group in result.json()["items"])
    full = await client.get(URL, headers=auth(seeded.student_id), params={"view": "all"})
    assert len(ids(full)) == 24


@pytest.mark.parametrize(
    "history_kind", ["assigned", "opened", "helpful", "ignores", "other_user_ignores"]
)
async def test_personal_ignores_promotes_another_contact_only_in_future_batches(
    client, seeded, pool, monkeypatch, history_kind
):
    clock, contacts, _ = pool
    await group_companies(contacts, [[0, 1, 2]])
    monkeypatch.setattr(daily, "random_draw", lambda: literal(0.5))
    async with TestSession() as session:
        if history_kind == "assigned":
            previous_day = (clock[0] - timedelta(days=3)).date()
            session.add(RecruiterDailyBatch(user_id=seeded.student_id, day=previous_day))
            await session.flush()
            session.add(
                RecruiterDailyAssignment(
                    user_id=seeded.student_id,
                    day=previous_day,
                    recruiter_id=contacts[0],
                    position=1,
                )
            )
        else:
            session.add(RecruiterContactOpen(user_id=seeded.student_id, recruiter_id=contacts[0]))
        if history_kind in {"helpful", "ignores", "other_user_ignores"}:
            session.add(
                RecruiterFeedback(
                    user_id=seeded.admin_id
                    if history_kind == "other_user_ignores"
                    else seeded.student_id,
                    recruiter_id=contacts[0],
                    kind=RecruiterFeedbackKind.HELPFUL
                    if history_kind == "helpful"
                    else RecruiterFeedbackKind.IGNORES,
                )
            )
        session.add(
            RecruiterFeedback(
                user_id=seeded.admin_id,
                recruiter_id=contacts[1],
                kind=RecruiterFeedbackKind.INVITED,
            )
        )
        await session.commit()
    selected = set(ids(await client.get(URL, headers=auth(seeded.student_id))))
    assert len(selected) == 10
    assert (str(contacts[1]) in selected) == (history_kind == "ignores")
    assert str(contacts[0]) not in selected and str(contacts[2]) not in selected
    if history_kind != "ignores":
        response = await client.put(
            f"{URL}/{contacts[0]}/feedback",
            headers=auth(seeded.student_id),
            json={"kind": "ignores"},
        )
        assert response.status_code == 200
        assert set(ids(await client.get(URL, headers=auth(seeded.student_id)))) == selected
        clock[0] += timedelta(days=1)
        tomorrow = set(ids(await client.get(URL, headers=auth(seeded.student_id))))
        assert str(contacts[1]) in tomorrow and not tomorrow & selected


async def test_migration_roundtrip_preserves_feedback(pool, seeded):
    path = (
        Path(__file__).parents[1] / "migrations/versions/20260921_0087_recruiter_daily_batches.py"
    )
    spec = importlib.util.spec_from_file_location("daily_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    async with TestSession() as session:
        session.add(
            RecruiterFeedback(
                user_id=seeded.admin_id, recruiter_id=pool[1][0], kind=RecruiterFeedbackKind.INVITED
            )
        )
        await session.commit()

    def migrate(conn):
        with Operations.context(MigrationContext.configure(conn)):
            migration.downgrade()
            migration.upgrade()

    async with test_engine.begin() as conn:
        await conn.run_sync(migrate)
    async with TestSession() as session:
        row = await session.get(RecruiterFeedback, (pool[1][0], seeded.admin_id))
        assert row.kind is RecruiterFeedbackKind.HELPFUL
