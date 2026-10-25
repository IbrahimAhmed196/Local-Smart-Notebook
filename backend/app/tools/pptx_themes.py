"""Colours and fonts for the generated presentations."""
 
from dataclasses import dataclass
 
 
@dataclass(frozen=True)
class Theme:
    name: str
    background: str  # content slides
    title_background: str  # title slide
    title_text: str  # text on the title slide
    heading: str  # slide titles
    text: str  # body text
    muted: str  # footers, sources
    primary: str  # bars, table header
    accent: str
    accent2: str
    card: str  # card / panel background
    font_heading: str
    font_body: str
    palette: tuple[str, ...]  # chart colours
 
 
THEMES: dict[str, Theme] = {
    "classic": Theme(
        name="classic",
        background="FFFFFF",
        title_background="1F3A68",
        title_text="FFFFFF",
        heading="1F3A68",
        text="222B38",
        muted="6B7685",
        primary="1F3A68",
        accent="2F6FDE",
        accent2="E08A00",
        card="EEF3FB",
        font_heading="Calibri",
        font_body="Calibri",
        palette=("1F3A68", "2F6FDE", "E08A00", "2E9E5B", "8A5CC2"),
    ),
    "modern": Theme(
        name="modern",
        background="14171F",
        title_background="0B0D12",
        title_text="FFFFFF",
        heading="FFFFFF",
        text="E3E7EF",
        muted="8D96A8",
        primary="22C1B7",
        accent="22C1B7",
        accent2="FF7A59",
        card="1F2430",
        font_heading="Calibri",
        font_body="Calibri",
        palette=("22C1B7", "FF7A59", "7C8CFF", "F5C451", "B084F5"),
    ),
    "warm": Theme(
        name="warm",
        background="FFF9F2",
        title_background="7A2E1D",
        title_text="FFF9F2",
        heading="7A2E1D",
        text="3A2A24",
        muted="8C7468",
        primary="B5472B",
        accent="D9822B",
        accent2="3E7C6B",
        card="FBEBDD",
        font_heading="Georgia",
        font_body="Calibri",
        palette=("B5472B", "D9822B", "3E7C6B", "6D5A9E", "C9A227"),
    ),
}
 
 
def get_theme(name: str) -> Theme:
    try:
        return THEMES[name]
    except KeyError:
        raise ValueError(f"Unknown theme '{name}'. Available: {', '.join(THEMES)}")
