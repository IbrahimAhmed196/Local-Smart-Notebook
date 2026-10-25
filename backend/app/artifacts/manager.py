"""Stores generated files under data/artifacts/notebook_<id>/...
 
The database keeps the path RELATIVE to data/artifacts, so the data folder can be moved.
"""
 
import logging
import shutil
from pathlib import Path
 
from app.core.config import settings
from app.core.security import safe_join
 
log = logging.getLogger(__name__)
 
 
def presentation_file(notebook_id: int, presentation_id: int) -> str:
    """Relative path of a presentation file (this is what the database stores)."""
    return f"notebook_{notebook_id}/presentations/presentation_{presentation_id}.pptx"
 
 
def resolve(relative: str) -> Path:
    """Absolute path of a stored file. Refuses paths that leave data/artifacts."""
    return safe_join(settings.artifacts_dir, relative)
 
 
def delete(relative: str) -> None:
    try:
        resolve(relative).unlink(missing_ok=True)
    except OSError:
        log.exception("Could not delete artifact %s", relative)
 
 
def purge_notebook_artifacts(notebook_id: int) -> None:
    """Call AFTER a notebook is deleted: removes all of its generated files."""
    shutil.rmtree(
        safe_join(settings.artifacts_dir, f"notebook_{notebook_id}"), ignore_errors=True
    )
