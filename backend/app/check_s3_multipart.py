from __future__ import annotations

import argparse
import asyncio
from uuid import uuid4

import httpx

from app.core.config import get_settings
from app.interviews.uploads import (
    CompletedMultipartUploadPart,
    InterviewUploadStore,
    MultipartUploadIntent,
)

SMOKE_PAYLOAD_SIZE = 6 * 1024 * 1024
SMOKE_CONTENT_TYPE = "application/octet-stream"
SMOKE_PLAYBACK_RANGE_SIZE = 1024 * 1024


def _error_label(error: Exception) -> str:
    if isinstance(error, httpx.HTTPStatusError):
        return f"HTTP_{error.response.status_code}"
    if isinstance(error, ValueError):
        return str(error)
    return type(error).__name__


async def check() -> int:
    settings = get_settings()
    store = InterviewUploadStore(settings)
    resource = f"s3-multipart-smoke:{uuid4().hex}"
    smoke_user_id = uuid4()
    intent: MultipartUploadIntent | None = None
    failure: str | None = None

    try:
        intent = await store.create_multipart_upload_intent(
            user_id=smoke_user_id,
            category="smoke-tests",
            resource=resource,
            filename="multipart-smoke.bin",
            content_type=SMOKE_CONTENT_TYPE,
            size=SMOKE_PAYLOAD_SIZE,
            allowed_content_types=(SMOKE_CONTENT_TYPE,),
            max_bytes=SMOKE_PAYLOAD_SIZE,
        )
        if len(intent.parts) != 1:
            raise ValueError("smoke payload must fit into one multipart part")

        part = intent.parts[0]
        origin = settings.web_frontend_url.rstrip("/")
        async with httpx.AsyncClient(timeout=120, follow_redirects=False) as client:
            response = await client.put(
                part.upload_url,
                content=b"m" * SMOKE_PAYLOAD_SIZE,
                headers={
                    **part.headers,
                    "Accept": "*/*",
                    "Origin": origin,
                    "Referer": f"{origin}/",
                    "Sec-Fetch-Mode": "cors",
                    "Sec-Fetch-Site": "same-site",
                    "User-Agent": "Mozilla/5.0 multipart-browser-smoke",
                },
            )
        response.raise_for_status()

        allowed_origin = response.headers.get("access-control-allow-origin")
        if allowed_origin != origin:
            browser_headers = ", ".join(
                f"{name}={value}"
                for name, value in response.headers.items()
                if name.casefold().startswith("access-control-") or name.casefold() == "etag"
            )
            raise ValueError(
                "S3 response does not allow the configured frontend origin "
                f"(expected {origin}, received {allowed_origin or 'missing'}; "
                f"browser headers: {browser_headers or 'missing'})"
            )
        exposed_headers = {
            item.strip().casefold()
            for item in response.headers.get("access-control-expose-headers", "").split(",")
            if item.strip()
        }
        if "etag" not in exposed_headers:
            raise ValueError("S3 response does not expose ETag to the browser")
        etag = response.headers.get("etag")
        if not etag:
            raise ValueError("S3 response does not contain ETag")

        upload = await store.complete_multipart_upload(
            user_id=smoke_user_id,
            category="smoke-tests",
            resource=resource,
            storage_key=intent.storage_key,
            upload_id=intent.upload_id,
            upload_token=intent.upload_token,
            filename=intent.filename,
            content_type=intent.content_type,
            expected_size=intent.size,
            parts=(CompletedMultipartUploadPart(part_number=1, etag=etag),),
            allowed_content_types=(SMOKE_CONTENT_TYPE,),
            max_bytes=SMOKE_PAYLOAD_SIZE,
        )
        if upload.size != SMOKE_PAYLOAD_SIZE:
            raise ValueError("completed object size does not match")

        playback_url = store.download_url(upload, inline=True, expires_in=60)
        async with httpx.AsyncClient(timeout=120, follow_redirects=False) as client:
            playback = await client.get(
                playback_url,
                headers={
                    "Accept": "*/*",
                    "Range": f"bytes=0-{SMOKE_PLAYBACK_RANGE_SIZE - 1}",
                    "User-Agent": "Mozilla/5.0 private-media-playback-smoke",
                },
            )
        playback.raise_for_status()
        expected_content_range = f"bytes 0-{SMOKE_PLAYBACK_RANGE_SIZE - 1}/{SMOKE_PAYLOAD_SIZE}"
        if playback.status_code != 206:
            raise ValueError(
                "S3 signed playback does not support byte ranges "
                f"(expected 206, received {playback.status_code})"
            )
        if playback.headers.get("content-range") != expected_content_range:
            raise ValueError(
                "S3 signed playback returned an invalid Content-Range "
                f"(expected {expected_content_range}, received "
                f"{playback.headers.get('content-range') or 'missing'})"
            )
        if len(playback.content) != SMOKE_PLAYBACK_RANGE_SIZE:
            raise ValueError("S3 signed playback returned an invalid byte-range length")
    except Exception as error:  # noqa: BLE001 - report only a sanitized smoke label
        failure = _error_label(error)
    finally:
        if intent is not None:
            try:
                await store.abort_multipart_upload(
                    user_id=smoke_user_id,
                    storage_key=intent.storage_key,
                    upload_id=intent.upload_id,
                    upload_token=intent.upload_token,
                )
            except Exception as error:  # noqa: BLE001 - cleanup must remain best effort
                failure = failure or f"cleanup:{_error_label(error)}"
            try:
                await store.delete(intent.storage_key)
            except Exception as error:  # noqa: BLE001 - cleanup must remain best effort
                failure = failure or f"cleanup:{_error_label(error)}"

    if failure is not None:
        print(f"S3 multipart browser smoke: FAILED ({failure})")
        return 1
    print("S3 multipart browser smoke: OK (temporary object deleted)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Upload through a public presigned URL, verify browser CORS/ETag, "
            "complete, verify signed byte-range playback, HEAD, and delete a "
            "temporary S3 multipart object."
        )
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="confirm the temporary write/delete smoke operation",
    )
    args = parser.parse_args()
    if not args.confirm:
        print("S3 multipart browser smoke: REFUSED (pass --confirm for a temporary object)")
        return 2
    return asyncio.run(check())


if __name__ == "__main__":
    raise SystemExit(main())
