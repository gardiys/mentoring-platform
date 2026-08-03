from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import AdminUser
from app.db.session import get_db_session
from app.interviews.intelligence_operations_service import admin_intelligence_operations
from app.interviews.intelligence_schemas import AdminIntelligenceOperationsRead

router = APIRouter(prefix="/admin/interviews/ai-operations", tags=["admin-interviews"])
Session = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("", response_model=AdminIntelligenceOperationsRead)
async def admin_ai_operations(
    session: Session,
    _admin: AdminUser,
) -> AdminIntelligenceOperationsRead:
    return await admin_intelligence_operations(session)
