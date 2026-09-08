"""Private desktop releases. Students cannot list or download builds during the pilot."""

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ValidationError

from app.auth.dependencies import require_admin
from app.core.config import get_settings
from app.core.errors import api_error

router = APIRouter(prefix="/copilot", tags=["copilot"], dependencies=[Depends(require_admin)])
AssetId = Literal["mac-arm64", "mac-x64", "win-x64"]
PRIVATE_HEADERS = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}


class Release(BaseModel):
    id: AssetId
    os: Literal["macos", "windows"]
    arch: Literal["arm64", "x64"]
    version: str = Field(min_length=1, max_length=40)
    filename: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]+\.(dmg|exe)$", max_length=180)
    size_bytes: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    signed: bool = False


class ReleaseCatalog(BaseModel):
    releases: list[Release] = Field(default_factory=list, max_length=3)


def release_root() -> Path:
    return get_settings().copilot_releases_dir.resolve()


def release_path(root: Path, release: Release) -> Path | None:
    candidate = (root / release.filename).resolve()
    if not candidate.is_relative_to(root):
        return None
    try:
        if candidate.is_file() and candidate.stat().st_size == release.size_bytes:
            return candidate
    except OSError:
        pass
    return None


def catalog(root: Path) -> ReleaseCatalog:
    try:
        manifest = root / "manifest.json"
        if manifest.stat().st_size > 32_768:
            raise ValueError("Manifest too large")
        result = ReleaseCatalog.model_validate_json(manifest.read_bytes())
        if len({release.id for release in result.releases}) != len(result.releases):
            raise ValueError("Duplicate release IDs")
    except FileNotFoundError:
        return ReleaseCatalog()
    except (OSError, ValueError, ValidationError):
        api_error(503, "copilot_releases_unavailable", "Не удалось прочитать список сборок Copilot")
    return ReleaseCatalog(releases=[r for r in result.releases if release_path(root, r)])


@router.get("/releases", response_model=ReleaseCatalog)
def list_releases(response: Response) -> ReleaseCatalog:
    response.headers.update(PRIVATE_HEADERS)
    return catalog(release_root())


@router.get("/releases/{asset_id}/download", response_class=FileResponse)
def download_release(asset_id: AssetId) -> FileResponse:
    root = release_root()
    release = next((r for r in catalog(root).releases if r.id == asset_id), None)
    path = release_path(root, release) if release else None
    if release is None or path is None:
        api_error(404, "copilot_release_not_found", "Эта сборка пока недоступна для скачивания")
    return FileResponse(
        path,
        filename=release.filename,
        media_type="application/octet-stream",
        headers=PRIVATE_HEADERS,
    )
