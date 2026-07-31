from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import AdminUser
from app.db.session import get_db_session
from app.tracks.schemas import (
    AdminTrackMutation,
    AdminTrackOptions,
    AdminTrackRead,
    TrackAccessRead,
)
from app.tracks.service import (
    create_track,
    get_admin_track,
    get_admin_track_options,
    grant_track_access,
    list_admin_tracks,
    revoke_track_access,
    update_track,
)

router = APIRouter(prefix="/admin/tracks", tags=["admin-tracks"])
Session = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("", response_model=list[AdminTrackRead])
async def admin_tracks(session: Session, _admin: AdminUser) -> list[AdminTrackRead]:
    return await list_admin_tracks(session)


@router.get("/options", response_model=AdminTrackOptions)
async def admin_track_options(session: Session, _admin: AdminUser) -> AdminTrackOptions:
    return await get_admin_track_options(session)


@router.post("", response_model=AdminTrackRead, status_code=status.HTTP_201_CREATED)
async def admin_create_track(
    payload: AdminTrackMutation, session: Session, _admin: AdminUser
) -> AdminTrackRead:
    return await create_track(session, payload)


@router.get("/{track_id}", response_model=AdminTrackRead)
async def admin_track(track_id: UUID, session: Session, _admin: AdminUser) -> AdminTrackRead:
    return await get_admin_track(session, track_id)


@router.put("/{track_id}", response_model=AdminTrackRead)
async def admin_update_track(
    track_id: UUID,
    payload: AdminTrackMutation,
    session: Session,
    _admin: AdminUser,
) -> AdminTrackRead:
    return await update_track(session, track_id, payload)


@router.put("/{track_id}/students/{student_id}", response_model=TrackAccessRead)
async def admin_grant_track(
    track_id: UUID,
    student_id: UUID,
    session: Session,
    _admin: AdminUser,
) -> TrackAccessRead:
    await grant_track_access(session, track_id, student_id)
    return TrackAccessRead(track_id=track_id, student_id=student_id, granted=True)


@router.delete("/{track_id}/students/{student_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_revoke_track(
    track_id: UUID,
    student_id: UUID,
    session: Session,
    _admin: AdminUser,
) -> Response:
    await revoke_track_access(session, track_id, student_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
