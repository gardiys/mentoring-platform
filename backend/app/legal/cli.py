"""poetry run python -m app.legal.cli import|activate|verify-bundled ..."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select

from app.db import models as _models  # noqa: F401
from app.db.session import async_session_factory
from app.legal.catalog import PRODUCTS, ROOT, financial_terms, manifest, validate_files
from app.legal.models import LegalOfferVersion
from app.legal.router import offer_status
from app.legal.schemas import OfferStatus
from app.legal.storage import put_document, read_document
from app.users.models import User, UserRole


async def run(args: argparse.Namespace) -> None:
    if args.command == "verify-bundled":
        for bundled in manifest():
            data = await read_document(bundled["pdf_storage_key"], bundled["pdf_sha256"])
            bundled_markdown = await read_document(
                bundled["markdown_storage_key"], bundled["markdown_sha256"]
            )
            validate_files(data, bundled_markdown.decode())
            if len(data) != bundled["pdf_size"]:
                raise ValueError("PDF size mismatch")
            print(bundled["product_code"], bundled["pdf_sha256"], bundled["pdf_storage_key"])
        return
    async with async_session_factory() as session:
        admin = await session.get(User, args.admin_id)
        if admin is None or admin.role is not UserRole.ADMIN or not admin.is_active:
            raise ValueError("An active administrator --admin-id is required")
        row = await session.scalar(
            select(LegalOfferVersion).where(
                LegalOfferVersion.product_code == args.product,
                LegalOfferVersion.version_code == args.version,
            )
        )
        if args.command == "activate":
            if row is None:
                raise ValueError("Import the offer first")
            await offer_status(row.id, OfferStatus(status="active"), session, admin)
            print("Activated", args.product, args.version)
            return
        pdf = Path(args.pdf).read_bytes()
        markdown: bytes | None = Path(args.markdown).read_bytes() if args.markdown else None
        validate_files(pdf, markdown.decode() if markdown else None)
        digest = hashlib.sha256(pdf).hexdigest()
        md_hash = hashlib.sha256(markdown).hexdigest() if markdown else None
        if row is not None:
            if (
                row.pdf_sha256 != digest
                or row.markdown_sha256 != md_hash
                or row.publication_date != date.fromisoformat(args.publication_date)
                or row.financial_terms != financial_terms()
            ):
                raise ValueError("Existing versions are immutable; use a new version code")
            print("Already imported", digest, row.pdf_storage_key)
            return
        prefix = f"legal/offers/{PRODUCTS[args.product]['slug']}/{args.version}"
        pdf_key = f"{prefix}/{digest}.pdf"
        md_key = f"{prefix}/{md_hash}.md" if markdown else None
        if not args.dry_run:
            for key, file_bytes, mime in [
                (pdf_key, pdf, "application/pdf"),
                (md_key, markdown, "text/markdown"),
            ]:
                if key and file_bytes:
                    # Bundled imports share the exact same immutable keys.
                    if not (ROOT / key).is_file():
                        try:
                            await put_document(key, file_bytes, mime)
                        except Exception:
                            # A previous import may have uploaded but crashed before commit.
                            await read_document(key, hashlib.sha256(file_bytes).hexdigest())
            row = LegalOfferVersion(
                id=uuid4(),
                product_code=args.product,
                version_code=args.version,
                title=PRODUCTS[args.product]["title"],
                publication_date=date.fromisoformat(args.publication_date),
                effective_from=datetime.fromisoformat(args.publication_date).replace(tzinfo=UTC),
                pdf_storage_key=pdf_key,
                markdown_storage_key=md_key,
                pdf_sha256=digest,
                markdown_sha256=md_hash,
                pdf_size=len(pdf),
                financial_terms=financial_terms(),
            )
            session.add(row)
            from app.legal.service import audit

            audit(session, "offer.imported", row.id, admin.id, product_code=args.product)
            await session.commit()
        print(digest, pdf_key, md_key or "")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("verify-bundled")
    for command in ("import", "activate"):
        sub = commands.add_parser(command)
        sub.add_argument("--product", required=True, choices=PRODUCTS)
        sub.add_argument(
            "--version", required=True, type=lambda value: date.fromisoformat(value).isoformat()
        )
        sub.add_argument("--admin-id", required=True, type=UUID)
        if command == "import":
            sub.add_argument("--publication-date", required=True)
            sub.add_argument("--pdf", required=True)
            sub.add_argument("--markdown")
            sub.add_argument("--dry-run", action="store_true")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
