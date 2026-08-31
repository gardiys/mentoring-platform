import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.api.health import router as health_router
from app.auth.web_router import router as web_auth_router
from app.core.config import Settings, get_settings
from app.core.middleware import (
    CookieCSRFMiddleware,
    RequestBodyLimitMiddleware,
    RequestContextMiddleware,
)
from app.integrations.router import router as integrations_router
from app.interviews.admin_process_router import router as admin_interview_processes_router
from app.interviews.admin_router import router as admin_interviews_router
from app.interviews.card_automation_router import (
    admin_router as admin_card_automation_router,
)
from app.interviews.card_automation_router import (
    mentor_router as mentor_card_automation_router,
)
from app.interviews.card_automation_router import (
    student_router as student_card_automation_router,
)
from app.interviews.catalog_router import router as interview_catalog_router
from app.interviews.company_admin_router import router as company_alias_admin_router
from app.interviews.intelligence_operations_router import router as intelligence_operations_router
from app.interviews.intelligence_router import admin_router as admin_intelligence_router
from app.interviews.intelligence_router import mentor_router as mentor_intelligence_router
from app.interviews.intelligence_router import router as interview_intelligence_router
from app.interviews.journal_router import router as interview_journal_router
from app.interviews.recruiter_router import router as interview_recruiter_router
from app.interviews.router import router as interviews_router
from app.interviews.upload_router import router as private_uploads_router
from app.knowledge.admin_router import router as admin_knowledge_router
from app.knowledge.router import router as knowledge_router
from app.media.router import (
    admin_content_media_router,
    admin_knowledge_media_router,
    admin_roadmap_media_router,
    knowledge_media_router,
    roadmap_media_router,
)
from app.mentors.admin_router import router as admin_mentors_router
from app.mentors.router import router as mentors_router
from app.notifications.router import router as notifications_router
from app.onboarding_applications.router import router as onboarding_applications_router
from app.opportunities.router import admin_router as admin_opportunities_router
from app.opportunities.router import router as opportunities_router
from app.payments.router import (
    admin_router as admin_payments_router,
)
from app.payments.router import (
    mentor_router as mentor_payments_router,
)
from app.payments.router import (
    router as payments_router,
)
from app.roadmaps.admin_router import router as admin_roadmaps_router
from app.roadmaps.router import router as roadmaps_router
from app.schedule.router import (
    admin_schedule_router,
    admin_useful_links_router,
    mentor_profile_router,
    my_mentor_router,
)
from app.students.admin_router import router as admin_students_router
from app.tracks.admin_router import router as admin_tracks_router
from app.users.router import router as users_router

settings = get_settings()
logging.basicConfig(level=settings.log_level)


def create_app(app_settings: Settings | None = None) -> FastAPI:
    configured = app_settings or get_settings()
    production = configured.app_env == "production"
    application = FastAPI(
        title="Mentoring Platform API",
        version="0.2.0",
        debug=configured.app_debug,
        docs_url=None if production else "/docs",
        redoc_url=None if production else "/redoc",
        openapi_url=None if production else "/openapi.json",
    )

    # Middleware is registered from the innermost to the outermost layer.
    application.add_middleware(
        RequestBodyLimitMiddleware,
        max_body_size=configured.api_max_request_body_bytes,
    )
    application.add_middleware(
        CookieCSRFMiddleware,
        trusted_origins=configured.csrf_trusted_origins,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=configured.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.add_middleware(TrustedHostMiddleware, allowed_hosts=configured.trusted_hosts)
    application.add_middleware(RequestContextMiddleware)

    application.include_router(health_router)
    application.include_router(web_auth_router, prefix="/api/v1")
    application.include_router(integrations_router, prefix="/api/v1")
    application.include_router(interviews_router, prefix="/api/v1")
    application.include_router(interview_catalog_router, prefix="/api/v1")
    application.include_router(interview_journal_router, prefix="/api/v1")
    application.include_router(interview_recruiter_router, prefix="/api/v1")
    application.include_router(private_uploads_router, prefix="/api/v1")
    application.include_router(admin_interviews_router, prefix="/api/v1")
    application.include_router(admin_interview_processes_router, prefix="/api/v1")
    application.include_router(company_alias_admin_router, prefix="/api/v1")
    application.include_router(interview_intelligence_router, prefix="/api/v1")
    application.include_router(mentor_intelligence_router, prefix="/api/v1")
    application.include_router(admin_intelligence_router, prefix="/api/v1")
    application.include_router(intelligence_operations_router, prefix="/api/v1")
    application.include_router(admin_card_automation_router, prefix="/api/v1")
    application.include_router(mentor_card_automation_router, prefix="/api/v1")
    application.include_router(student_card_automation_router, prefix="/api/v1")
    application.include_router(knowledge_router, prefix="/api/v1")
    application.include_router(admin_knowledge_router, prefix="/api/v1")
    application.include_router(knowledge_media_router, prefix="/api/v1")
    application.include_router(admin_knowledge_media_router, prefix="/api/v1")
    application.include_router(admin_content_media_router, prefix="/api/v1")
    application.include_router(users_router, prefix="/api/v1")
    application.include_router(roadmaps_router, prefix="/api/v1")
    application.include_router(mentors_router, prefix="/api/v1")
    application.include_router(notifications_router, prefix="/api/v1")
    application.include_router(payments_router, prefix="/api/v1")
    application.include_router(mentor_payments_router, prefix="/api/v1")
    application.include_router(admin_payments_router, prefix="/api/v1")
    application.include_router(admin_mentors_router, prefix="/api/v1")
    application.include_router(admin_roadmaps_router, prefix="/api/v1")
    application.include_router(roadmap_media_router, prefix="/api/v1")
    application.include_router(admin_roadmap_media_router, prefix="/api/v1")
    application.include_router(admin_tracks_router, prefix="/api/v1")
    application.include_router(admin_students_router, prefix="/api/v1")
    application.include_router(onboarding_applications_router, prefix="/api/v1")
    application.include_router(opportunities_router, prefix="/api/v1")
    application.include_router(admin_opportunities_router, prefix="/api/v1")
    application.include_router(mentor_profile_router, prefix="/api/v1")
    application.include_router(my_mentor_router, prefix="/api/v1")
    application.include_router(admin_schedule_router, prefix="/api/v1")
    application.include_router(admin_useful_links_router, prefix="/api/v1")
    return application


app = create_app(settings)
