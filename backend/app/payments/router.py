from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import AdminUser, MentorUser, StudentUser
from app.core.config import get_settings
from app.core.errors import api_error
from app.db.session import get_db_session
from app.interviews.schemas import (
    InterviewDownloadUrl,
    InterviewMultipartUploadIntent,
    InterviewUploadComplete,
    InterviewUploadIntent,
    InterviewUploadIntentResponse,
    InterviewUploadProtocol,
    InterviewUploadRequest,
)
from app.interviews.upload_cleanup import delete_upload_if_unreferenced
from app.interviews.uploads import (
    CompletedMultipartUploadPart,
    InterviewUploadStore,
    StoredUpload,
)
from app.payments.models import (
    PaymentAttempt,
    PaymentAttemptStatus,
    PaymentInstallment,
    PaymentInstallmentStatus,
    PaymentWebhookEvent,
)
from app.payments.schemas import (
    AdminMentorPayoutCancelMutation,
    AdminMentorPayoutDashboard,
    AdminMentorPayoutDetail,
    AdminPaymentPage,
    AdminPaymentStudentPage,
    EmploymentMutation,
    EmploymentTerminationMutation,
    MentorPayoutAmountMutation,
    MentorPayoutCancelMutation,
    MentorPayoutEditMutation,
    MentorPayoutMarkPaidMutation,
    MentorRewardSummary,
    MentorRewardVoidMutation,
    PaymentDaysMutation,
    PaymentLinkRead,
    PaymentRevocationMutation,
    StudentPaymentDashboard,
    WebhookResult,
)
from app.payments.service import (
    admin_mentor_payout_dashboard,
    admin_mentor_payout_detail,
    admin_payment_page,
    admin_payment_student_page,
    cancel_mentor_payout,
    confirm_installment,
    create_admin_mentor_payout,
    create_payment_link,
    delete_mentor_payout_receipt,
    edit_mentor_payout,
    ensure_mentor_payout_receipt_upload_allowed,
    mark_installment_paid,
    mark_mentor_payout_paid,
    mark_mentor_reward_paid,
    mentor_reward_summary,
    payment_dashboard,
    payout_receipt_upload,
    request_mentor_payout,
    revoke_installment_payment,
    set_employment,
    set_mentor_payout_receipt,
    set_payment_days,
    terminate_employment,
    void_mentor_reward,
)
from app.payments.tochka import (
    TochkaPaymentService,
    extract_payment_status,
    map_payment_status,
    parse_webhook_body,
    parse_webhook_event,
)

Session = Annotated[AsyncSession, Depends(get_db_session)]
router = APIRouter(prefix="/payments", tags=["payments"])
mentor_router = APIRouter(prefix="/mentor", tags=["mentor-payments"])
admin_router = APIRouter(prefix="/admin/payments", tags=["admin-payments"])
settings = get_settings()
store = InterviewUploadStore(settings)
PAYOUT_RECEIPT_TYPES = ("image", "application/pdf")
PAYOUT_RECEIPT_MAX_BYTES = 20 * 1024 * 1024


def _kopecks(amount_rubles: Decimal) -> int:
    return int(amount_rubles * 100)


async def _receipt_upload_intent(
    mentor_id: UUID,
    payout_id: UUID,
    payload: InterviewUploadRequest,
) -> InterviewUploadIntentResponse:
    if payload.upload_protocol is InterviewUploadProtocol.MULTIPART_V1:
        multipart_intent = await store.create_multipart_upload_intent(
            user_id=mentor_id,
            category="mentor-payout-receipt",
            resource=f"mentor-payout-receipt:{payout_id}",
            filename=payload.filename,
            content_type=payload.content_type,
            size=payload.size,
            allowed_content_types=PAYOUT_RECEIPT_TYPES,
            max_bytes=PAYOUT_RECEIPT_MAX_BYTES,
        )
        return InterviewMultipartUploadIntent.model_validate(multipart_intent, from_attributes=True)
    intent = store.create_upload_intent(
        user_id=mentor_id,
        category="mentor-payout-receipt",
        filename=payload.filename,
        content_type=payload.content_type,
        size=payload.size,
        allowed_content_types=PAYOUT_RECEIPT_TYPES,
        max_bytes=PAYOUT_RECEIPT_MAX_BYTES,
    )
    return InterviewUploadIntent.model_validate(intent, from_attributes=True)


