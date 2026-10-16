"""Administrative stages shared by counts, inbox, details and reminders."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import DateTime, String, case, func, literal, select, text, union_all
from sqlalchemy.sql import ColumnElement, Select
from sqlalchemy.sql.selectable import Subquery

from app.opportunities.models import (
    ConsultationRequest as C,
)
from app.opportunities.models import (
    GoTransitionApplication as G,
)
from app.opportunities.models import (
    OpportunityPaymentAttempt as P,
)
from app.opportunities.models import (
    PythonRepeatApplication as R,
)
from app.opportunities.models import (
    PythonRepeatEmploymentOffer as O,
)
from app.opportunities.models import (
    PythonRepeatEnrollment as E,
)

THRESHOLDS = {
    "consultations": {"new": 24, "needs_schedule": 48, "needs_completion": 2, "payment_review": 0},
    "go_transition": {"new": 24, "expired": 0},
    "python_repeat": {"new": 48, "review": 48, "offer_review": 48, "needs_mentor": 24},
}
NEXT_ACTION = {
    "new": "Рассмотреть заявку",
    "review": "Принять решение",
    "awaiting_payment": "Ждём оплату от выпускника",
    "awaiting_student": "Ждём подтверждения выпускника",
    "payment_review": "Проверить оплату",
    "needs_schedule": "Согласовать время встречи",
    "scheduled": "Встреча назначена",
    "needs_completion": "Внести итог и закрыть",
    "expired": "Продлить условия или отменить заявку",
    "needs_mentor": "Назначить ментора",
    "offer_review": "Проверить оффер",
    "completed": "Консультация завершена",
    "cancelled": "Заявка отменена",
    "enrolled": "Зачислен в Go",
    "active": "Идёт программа",
    "closed": "Заявка закрыта",
}


@dataclass(frozen=True)
class Stage:
    stage: str
    next_action: str
    waiting_since: datetime | None
    overdue: bool


def stage_info(product: str, stage: str, waiting: datetime | None, at: datetime) -> Stage:
    threshold = THRESHOLDS[product].get(stage)
    overdue = bool(
        threshold is not None
        and waiting is not None
        and (threshold == 0 or at > waiting + timedelta(hours=threshold))
    )
    action = NEXT_ACTION[stage]
    if product == "consultations" and stage == "new":
        action = "Назначить ментора и выставить счёт"
    return Stage(stage, action, waiting, overdue)


def consultation_stage(
    item: C, *, manual_review_at: datetime | None = None, at: datetime | None = None
) -> Stage:
    at = at or datetime.now(UTC)
    end = (
        item.scheduled_at + timedelta(minutes=item.duration_minutes) if item.scheduled_at else None
    )
    status = str(item.status)
    if status == "requested":
        stage, waiting = "new", item.created_at
    elif status == "payment_pending" and manual_review_at is not None:
        stage, waiting = "payment_review", manual_review_at
    elif status == "payment_pending":
        stage, waiting = "awaiting_payment", None
    elif status == "paid":
        stage, waiting = "needs_schedule", item.paid_at or item.updated_at
    elif status == "scheduled" and end is not None and end <= at:
        stage, waiting = "needs_completion", end
    else:
        stage, waiting = status, None
    return stage_info("consultations", stage, waiting, at)


def go_transition_stage(item: G, *, at: datetime | None = None) -> Stage:
    at = at or datetime.now(UTC)
    waiting: datetime | None
    status = str(item.status)
    if status == "submitted":
        stage, waiting = "new", item.created_at
    elif status in {"approved", "payment_pending"}:
        expired = item.terms_expires_at is not None and item.terms_expires_at <= at
        stage, waiting = (
            ("expired", item.terms_expires_at) if expired else ("awaiting_student", None)
        )
    else:
        stage, waiting = ("enrolled" if status == "paid" else "closed"), None
    return stage_info("go_transition", stage, waiting, at)


def python_repeat_stage(
    item: R,
    *,
    enrollment: E | None = None,
    submitted_offer_at: datetime | None = None,
    at: datetime | None = None,
) -> Stage:
    at = at or datetime.now(UTC)
    status = str(item.status)
    if status in {"rejected", "cancelled", "expired"}:
        stage, waiting = "closed", None
    elif status == "submitted":
        stage, waiting = "new", item.created_at
    elif status == "under_review":
        stage, waiting = "review", item.updated_at
    elif status in {"needs_diagnostic", "needs_clarification"}:
        stage, waiting = "awaiting_student", None
    elif status in {"approved", "terms_accepted", "payment_pending"}:
        stage, waiting = "awaiting_payment", None
    elif status in {"paid", "enrolled"} and (enrollment is None or enrollment.mentor_id is None):
        stage, waiting = "needs_mentor", item.paid_at or item.updated_at
    elif submitted_offer_at is not None:
        stage, waiting = "offer_review", submitted_offer_at
    else:
        stage, waiting = "active", None
    return stage_info("python_repeat", stage, waiting, at)


def stage_rows(at: datetime) -> Subquery:
    """SQL counterpart of the pure stage functions; never loads archived rows to count them."""
    null_date = literal(None, type_=DateTime(timezone=True))
    last_status = (
        select(P.status)
        .where(P.consultation_request_id == C.id)
        .order_by(P.created_at.desc(), P.id.desc())
        .limit(1)
        .scalar_subquery()
    )
    last_date = (
        select(P.created_at)
        .where(P.consultation_request_id == C.id)
        .order_by(P.created_at.desc(), P.id.desc())
        .limit(1)
        .scalar_subquery()
    )
    end = C.scheduled_at + C.duration_minutes * text("interval '1 minute'")
    c_stage = case(
        (C.status == "requested", "new"),
        ((C.status == "payment_pending") & (last_status == "manual_review"), "payment_review"),
        (C.status == "payment_pending", "awaiting_payment"),
        (C.status == "paid", "needs_schedule"),
        ((C.status == "scheduled") & (end <= at), "needs_completion"),
        else_=C.status.cast(String),
    )
    c_wait = case(
        (C.status == "requested", C.created_at),
        ((C.status == "payment_pending") & (last_status == "manual_review"), last_date),
        (C.status == "paid", func.coalesce(C.paid_at, C.updated_at)),
        ((C.status == "scheduled") & (end <= at), end),
        else_=null_date,
    )
    g_expired = G.status.in_(["approved", "payment_pending"]) & (G.terms_expires_at <= at)
    g_stage = case(
        (G.status == "submitted", "new"),
        (g_expired, "expired"),
        (G.status.in_(["approved", "payment_pending"]), "awaiting_student"),
        (G.status == "paid", "enrolled"),
        else_="closed",
    )
    g_wait = case(
        (G.status == "submitted", G.created_at), (g_expired, G.terms_expires_at), else_=null_date
    )
    mentor = select(E.mentor_id).where(E.application_id == R.id).scalar_subquery()
    offer_at = (
        select(func.min(func.coalesce(O.submitted_at, O.created_at)))
        .join(E, E.id == O.enrollment_id)
        .where(E.application_id == R.id, O.status == "submitted")
        .scalar_subquery()
    )
    needs_mentor = R.status.in_(["paid", "enrolled"]) & mentor.is_(None)
    r_stage = case(
        (R.status.in_(["rejected", "cancelled", "expired"]), "closed"),
        (R.status == "submitted", "new"),
        (R.status == "under_review", "review"),
        (R.status.in_(["needs_diagnostic", "needs_clarification"]), "awaiting_student"),
        (R.status.in_(["approved", "terms_accepted", "payment_pending"]), "awaiting_payment"),
        (needs_mentor, "needs_mentor"),
        (offer_at.is_not(None), "offer_review"),
        else_="active",
    )
    r_wait = case(
        (r_stage == "new", R.created_at),
        (r_stage == "review", R.updated_at),
        (r_stage == "needs_mentor", func.coalesce(R.paid_at, R.updated_at)),
        (r_stage == "offer_review", offer_at),
        else_=null_date,
    )
    queries = []
    configs: list[tuple[type[C] | type[G] | type[R], str, Any, Any, Any]] = [
        (
            C,
            "consultations",
            c_stage,
            c_wait,
            func.coalesce(C.scheduled_at, C.paid_at, C.created_at),
        ),
        (G, "go_transition", g_stage, g_wait, func.coalesce(G.terms_expires_at, G.created_at)),
        (R, "python_repeat", r_stage, r_wait, R.created_at),
    ]
    for model, product, stage, waiting, date in configs:
        query: Select[Any] = select(
            literal(product).label("product"),
            model.id.label("id"),
            model.student_id.label("student_id"),
            model.status.cast(String).label("status"),
            stage.label("stage"),
            waiting.label("waiting_since"),
            date.label("key_date"),
        )
        if model is R:
            query = query.where(R.status != "draft")
        queries.append(query)
    return union_all(*queries).subquery("opportunity_stages")


def overdue_sql(rows: Subquery, at: datetime) -> ColumnElement[bool]:
    return case(
        *[
            (
                (rows.c.product == product)
                & (rows.c.stage == stage)
                & (rows.c.waiting_since.is_not(None))
                & (
                    literal(True)
                    if hours == 0
                    else rows.c.waiting_since < at - timedelta(hours=hours)
                ),
                True,
            )
            for product, stages in THRESHOLDS.items()
            for stage, hours in stages.items()
        ],
        else_=False,
    )


def needs_action_sql(rows: Subquery) -> ColumnElement[bool]:
    return case(
        *[
            ((rows.c.product == product) & rows.c.stage.in_(list(stages)), True)
            for product, stages in THRESHOLDS.items()
        ],
        else_=False,
    )
