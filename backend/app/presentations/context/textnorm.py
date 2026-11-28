"""Text folding shared by fact checking (CTX-06) and slide selection (CTX-08).
 
Two texts that a person reads as the same must fold to the same string: PDF extraction changes ligatures, quotes,
spacing and Arabic forms, and models "tidy" them again when they copy a quote.
"""
 
import re
import unicodedata
 
_ARABIC_MARKS = re.compile("[\u064b-\u065f\u0670\u0640]")  # diacritics, dagger alef, tatweel
_INVISIBLE = re.compile("[\u200b-\u200f\u202a-\u202e\u2060\ufeff\u00ad]")  # zero-width, direction marks, soft hyphen
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_PUNCTUATION = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", "‑": "-"})
 
 
def fold(text: str) -> str:
    """NFKC (ligatures, Arabic presentation forms), lower case, no Arabic marks, ASCII digits, plain quotes."""
    text = unicodedata.normalize("NFKC", text or "")
    text = _INVISIBLE.sub("", _ARABIC_MARKS.sub("", text))
    return text.translate(_DIGITS).translate(_PUNCTUATION).casefold()
 
 
def compact(text: str) -> str:
    """fold() without any whitespace: PDF extraction adds and drops spaces, so spacing must not matter."""
    return re.sub(r"\s+", "", fold(text))
