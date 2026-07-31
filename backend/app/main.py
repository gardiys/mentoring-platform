import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.core.config import get_settings
from app.core.middleware import RequestContextMiddleware
from app.integrations.router import router as integrations_router
from app.interviews.admin_router import router as admin_interviews_router
from app.interviews.router import router as interviews_router
from app.knowledge.admin_router import router as admin_knowledge_router
from app.knowledge.router import router as knowledge_router
from app.mentors.router import router as mentors_router
from app.roadmaps.admin_router import router as admin_roadmaps_router
from app.roadmaps.router import router as roadmaps_router
from app.tracks.admin_router import router as admin_tracks_router
from app.users.router import router as users_router

settings = get_settings()
logging.basicConfig(level=settings.log_level)

app = FastAPI(title="Mentoring Platform API", version="0.2.0", debug=settings.app_debug)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health_router)
app.include_router(integrations_router, prefix="/api/v1")
app.include_router(interviews_router, prefix="/api/v1")
app.include_router(admin_interviews_router, prefix="/api/v1")
app.include_router(knowledge_router, prefix="/api/v1")
app.include_router(admin_knowledge_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
app.include_router(roadmaps_router, prefix="/api/v1")
app.include_router(mentors_router, prefix="/api/v1")
app.include_router(admin_roadmaps_router, prefix="/api/v1")
app.include_router(admin_tracks_router, prefix="/api/v1")
