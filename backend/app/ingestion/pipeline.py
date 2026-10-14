"""Ingestion pipeline entry points (Stage 2 fills these in).

Document management calls these at the right moments; they do nothing yet.
Later: `on_document_uploaded` creates a job and runs parse -> OCR -> clean ->
chunk -> embed -> Qdrant (updating Document.status), and `on_document_deleted`
removes the document's vectors from Qdrant.
"""
import logging

from app.database.models import Document

log = logging.getLogger(__name__)


def on_document_uploaded(document: Document) -> None:
    log.info("Document %s uploaded (ingestion not enabled yet)", document.id)


def on_document_deleted(document: Document) -> None:
    log.info("Document %s deleted (no vectors to remove yet)", document.id)
