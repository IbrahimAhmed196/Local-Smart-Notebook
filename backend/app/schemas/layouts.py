"""Week 6 presentation edits (ARC-06): the ONE place that knows every slide layout.

Before this file the layouts were described four times (schemas/slide_content.py, the slide agent,
the slide prompt and the renderer) and the copies disagreed: the prompt asked for 3-5 bullets while
the code allowed 6, and the renderer accepted 'closing' / 'comparison' that the agent did not.

Now the schema, the outline, the prompt, the agent and the renderer all read LAYOUTS below.
To add a layout: add one LayoutSpec here, one prompt rule in llm/prompts/slide_content.py and one
render function in tools/pptx_tool.py (tests/test_layouts.py fails if the renderer or the rule is missing).

This file imports nothing from the app, so every layer can import it without a circular import.
"""
from dataclasses import dataclass
from typing import Dict, Optional, Tuple


@dataclass(frozen=True)
class LayoutSpec:
    name: str
    aliases: Tuple[str, ...] = ()  # other spellings the model or the renderer accepts
    min_bullets: int = 0  # per column; asked for in the prompt
    max_bullets: int = 0  # per column; the agent trims to this (0 = the layout has no bullets)
    max_words_per_bullet: int = 18  # asked for in the prompt
    columns: int = 1  # 2 = right_bullets is used as well
    required: Tuple[str, ...] = ()  # SlideContent fields that must be filled, else the slide is a bullet slide
    selectable: bool = True  # False = only the renderer chooses it; the outline and the model never do

    @property
    def needs_data(self) -> bool:
        """True for layouts built from a spreadsheet (they need a chart or a table)."""
        return bool({"chart", "table"} & set(self.required))


LAYOUTS: Tuple[LayoutSpec, ...] = (
    LayoutSpec("title"),
    LayoutSpec(
        "bullet_points",
        aliases=("bullets", "bullet_point", "bullet"),
        min_bullets=3,
        max_bullets=5,
    ),
    LayoutSpec(
        "two_columns",
        aliases=("two_column", "two_cols", "comparison"),
        min_bullets=2,
        max_bullets=4,
        columns=2,
    ),
    LayoutSpec("chart", min_bullets=1, max_bullets=3, required=("chart",)),
    LayoutSpec("table", min_bullets=1, max_bullets=3, required=("table",)),
    # The renderer gives this look to the last text slide; the model is never asked for it.
    LayoutSpec("closing", aliases=("conclusion",), min_bullets=3, max_bullets=5, selectable=False),
)

DEFAULT_LAYOUT = "bullet_points"  # the contract: an unknown layout is a bullet slide

# The layouts the outline and the slide writer may choose (the renderer also knows 'closing').
SLIDE_LAYOUTS: Tuple[str, ...] = tuple(spec.name for spec in LAYOUTS if spec.selectable)
DATA_LAYOUTS: Tuple[str, ...] = tuple(spec.name for spec in LAYOUTS if spec.needs_data)


def _build_lookup() -> Dict[str, LayoutSpec]:
    lookup: Dict[str, LayoutSpec] = {}
    for spec in LAYOUTS:
        for key in (spec.name, *spec.aliases):
            if key in lookup:
                raise ValueError(f"layout name or alias '{key}' is used twice")
            lookup[key] = spec
    return lookup


_LOOKUP = _build_lookup()


def normalise_name(raw: Optional[str]) -> str:
    """'Two Column' / 'TWO-COLUMNS' -> 'two_column' / 'two_columns'."""
    return (raw or "").strip().lower().replace(" ", "_").replace("-", "_")


def find_layout(raw: Optional[str], selectable_only: bool = False) -> Optional[LayoutSpec]:
    """The layout a name or alias stands for, or None when it is unknown.

    selectable_only=True is for the outline and the slide writer: renderer-only layouts count as unknown.
    """
    spec = _LOOKUP.get(normalise_name(raw))
    if spec is not None and selectable_only and not spec.selectable:
        return None
    return spec


def get_layout(name: str) -> LayoutSpec:
    """The layout with this exact (already normalised) name; raises KeyError when there is none."""
    spec = _LOOKUP.get(name)
    if spec is None or spec.name != name:
        raise KeyError(name)
    return spec
