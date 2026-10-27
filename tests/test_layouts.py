"""Week 6 presentation edits (ARC-06): one layout registry that the schema, prompt, agent and renderer all read."""
import dataclasses

import pytest

from app.agents.slide_content_agent import _normalise_layout, generate_slide_content
from app.llm.prompts import slide_content as prompt_module
from app.llm.prompts.slide_content import LAYOUT_RULES, build_slide_prompt
from app.schemas import layouts
from app.schemas.layouts import (
    DATA_LAYOUTS,
    LAYOUTS,
    SLIDE_LAYOUTS,
    find_layout,
    get_layout,
)
from app.schemas.slide_content import Bullet, SlideContent, SlideContentDraft
from app.schemas.slides import SlideOutlineItem
from app.tools import pptx_tool
from tests.slide_samples import FakeClient, mock_chunks


# ---------------------------------------------------------------- the registry itself

def test_the_registry_defines_the_layouts_the_rest_of_the_app_already_used():
    assert SLIDE_LAYOUTS == ("title", "bullet_points", "two_columns", "chart", "table")
    assert DATA_LAYOUTS == ("chart", "table")
    assert [spec.name for spec in LAYOUTS] == [*SLIDE_LAYOUTS, "closing"]  # 'closing' is renderer-only


def test_a_name_or_alias_used_twice_is_refused(monkeypatch):
    new_alias_clash = layouts.LayoutSpec("timeline", aliases=("bullets",))  # 'bullets' already means bullet_points
    monkeypatch.setattr(layouts, "LAYOUTS", (*LAYOUTS, new_alias_clash))
    with pytest.raises(ValueError, match="'bullets' is used twice"):
        layouts._build_lookup()

    new_name_clash = layouts.LayoutSpec("table")
    monkeypatch.setattr(layouts, "LAYOUTS", (*LAYOUTS, new_name_clash))
    with pytest.raises(ValueError, match="'table' is used twice"):
        layouts._build_lookup()


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("bullet_points", "bullet_points"),
        ("Bullets", "bullet_points"),
        ("two column", "two_columns"),
        ("TWO-COLUMNS", "two_columns"),
        ("comparison", "two_columns"),
        ("Conclusion", "closing"),
        ("chart", "chart"),
    ],
)
def test_names_and_aliases_find_the_layout_whatever_the_spelling(raw, expected):
    assert find_layout(raw).name == expected


@pytest.mark.parametrize("raw", ["timeline", "", None, "  "])
def test_an_unknown_name_finds_nothing(raw):
    assert find_layout(raw) is None


def test_selectable_only_hides_the_renderer_only_layout():
    assert find_layout("closing").name == "closing"
    assert find_layout("closing", selectable_only=True) is None
    assert find_layout("conclusion", selectable_only=True) is None
    assert find_layout("bullets", selectable_only=True).name == "bullet_points"


def test_get_layout_wants_the_exact_name():
    assert get_layout("two_columns").columns == 2
    for bad in ("bullets", "nope"):  # an alias is not a name
        with pytest.raises(KeyError):
            get_layout(bad)


def test_only_chart_and_table_need_a_spreadsheet():
    assert [spec.name for spec in LAYOUTS if spec.needs_data] == ["chart", "table"]
    assert get_layout("chart").required == ("chart",) and get_layout("table").required == ("table",)


# ---------------------------------------------------------------- every layout is wired everywhere

def test_every_layout_has_a_renderer_and_the_renderer_knows_no_other_layout():
    renderers = set(pptx_tool._RENDERERS)
    assert {spec.name for spec in LAYOUTS} <= renderers
    assert renderers - {spec.name for spec in LAYOUTS} == {"sources"}  # the Sources slide is not a layout


def test_every_selectable_layout_has_a_prompt_rule_and_every_rule_belongs_to_a_layout():
    assert set(LAYOUT_RULES) == set(SLIDE_LAYOUTS)


# ---------------------------------------------------------------- the copies can no longer disagree

@pytest.mark.parametrize("raw", ["bullets", "bullet_point", "two_column", "two_cols", "comparison", "Two Columns"])
def test_the_agent_and_the_renderer_resolve_every_alias_the_same_way(raw):
    in_agent, warnings = _normalise_layout(raw)
    slide = SlideContent(slide_number=2, title="T", layout_type=raw)
    in_renderer = pptx_tool._layout_of(slide)
    assert warnings == []
    assert in_agent == find_layout(raw).name
    # the renderer also needs the layout's data; with none it shows a bullet slide, like before
    assert in_renderer == in_agent


def test_comparison_used_to_work_only_in_the_renderer_and_now_works_in_the_agent_too():
    assert _normalise_layout("comparison") == ("two_columns", [])


def test_conclusion_is_a_renderer_look_so_the_agent_still_treats_it_as_unknown():
    layout, warnings = _normalise_layout("conclusion")
    assert layout == "bullet_points" and "Unknown layout 'conclusion'" in warnings[0]
    slide = SlideContent(slide_number=9, title="Wrap up", layout_type="conclusion")
    assert pptx_tool._layout_of(slide) == "closing"


@pytest.mark.parametrize("name", ["chart", "table"])
def test_a_data_layout_without_its_data_is_drawn_as_a_bullet_slide(name):
    slide = SlideContent(slide_number=3, title="Data", layout_type=name)
    assert pptx_tool._layout_of(slide) == "bullet_points"


def test_an_unknown_layout_is_drawn_as_a_bullet_slide():
    assert pptx_tool._layout_of(SlideContent(slide_number=3, title="X", layout_type="timeline")) == "bullet_points"


# ---------------------------------------------------------------- limits: prompt and code use one number

def make_prompt(layout):
    return build_slide_prompt(
        presentation_title="Deck", audience="Team", style=None, slide_number=2, title="T",
        purpose="P", layout=layout, sources={},
    )


@pytest.mark.parametrize("name", SLIDE_LAYOUTS)
def test_the_prompt_asks_for_the_numbers_the_registry_holds(name):
    spec = get_layout(name)
    prompt = make_prompt(name)
    assert f"at most {spec.max_words_per_bullet} words" in prompt
    if spec.max_bullets:
        assert f"{spec.min_bullets} to {spec.max_bullets} " in prompt
    assert "{min}" not in prompt and "{max}" not in prompt  # every placeholder was filled


def test_changing_one_registry_entry_changes_both_the_prompt_and_the_trimming(monkeypatch):
    spec = get_layout("bullet_points")
    monkeypatch.setitem(layouts._LOOKUP, "bullet_points", dataclasses.replace(spec, min_bullets=2, max_bullets=4, max_words_per_bullet=9))
    assert "Write 2 to 4 bullets" in make_prompt("bullet_points") and "at most 9 words" in make_prompt("bullet_points")

    many = SlideContentDraft(bullets=[Bullet(text=f"point {i}", source_ids=["S1"]) for i in range(8)])
    slide = generate_slide_content(
        SlideOutlineItem(slide_number=2, title="T", purpose="P", layout_type="bullet_points"),
        presentation_title="Deck", audience="Team", chunks=mock_chunks(2), client=FakeClient.sequence(many),
    )
    assert len(slide.bullets) == 4


def test_the_prompt_module_keeps_no_layout_table_of_its_own_numbers():
    # the rules are text with {min}/{max} placeholders, never a hand-typed "3 to 5"
    assert "3 to 5" not in " ".join(LAYOUT_RULES.values())
    assert hasattr(prompt_module, "get_layout")
