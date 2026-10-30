import re
from app.schemas.slide_content import PresentationContent


def detect_rtl(deck: PresentationContent) -> bool:
    """True when most letters in the deck are Arabic or Hebrew."""
    text = " ".join(
        [deck.presentation_title]
        + [s.title for s in deck.slides]
        + [b.text for s in deck.slides for b in s.bullets + s.right_bullets]
    )
    rtl = len(re.findall(r"[\u0590-\u08ff]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    return rtl > latin


def detect_language(deck: PresentationContent) -> str:
    """'ar' when most letters are Arabic (the added labels are then Arabic), else 'en'."""
    text = " ".join([deck.presentation_title] + [s.title for s in deck.slides])
    arabic = len(re.findall(r"[\u0600-\u06ff]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    return "ar" if arabic > latin else "en"
