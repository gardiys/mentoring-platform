from __future__ import annotations

import hashlib
from typing import Any

import anyio

from app.core.config import get_settings
from app.legal.catalog import ROOT
from app.media.storage import PrivateMediaStore


class LegalDocumentError(RuntimeError):
    pass


async def read_document(key: str, expected_hash: str) -> bytes:
    path = (ROOT / key).resolve()
    if not path.is_relative_to(ROOT.resolve()) or not key.startswith("legal/offers/"):
        raise LegalDocumentError("invalid_document_key")
    try:
        if path.is_file():
            data = await anyio.to_thread.run_sync(path.read_bytes)
        else:
            store = PrivateMediaStore(get_settings())

            def read() -> bytes:
                response = store.client.get_object(Bucket=store.bucket, Key=key)
                try:
                    return bytes(response["Body"].read(10_000_001))
                finally:
                    response["Body"].close()

            data = await anyio.to_thread.run_sync(read)
    except Exception as error:
        raise LegalDocumentError("document_unavailable") from error
    if len(data) > 10_000_000 or hashlib.sha256(data).hexdigest() != expected_hash:
        raise LegalDocumentError("legal_offer_hash_mismatch")
    return data


async def put_document(key: str, data: bytes, mime: str) -> None:
    store = PrivateMediaStore(get_settings())

    def put() -> Any:
        # Conditional write prevents replacing even an unused object at an immutable key.
        return store.client.put_object(
            Bucket=store.bucket, Key=key, Body=data, ContentType=mime, IfNoneMatch="*"
        )

    await anyio.to_thread.run_sync(put)
