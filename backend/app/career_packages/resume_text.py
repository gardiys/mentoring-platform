from __future__ import annotations

import re
import tempfile
from html import unescape
from pathlib import Path
from zipfile import BadZipFile, ZipFile

import anyio
from pypdf import PdfReader

from app.career_packages.models import CareerResumeVersion
from app.interviews.uploads import InterviewStorageReadError, InterviewUploadStore, StoredUpload

MAX_RESUME_PAGES = 100
MAX_RESUME_TEXT_CHARACTERS = 200_000
SUPPORTED_RESUME_CONTENT_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/markdown",
}


class ResumeTextExtractionError(RuntimeError):
    pass


def resume_file_can_be_extracted(resume: CareerResumeVersion) -> bool:
    return bool(
        resume.storage_key
        and resume.filename
        and resume.content_type in SUPPORTED_RESUME_CONTENT_TYPES
        and resume.size
        and resume.size > 0
    )


def _clean_text(value: str) -> str:
    value = value.replace("\x00", " ")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()[:MAX_RESUME_TEXT_CHARACTERS]


def _extract_pdf(path: Path) -> str:
    reader = PdfReader(path)
    if reader.is_encrypted:
        try:
            if reader.decrypt("") == 0:
                raise ResumeTextExtractionError("Password-protected PDF is not supported")
        except Exception as error:
            raise ResumeTextExtractionError("Password-protected PDF is not supported") from error
    if len(reader.pages) > MAX_RESUME_PAGES:
        raise ResumeTextExtractionError("Resume PDF has too many pages")
    return "\n\n".join((page.extract_text() or "") for page in reader.pages)


def _extract_docx(path: Path) -> str:
    try:
        with ZipFile(path) as archive:
            raw = archive.read("word/document.xml").decode("utf-8", errors="replace")
    except (BadZipFile, KeyError) as error:
        raise ResumeTextExtractionError("Resume DOCX is damaged or unsupported") from error
    raw = re.sub(r"</w:(?:p|tr)>", "\n", raw)
    raw = re.sub(r"<w:tab[^>]*/>", "\t", raw)
    return unescape(re.sub(r"<[^>]+>", "", raw))


def _extract_path(path: Path, content_type: str) -> str:
    try:
        if content_type == "application/pdf":
            text = _extract_pdf(path)
        elif content_type == (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ):
            text = _extract_docx(path)
        elif content_type in {"text/plain", "text/markdown"}:
            text = path.read_text(encoding="utf-8", errors="replace")
        else:
            raise ResumeTextExtractionError("Resume file type is not supported for AI generation")
    except ResumeTextExtractionError:
        raise
    except Exception as error:
        raise ResumeTextExtractionError("Could not read text from the resume file") from error
    text = _clean_text(text)
    if not text:
        raise ResumeTextExtractionError(
            "The resume does not contain readable text; upload a searchable PDF/DOCX or add text"
        )
    return text


async def resume_text_for_ai(
    resume: CareerResumeVersion,
    store: InterviewUploadStore,
) -> str:
    inline = _clean_text(resume.text_content or "")
    if inline:
        return inline
    if not resume_file_can_be_extracted(resume):
        raise ResumeTextExtractionError(
            "Upload a searchable PDF, DOCX or text resume before AI generation"
        )
    assert resume.storage_key and resume.filename and resume.content_type and resume.size
    suffix = Path(resume.filename).suffix[:20]
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix="career-resume-", suffix=suffix, delete=False
        ) as file:
            temp_path = Path(file.name)
        upload = StoredUpload(
            storage_key=resume.storage_key,
            filename=resume.filename,
            content_type=resume.content_type,
            size=resume.size,
        )
        await store.download_to_path(upload, temp_path)
        if temp_path.stat().st_size != resume.size:
            raise ResumeTextExtractionError("Resume file size does not match stored metadata")
        return await anyio.to_thread.run_sync(_extract_path, temp_path, resume.content_type)
    except InterviewStorageReadError as error:
        raise ResumeTextExtractionError("Could not download the resume file") from error
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