async def _complete_receipt_upload(
    mentor_id: UUID,
    payout_id: UUID,
    payload: InterviewUploadComplete,
) -> StoredUpload:
    if payload.upload_protocol is InterviewUploadProtocol.MULTIPART_V1:
        if payload.upload_id is None or payload.upload_token is None:
            api_error(422, "invalid_payout_receipt_upload", "Multipart metadata is invalid")
        return await store.complete_multipart_upload(
            user_id=mentor_id,
            category="mentor-payout-receipt",
            resource=f"mentor-payout-receipt:{payout_id}",
            storage_key=payload.storage_key,
            upload_id=payload.upload_id,
            upload_token=payload.upload_token,
            filename=payload.filename,
            content_type=payload.content_type,
            expected_size=payload.size,
            parts=tuple(
                CompletedMultipartUploadPart(part_number=part.part_number, etag=part.etag)
                for part in payload.parts
            ),
            allowed_content_types=PAYOUT_RECEIPT_TYPES,
            max_bytes=PAYOUT_RECEIPT_MAX_BYTES,
        )
    return await store.complete_upload(
        user_id=mentor_id,
        category="mentor-payout-receipt",
        storage_key=payload.storage_key,
        filename=payload.filename,
        content_type=payload.content_type,
        expected_size=payload.size,
        allowed_content_types=PAYOUT_RECEIPT_TYPES,
        max_bytes=PAYOUT_RECEIPT_MAX_BYTES,
    )


@router.get("/me", response_model=StudentPaymentDashboard)
async def my_payments(session: Session, student: StudentUser) -> StudentPaymentDashboard:
    return await payment_dashboard(session, student, student.id)


@router.put("/me/schedule", response_model=StudentPaymentDashboard)
async def update_my_payment_days(
    payload: PaymentDaysMutation,
    session: Session,
    student: StudentUser,
) -> StudentPaymentDashboard:
    return await set_payment_days(session, student, student.id, payload.payment_days)


@router.post("/installments/{installment_id}/link", response_model=PaymentLinkRead)
async def installment_payment_link(
    installment_id: UUID,
    session: Session,
    student: StudentUser,
) -> PaymentLinkRead:
    return await create_payment_link(session, student, installment_id)


@mentor_router.get(
    "/students/{student_id}/payments",
    response_model=StudentPaymentDashboard,
)
async def mentor_student_payments(
    student_id: UUID,
    session: Session,
    mentor: MentorUser,
) -> StudentPaymentDashboard:
    return await payment_dashboard(session, mentor, student_id)


@mentor_router.put(
    "/students/{student_id}/employment",
    response_model=StudentPaymentDashboard,
)
async def mentor_set_student_employment(
    student_id: UUID,
    payload: EmploymentMutation,
    session: Session,
    mentor: MentorUser,
) -> StudentPaymentDashboard:
    return await set_employment(session, mentor, student_id, payload)


@mentor_router.post(
    "/students/{student_id}/employment/terminate",
    response_model=StudentPaymentDashboard,
)
async def mentor_terminate_student_employment(
    student_id: UUID,
    payload: EmploymentTerminationMutation,
    session: Session,
    mentor: MentorUser,
) -> StudentPaymentDashboard:
    return await terminate_employment(session, mentor, student_id, payload)


@mentor_router.get("/rewards", response_model=MentorRewardSummary)
async def my_mentor_rewards(session: Session, mentor: MentorUser) -> MentorRewardSummary:
    return await mentor_reward_summary(session, mentor)


@mentor_router.post("/payouts", response_model=MentorRewardSummary)
async def create_my_payout_request(
    payload: MentorPayoutAmountMutation,
    session: Session,
    mentor: MentorUser,
) -> MentorRewardSummary:
    return await request_mentor_payout(session, mentor, _kopecks(payload.amount_rubles))


