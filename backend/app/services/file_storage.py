"""Local file storage:  data/uploads/notebook_<id>/<uuid>.<ext>

Uploads are streamed to data/temporary (size-limited + hashed), validated,
then moved into place. `Document.file_path` stores the path relative to
data/uploads, so the data folder can be moved without breaking records.
"""
import hashlib
import logging
import shutil
import uuid
from pathlib import Path
from typing import BinaryIO

from app.core.config import settings
from app.core.exceptions import PayloadTooLargeError
from app.core.security import safe_join

log = logging.getLogger(__name__)
CHUNK = 1024 * 1024


def ensure_dirs() -> None:
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    settings.temp_dir.mkdir(parents=True, exist_ok=True)


def save_temp(stream: BinaryIO, max_bytes: int) -> tuple[Path, int, str]:
    """Stream to a temp file. Returns (path, size, sha256). Aborts once max_bytes is exceeded."""
    ensure_dirs()
    tmp = settings.temp_dir / f"{uuid.uuid4().hex}.part"
    sha, size = hashlib.sha256(), 0
    try:
        with open(tmp, "wb") as out:
            while chunk := stream.read(CHUNK):
                size += len(chunk)
                if size > max_bytes:
                    raise PayloadTooLargeError(
                        f"File exceeds the maximum allowed size of {settings.max_upload_mb:g} MB."
                    )
                sha.update(chunk)
                out.write(chunk)
    except Exception:
        discard(tmp)
        raise
    return tmp, size, sha.hexdigest()


def commit(tmp: Path, notebook_id: int, ext: str) -> str:
    relative = f"notebook_{notebook_id}/{uuid.uuid4().hex}{ext}"
    dest = safe_join(settings.uploads_dir, relative)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(tmp), str(dest))
    return relative


def discard(tmp: Path) -> None:
    tmp.unlink(missing_ok=True)


def resolve(relative: str) -> Path:
    return safe_join(settings.uploads_dir, relative)


def delete(relative: str) -> None:
    try:
        resolve(relative).unlink(missing_ok=True)
    except OSError:
        log.exception("Could not delete file %s", relative)


def delete_notebook_dir(notebook_id: int) -> None:
    shutil.rmtree(safe_join(settings.uploads_dir, f"notebook_{notebook_id}"), ignore_errors=True)
