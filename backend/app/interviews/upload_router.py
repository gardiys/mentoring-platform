from fastapi import APIRouter, Response, status

from app.auth.dependencies import CurrentUser
from app.core.config import get_settings
from app.interviews.schemas import InterviewMultipartUploadAbort
from app.interviews.uploads import InterviewUploadStore

router = APIRouter(prefix="/uploads", tags=["private-uploads"])
store = InterviewUploadStore(get_settings())


@router.post(
    "/multipart/abort",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def abort_private_multipart_upload(
    payload: InterviewMultipartUploadAbort,
    user: CurrentUser,
) -> Response:
    await store.abort_multipart_upload(
        user_id=user.id,
        storage_key=payload.storage_key,
        upload_id=payload.upload_id,
        upload_token=payload.upload_token,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
