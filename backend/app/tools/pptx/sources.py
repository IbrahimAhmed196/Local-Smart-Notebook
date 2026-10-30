from app.schemas.slide_content import SlideContent
from .constants import LABELS


def _sources_lines(slides: list[SlideContent], lang: str = "en") -> list[str]:
    """One line per file: 'report.pdf (pages 2, 3, 4)'."""
    pages: dict[str, set[int]] = {}
    for s in slides:
        for c in s.citations:
            pages.setdefault(c.filename, set())
            if c.page:
                pages[c.filename].add(c.page)
    lines = []
    for name, nums in pages.items():
        if not nums:
            lines.append(name)
        else:
            label = LABELS[lang]["page" if len(nums) == 1 else "pages"]
            lines.append(f"{name} ({label} {', '.join(str(n) for n in sorted(nums))})")
    return lines


def _footer_text(slide: SlideContent, lang: str) -> str:
    """'Sources: report.pdf (pages 2, 7) | sales.csv' for the slide footer."""
    parts = _sources_lines([slide], lang)
    for data in (slide.chart, slide.table):
        if data is not None and data.source:
            parts.append(data.source)
    unique = list(dict.fromkeys(parts))
    if not unique:
        return ""
    line = f"{LABELS[lang]['footer']} " + " | ".join(unique)
    return line if len(line) <= 170 else line[:167] + "..."
