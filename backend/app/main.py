import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.auth.web_router import router as web_auth_router
from app.core.config import get_settings
from app.core.middleware import RequestContextMiddleware
from app.integrations.router import router as integrations_router
from app.interviews.admin_process_router import router as admin_interview_processes_router
from app.interviews.admin_router import router as admin_interviews_router
from app.interviews.catalog_router import router as interview_catalog_router
from app.interviews.intelligence_operations_router import router as intelligence_operations_router
from app.interviews.intelligence_router import admin_router as admin_intelligence_router
from app.interviews.intelligence_router import mentor_router as mentor_intelligence_router
from app.interviews.intelligence_router import router as interview_intelligence_router
from app.interviews.journal_router import router as interview_journal_router
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

app = FastAPI(title="Mentoring Platform API", version="0.2.0", debug=settings.app_debug)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health_router)
app.include_router(web_auth_router, prefix="/api/v1")
app.include_router(integrations_router, prefix="/api/v1")
app.include_router(interviews_router, prefix="/api/v1")
app.include_router(interview_catalog_router, prefix="/api/v1")
app.include_router(interview_journal_router, prefix="/api/v1")
app.include_router(private_uploads_router, prefix="/api/v1")
app.include_router(admin_interviews_router, prefix="/api/v1")
app.include_router(admin_interview_processes_router, prefix="/api/v1")
app.include_router(interview_intelligence_router, prefix="/api/v1")
app.include_router(mentor_intelligence_router, prefix="/api/v1")
app.include_router(admin_intelligence_router, prefix="/api/v1")
app.include_router(intelligence_operations_router, prefix="/api/v1")
app.include_router(knowledge_router, prefix="/api/v1")
app.include_router(admin_knowledge_router, prefix="/api/v1")
app.include_router(knowledge_media_router, prefix="/api/v1")
app.include_router(admin_knowledge_media_router, prefix="/api/v1")
app.include_router(admin_content_media_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
app.include_router(roadmaps_router, prefix="/api/v1")
app.include_router(mentors_router, prefix="/api/v1")
app.include_router(payments_router, prefix="/api/v1")
app.include_router(mentor_payments_router, prefix="/api/v1")
app.include_router(admin_payments_router, prefix="/api/v1")
app.include_router(admin_mentors_router, prefix="/api/v1")
app.include_router(admin_roadmaps_router, prefix="/api/v1")
app.include_router(roadmap_media_router, prefix="/api/v1")
app.include_router(admin_roadmap_media_router, prefix="/api/v1")
app.include_router(admin_tracks_router, prefix="/api/v1")
app.include_router(admin_students_router, prefix="/api/v1")
app.include_router(mentor_profile_router, prefix="/api/v1")
app.include_router(my_mentor_router, prefix="/api/v1")
app.include_router(admin_schedule_router, prefix="/api/v1")
app.include_router(admin_useful_links_router, prefix="/api/v1")
