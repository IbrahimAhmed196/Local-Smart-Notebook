from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned_document
from app.core.config import settings
from app.database.database import get_db
from app.database.models import Document, User
from app.schemas.documents import (
    DocumentListOut,
    DocumentOut,
    DocumentUpdate,
    SupportedTypesOut,
)
from app.services import document_service as service

# Every document endpoint needs a logged-in user (Task 2).
router = APIRouter(
    prefix="/documents",
    tags=["documents"],
    dependencies=[Depends(get_current_user)],
)


@router.post("", response_model=DocumentOut, status_code=201, summary="Upload a document")
def upload_document(
    notebook_id: int = Form(..., description="Notebook that will own the document"),
    file: UploadFile = File(..., description="PDF, DOCX, TXT, CSV or XLSX"),
    description: str | None = Form(None, max_length=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return service.upload_document(db, current_user, notebook_id, file, description)


@router.get("", response_model=DocumentListOut, summary="List my documents")
def list_documents(
    notebook_id: int | None = None,
    file_type: str | None = Query(None, description="pdf, docx, txt, csv, xlsx"),
    status: str | None = Query(
        None, description="UPLOADED, QUEUED, PROCESSING, COMPLETED, FAILED"
    ),
    search: str | None = Query(None, description="Filter by file name"),
    sort_by: str = Query(
        "uploaded_at", pattern="^(uploaded_at|filename|file_size|file_type)$"
    ),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items, total = service.list_documents(
        db,
        current_user,
        notebook_id=notebook_id,
        file_type=file_type,
        status=status,
        search=search,
        sort_by=sort_by,
        order=order,
        limit=limit,
        offset=offset,
    )
    return DocumentListOut(items=items, total=total, limit=limit, offset=offset)


# NOTE: keep this route above /{document_id}, otherwise "supported-types" would be
# read as a document id.
@router.get(
    "/supported-types", response_model=SupportedTypesOut, summary="Allowed types & size limit"
)
def supported_types():
    return SupportedTypesOut(
        extensions=[e.lstrip(".") for e in settings.allowed_extensions],
        max_upload_mb=settings.max_upload_mb,
    )


# The routes below use get_owned_document (Task 2): 404 if the document does not
# exist OR belongs to another user. The path parameter MUST be named document_id.
@router.get("/{document_id}", response_model=DocumentOut, summary="Get document metadata")
def get_document(document: Document = Depends(get_owned_document)):
    return document


@router.patch(
    "/{document_id}", response_model=DocumentOut, summary="Rename / edit description"
)
def update_document(
    body: DocumentUpdate,
    document: Document = Depends(get_owned_document),
    db: Session = Depends(get_db),
):
    return service.update_document(
        db, document, body.filename, body.description, body.model_fields_set
    )


@router.get("/{document_id}/download", summary="Download the original file")
def download_document(document: Document = Depends(get_owned_document)):
    return FileResponse(
        service.get_file_path(document),
        media_type=document.mime_type or "application/octet-stream",
        filename=document.filename,
    )


@router.delete("/{document_id}", status_code=204, summary="Delete a document")
def delete_document(
    document: Document = Depends(get_owned_document), db: Session = Depends(get_db)
):
    service.delete_document(db, document)
    return Response(status_code=204)