@mentor_router.post("/payouts/{payout_id}/cancel", response_model=MentorRewardSummary)
async def cancel_my_payout_request(
    payout_id: UUID,
    payload: MentorPayoutCancelMutation,
    session: Session,
    mentor: MentorUser,
) -> MentorRewardSummary:
    await cancel_mentor_payout(session, mentor, payout_id, payload.reason)
    return await mentor_reward_summary(session, mentor)


@mentor_router.post(
    "/payouts/{payout_id}/receipt/upload",
    response_model=InterviewUploadIntentResponse,
)
async def create_payout_receipt_upload(
    payout_id: UUID,
    payload: InterviewUploadRequest,
    session: Session,
    mentor: MentorUser,
) -> InterviewUploadIntentResponse:
    await ensure_mentor_payout_receipt_upload_allowed(session, mentor, payout_id)
    return await _receipt_upload_intent(mentor.id, payout_id, payload)


@mentor_router.post("/payouts/{payout_id}/receipt/complete", response_model=MentorRewardSummary)
async def complete_payout_receipt_upload(
    payout_id: UUID,
    payload: InterviewUploadComplete,
    session: Session,
    mentor: MentorUser,
) -> MentorRewardSummary:
    await ensure_mentor_payout_receipt_upload_allowed(session, mentor, payout_id)
    upload = await _complete_receipt_upload(mentor.id, payout_id, payload)
    try:
        summary, previous_key = await set_mentor_payout_receipt(session, mentor, payout_id, upload)
    except Exception:
        await delete_upload_if_unreferenced(session, store, upload.storage_key)
        raise
    if previous_key != upload.storage_key:
        await store.delete(previous_key)
    return summary


@mentor_router.get("/payouts/{payout_id}/receipt", response_model=InterviewDownloadUrl)
async def open_payout_receipt(
    payout_id: UUID,
    session: Session,
    mentor: MentorUser,
) -> InterviewDownloadUrl:
    upload = await payout_receipt_upload(session, mentor, payout_id)
    return InterviewDownloadUrl(url=store.download_url(upload, inline=True))


@mentor_router.delete("/payouts/{payout_id}/receipt", response_model=MentorRewardSummary)
async def delete_payout_receipt(
    payout_id: UUID,
    session: Session,
    mentor: MentorUser,
) -> MentorRewardSummary:
    summary, previous_key = await delete_mentor_payout_receipt(session, mentor, payout_id)
    await store.delete(previous_key)
    return summary


