"""Document lifecycle hooks for the ingestion pipeline."""
import logging

from app.database.models import Document

log = logging.getLogger(__name__)


def on_document_uploaded(document: Document) -> None:
    log.info("Document %s uploaded (ingestion not enabled yet)", document.id)


def on_document_deleted(document: Document) -> None:
    log.info("Document %s deleted (no vectors to remove yet)", document.id)
