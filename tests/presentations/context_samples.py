"""Helpers for the context tests: scripted model answers and small fake documents."""
 
from pathlib import Path
 
from app.presentations.context.schemas import DocumentExtraction, ExtractedFact
from tests.presentations.doc_samples import fake_document
 
 
def fact(text, evidence=None, page=None, section=None):
    """A fact as the model returns it. By default the evidence is the fact text itself (a real quote)."""
    return ExtractedFact(text=text, evidence=evidence or text, page=page, section=section)
 
 
def extraction(*facts, summary="A short summary."):
    return DocumentExtraction(summary=summary, facts=list(facts))
 
 
def txt_document(tmp_path: Path, doc_id: int, name: str, text: str):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return fake_document(doc_id, path, "txt")