@admin_router.get("", response_model=AdminPaymentPage)
async def admin_payments(
    session: Session,
    _admin: AdminUser,
    payment_status: Annotated[PaymentInstallmentStatus | None, Query(alias="status")] = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> AdminPaymentPage:
    return await admin_payment_page(session, status=payment_status, limit=limit, offset=offset)


@admin_router.get("/students", response_model=AdminPaymentStudentPage)
async def admin_payment_students(
    session: Session,
    _admin: AdminUser,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> AdminPaymentStudentPage:
    return await admin_payment_student_page(session, limit=limit, offset=offset)


@admin_router.get("/students/{student_id}", response_model=StudentPaymentDashboard)
async def admin_student_payments(
    student_id: UUID,
    session: Session,
    admin: AdminUser,
) -> StudentPaymentDashboard:
    return await payment_dashboard(session, admin, student_id)


@admin_router.get("/overdue", response_model=AdminPaymentPage)
async def admin_overdue_payments(
    session: Session,
    _admin: AdminUser,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> AdminPaymentPage:
    return await admin_payment_page(
        session,
        status=None,
        limit=limit,
        offset=offset,
        overdue_only=True,
    )


@admin_router.get("/mentor-payouts", response_model=AdminMentorPayoutDashboard)
async def admin_mentor_payouts(session: Session, _admin: AdminUser) -> AdminMentorPayoutDashboard:
    return await admin_mentor_payout_dashboard(session)


@admin_router.get("/mentors/{mentor_id}", response_model=AdminMentorPayoutDetail)
async def admin_mentor_payments(
    mentor_id: UUID,
    session: Session,
    _admin: AdminUser,
) -> AdminMentorPayoutDetail:
    return await admin_mentor_payout_detail(session, mentor_id)


@admin_router.post(
    "/mentors/{mentor_id}/payouts",
    response_model=AdminMentorPayoutDashboard,
)
async def admin_create_mentor_payout(
    mentor_id: UUID,
    payload: MentorPayoutAmountMutation,
    session: Session,
    admin: AdminUser,
) -> AdminMentorPayoutDashboard:
    return await create_admin_mentor_payout(
        session,
        admin,
        mentor_id,
        _kopecks(payload.amount_rubles),
        payload.payment_reference,
    )


@admin_router.post(
    "/payouts/{payout_id}/mark-paid",
    response_model=AdminMentorPayoutDashboard,
)
async def admin_mark_mentor_payout_paid(
    payout_id: UUID,
    payload: MentorPayoutMarkPaidMutation,
    session: Session,
    admin: AdminUser,
) -> AdminMentorPayoutDashboard:
    return await mark_mentor_payout_paid(session, admin, payout_id, payload.payment_reference)


@admin_router.patch(
    "/payouts/{payout_id}",
    response_model=AdminMentorPayoutDashboard,
)
async def admin_edit_mentor_payout(
    payout_id: UUID,
    payload: MentorPayoutEditMutation,
    session: Session,
    admin: AdminUser,
) -> AdminMentorPayoutDashboard:
    return await edit_mentor_payout(
        session,
        admin,
        payout_id,
        amount_kopecks=_kopecks(payload.amount_rubles),
        payment_reference=payload.payment_reference,
        paid_at=payload.paid_at,
        reason=payload.reason,
    )


@admin_router.post(
    "/payouts/{payout_id}/cancel",
    response_model=AdminMentorPayoutDashboard,
)
async def admin_cancel_mentor_payout(
    payout_id: UUID,
    payload: AdminMentorPayoutCancelMutation,
    session: Session,
    admin: AdminUser,
) -> AdminMentorPayoutDashboard:
    await cancel_mentor_payout(session, admin, payout_id, payload.reason)
    return await admin_mentor_payout_dashboard(session)


@admin_router.put(
    "/students/{student_id}/schedule",
    response_model=StudentPaymentDashboard,
)
async def admin_update_payment_days(
    student_id: UUID,
    payload: PaymentDaysMutation,
    session: Session,
    admin: AdminUser,
) -> StudentPaymentDashboard:
    return await set_payment_days(session, admin, student_id, payload.payment_days)


@admin_router.post(
    "/installments/{installment_id}/confirm",
    response_model=StudentPaymentDashboard,
)
async def admin_confirm_payment(
    installment_id: UUID,
    session: Session,
    admin: AdminUser,
) -> StudentPaymentDashboard:
    return await confirm_installment(session, installment_id, admin)


@admin_router.post(
    "/installments/{installment_id}/revoke",
    response_model=StudentPaymentDashboard,
)
async def admin_revoke_payment(
    installment_id: UUID,
    payload: PaymentRevocationMutation,
    session: Session,
    admin: AdminUser,
) -> StudentPaymentDashboard:
    return await revoke_installment_payment(session, installment_id, admin, payload)


@admin_router.post(
    "/rewards/{reward_id}/mark-paid",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def admin_mark_reward_paid(
    reward_id: UUID,
    session: Session,
    _admin: AdminUser,
) -> Response:
    await mark_mentor_reward_paid(session, reward_id, _admin)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@admin_router.post(
    "/rewards/{reward_id}/void",
    response_model=AdminMentorPayoutDashboard,
)
async def admin_void_mentor_reward(
    reward_id: UUID,
    payload: MentorRewardVoidMutation,
    session: Session,
    admin: AdminUser,
) -> AdminMentorPayoutDashboard:
    return await void_mentor_reward(session, admin, reward_id, payload.reason)


@admin_router.post("/tochka/webhook/configure")
async def configure_tochka_webhook(_admin: AdminUser) -> dict[str, Any]:
    callback_url = f"{settings.web_frontend_url.rstrip('/')}/api/v1/payments/tochka/webhook"
    return await TochkaPaymentService(settings).configure_webhook(callback_url)


@router.post("/tochka/webhook", response_model=WebhookResult)
async def tochka_webhook(request: Request, session: Session) -> WebhookResult:
    body = await request.body()
    if len(body) > 1_048_576:
        api_error(413, "webhook_too_large", "Webhook payload is too large")
    try:
        payload, is_signed = parse_webhook_body(
            body, request.headers.get("content-type", ""), settings
        )
        event = parse_webhook_event(payload)
    except (ValueError, json.JSONDecodeError) as error:
        api_error(400, "invalid_tochka_webhook", str(error))
    if event is None:
        return WebhookResult(status="ignored")

    existing = await session.scalar(
        select(PaymentWebhookEvent.id).where(
            PaymentWebhookEvent.deduplication_key == event.deduplication_key
        )
    )
    if existing is not None:
        return WebhookResult(status="duplicate")

    attempt = None
    if event.payment_link_id:
        attempt = await session.scalar(
            select(PaymentAttempt)
            .where(PaymentAttempt.payment_link_id == event.payment_link_id)
            .with_for_update()
        )
    if attempt is None and event.operation_id:
        attempt = await session.scalar(
            select(PaymentAttempt)
            .where(PaymentAttempt.provider_operation_id == event.operation_id)
            .with_for_update()
        )

    verified_status = await _verified_status(
        event.status,
        event.operation_id,
        is_signed,
        attempt=attempt,
    )
    if verified_status is None:
        return WebhookResult(status="unverified")
    webhook_event = PaymentWebhookEvent(
        attempt_id=attempt.id if attempt else None,
        provider="tochka",
        event_id=event.event_id,
        deduplication_key=event.deduplication_key,
        status=verified_status,
        raw_payload=event.raw_payload,
    )
    session.add(webhook_event)
    if attempt is None:
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return WebhookResult(status="duplicate")
        return WebhookResult(status="unknown_payment")

    if attempt.provider_operation_id is None and event.operation_id:
        attempt.provider_operation_id = event.operation_id
    mapped = PaymentAttemptStatus(map_payment_status(verified_status))
    attempt_was_revoked = attempt.status is PaymentAttemptStatus.REVOKED
    attempt.status = mapped
    installment = await session.scalar(
        select(PaymentInstallment)
        .where(PaymentInstallment.id == attempt.installment_id)
        .with_for_update()
    )
    if installment is not None:
        if mapped is PaymentAttemptStatus.APPROVED:
            if installment.status is PaymentInstallmentStatus.CANCELLED or attempt_was_revoked:
                attempt.status = PaymentAttemptStatus.MANUAL_REVIEW
            else:
                attempt.approved_at = datetime.now(UTC)
                await mark_installment_paid(
                    session,
                    installment,
                    confirmed_by=None,
                    approved_at=attempt.approved_at,
                )
        elif mapped in {PaymentAttemptStatus.FAILED, PaymentAttemptStatus.CANCELLED}:
            if installment.status is not PaymentInstallmentStatus.CANCELLED:
                installment.status = PaymentInstallmentStatus.SCHEDULED
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return WebhookResult(status="duplicate")
    return WebhookResult(status="ok")


async def _verified_status(
    webhook_status: str,
    operation_id: str | None,
    is_signed: bool,
    *,
    attempt: PaymentAttempt | None,
) -> str | None:
    if is_signed or settings.app_env != "production":
        return webhook_status
    if not operation_id or attempt is None:
        return None
    try:
        raw = await TochkaPaymentService(settings).get_payment_operation_info(operation_id)
    except Exception:
        return None
    if attempt.provider_operation_id is not None:
        if attempt.provider_operation_id != operation_id:
            return None
    else:
        try:
            verified_event = parse_webhook_event(raw)
        except ValueError:
            return None
        if verified_event is None or verified_event.payment_link_id != attempt.payment_link_id:
            return None
    return extract_payment_status(raw)
