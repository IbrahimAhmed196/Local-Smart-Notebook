"""Stage 2: generated outputs (charts, PPTX, reports, infographics)."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from app.artifacts import manager

router = APIRouter(prefix="/artifacts", tags=["Artifacts"])


@router.get("/{path:path}", summary="Serve generated artifact file")
def get_artifact(path: str):
    try:
        file_path = manager.resolve(path)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid artifact path")
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")

    ext = file_path.suffix.lower()
    media_types = {
        ".png": "image/png",
        ".html": "text/html",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".pdf": "application/pdf",
        ".txt": "text/plain",
    }
    media_type = media_types.get(ext, "application/octet-stream")
    return FileResponse(file_path, media_type=media_type)
