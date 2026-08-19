from typing import Annotated

from fastapi import APIRouter, Query

from app.auth.dependencies import AdminUser
from app.core.config import get_settings
from app.onboarding_applications.client import OnboardingBotClient
from app.onboarding_applications.schemas import (
    OnboardingApplicationActionRequest,
    OnboardingApplicationActionResponse,
    OnboardingApplicationDetail,
    OnboardingApplicationPage,
)

router = APIRouter(prefix="/admin/applications", tags=["admin-applications"])


@router.get("", response_model=OnboardingApplicationPage)
async def admin_applications(
    _admin: AdminUser,
    status: Annotated[list[str] | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OnboardingApplicationPage:
    return await OnboardingBotClient(get_settings()).applications(
        statuses=status,
        search=q,
        limit=limit,
        offset=offset,
    )


@router.get("/{applicant_id}", response_model=OnboardingApplicationDetail)
async def admin_application(
    applicant_id: str,
    _admin: AdminUser,
) -> OnboardingApplicationDetail:
    return await OnboardingBotClient(get_settings()).application(applicant_id)


@router.post("/{applicant_id}/actions", response_model=OnboardingApplicationActionResponse)
async def admin_application_action(
    applicant_id: str,
    payload: OnboardingApplicationActionRequest,
    admin: AdminUser,
) -> OnboardingApplicationActionResponse:
    return await OnboardingBotClient(get_settings()).execute_action(
        applicant_id,
        payload.action,
        comment=payload.comment,
        actor_id=str(admin.id),
        actor_telegram_id=admin.telegram_id,
    )
