"""How big a document the extractor accepts, by model and by language (CTX-03).
 
One document goes to the model in one call, so prompt + document + answer must fit the model's context window.
The window is counted in tokens, a document is counted in characters, and the two are linked by how many
characters one token holds. That depends on the language (Arabic needs more tokens per character than English)
and on the model (a 3B model copies quotes badly from a long text, so it gets a smaller share of the window).
 
These numbers are estimates. Measure your own with scripts/measure_context_tokens.py and edit them here.
Setting PRESENTATION_CONTEXT_MAX_CHARS_PER_DOCUMENT in .env overrides all of this with one fixed number.
"""
 
import re
 
from app.presentations.context.readers import DocumentText
from app.presentations.context.schemas import ContextOptions
 
RESERVED_TOKENS = 2600  # fixed prompt + JSON schema (about 800) and the model's answer (about 1,800)
MIN_DOCUMENT_TOKENS = 200
 
_ARABIC_LETTER = re.compile("[\u0600-\u06ff\u0750-\u077f\ufb50-\ufdff\ufe70-\ufeff]")
 
 
def detect_language(text: str) -> str:
    """'ar' when at least 30% of the letters are Arabic, otherwise 'en' (any other Latin-script text)."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return "en"
    arabic = sum(1 for c in letters if _ARABIC_LETTER.match(c))
    return "ar" if arabic / len(letters) >= 0.3 else "en"
 
 
def chars_per_token(language: str) -> float:
    if language == "ar":
        return 2.72  # Arabic: about 2 characters per token (estimate)
    else:
        return 5.2  # English: about 4 in practice, 3.5 keeps a margin
 
 
def document_tokens(model_name: str, num_ctx: int) -> int:
    """How many tokens of the window one document may use."""
    room = num_ctx - RESERVED_TOKENS
    name = model_name.lower()
    if "7b" in name:
        tokens = room  # qwen2.5 7B: the whole free window
    elif "3b" in name:
        tokens = min(room, 3500)  # qwen2.5 3B: follows instructions worse on long text, so a smaller share
    else:
        tokens = min(room, 3000)  # any other model: careful until it has been measured
    return max(tokens, MIN_DOCUMENT_TOKENS)
 
 
def char_limit(text: DocumentText, options: ContextOptions) -> tuple[int, str]:
    """(characters allowed for this document, short reason for the error message)."""
    if options.max_chars_per_document is not None:
        return options.max_chars_per_document, ""
    language = detect_language(" ".join(block.text for block in text.blocks))
    limit = int(document_tokens(options.model_name, options.num_ctx) * chars_per_token(language))
    name = "Arabic" if language == "ar" else "English"
    return limit, f" for {options.model_name} with {name} text"
