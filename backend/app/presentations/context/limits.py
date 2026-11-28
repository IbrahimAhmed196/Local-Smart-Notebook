"""Size limits of the temporary LLM extractor (CTX-03).
 
The extractor sends a whole document to the model in one call, so a document must fit the model's context window
(presentation_num_ctx tokens) together with the prompt and the answer. Ollama cuts silently when it does not
fit, which would lose facts without any error, so the limit is checked here, before any model call.
"""
 
from __future__ import annotations
 
from collections.abc import Sequence
 
from app.presentations.context.budget import char_limit
from app.presentations.context.errors import ContextTooLargeError
from app.presentations.context.readers import DocumentText
from app.presentations.context.schemas import ContextOptions
 
 
def check_document_count(count: int, options: ContextOptions) -> None:
    if count > options.max_documents:
        raise ContextTooLargeError(
            f"{count} text documents are selected and the limit is {options.max_documents}. "
            "Select fewer documents, or wait for the retrieval feature that handles large collections."
        )
 
 
def check_sizes(texts: Sequence[DocumentText], options: ContextOptions) -> None:
    """Fail fast, naming every document that is too big, so that the user can fix all of them at once."""
    problems = []
    for text in texts:
        if text.status == "too_large":
            problems.append(text.warnings[0].replace(" was not used: ", ": "))
        elif text.status == "used":
            limit, why = char_limit(text, options)
            if text.chars > limit:
                problems.append(f"'{text.filename}': {text.chars:,} characters; the limit is {limit:,}{why}.")
    if problems:
        raise ContextTooLargeError(
            "These documents are too large for the context step: "
            + " ".join(problems)
            + " Use shorter documents or select fewer pages. Nothing was cut."
        )
