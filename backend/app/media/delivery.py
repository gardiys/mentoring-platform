from fastapi import status
from fastapi.responses import RedirectResponse

from app.interviews.uploads import InterviewUploadStore, StoredUpload


def direct_private_media_response(
    store: InterviewUploadStore,
    upload: StoredUpload,
    *,
    expires_in: int,
) -> RedirectResponse:
    """Authorize in the application, then let S3 serve byte ranges directly.

    The stable application URL remains protected by the HttpOnly playback
    ticket. The storage URL is deliberately short-lived so it cannot be shared
    as a durable public link, while video bytes avoid the slow
    S3 -> FastAPI -> reverse proxy relay.
    """

    return RedirectResponse(
        url=store.download_url(upload, inline=True, expires_in=expires_in),
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
        headers={
            "Cache-Control": "private, no-store, max-age=0",
            "Pragma": "no-cache",
            "Referrer-Policy": "no-referrer",
            "Vary": "Cookie, User-Agent",
            "X-Content-Type-Options": "nosniff",
        },
    )
