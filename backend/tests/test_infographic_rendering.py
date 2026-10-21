import json
import struct
from datetime import date
from pathlib import Path

import pytest

from app.infographic.formatting import format_date, format_metric_value, format_number, format_refs, is_rtl
from app.infographic.rendering import RenderingError, render_html, render_infographic
from app.infographic.schema import InfographicPlan
from app.infographic.view_model import build_view_model, normalize_kind

SAMPLES = Path(__file__).resolve().parents[1] / "app" / "infographic" / "samples"


def load(name: str) -> InfographicPlan:
    return InfographicPlan.model_validate(json.loads((SAMPLES / f"{name}.json").read_text(encoding="utf-8")))


def make_plan(kind="process", items=None, sources=None, **extra) -> InfographicPlan:
    items = items if items is not None else [
        {"id": "a", "title": "A", "description": "", "date": None, "metrics": [], "source_refs": []},
        {"id": "b", "title": "B", "description": "", "date": None, "metrics": [], "source_refs": []},
    ]
    data = {"schema_version": "1.0", "title": "T", "subtitle": "", "type": kind, "summary": "S",
            "items": items, "sources": sources or [], **extra}
    return InfographicPlan.model_validate(data)


def item(id_, title, date_=None, metrics=(), refs=(), desc=""):
    return {"id": id_, "title": title, "description": desc, "date": date_,
            "metrics": [{"name": n, "value": v, "unit": u} for n, v, u in metrics], "source_refs": list(refs)}


# ------------------------------------------------------------------ formatting
def test_number_formatting_never_rounds():
    assert format_number(1234) == "1,234"
    assert format_number(38.0) == "38"
    assert format_number(1234567.891) == "1,234,567.891"
    assert format_number(0.125) == "0.125"


@pytest.mark.parametrize("value,unit,expected", [
    (32, "%", "32%"), (30, "USD", "$30"), (0, "USD", "$0"), (38, "minutes", "38 minutes"),
    (320, "people", "320 people"), ("Low", None, "Low"), (True, None, "Yes"), (False, "x", "No"),
    (None, "kg", "N/A"), (12.5, None, "12.5"), ("high", "USD", "high USD"),
])
def test_metric_value_formatting(value, unit, expected):
    assert format_metric_value(value, unit) == expected


def test_date_formatting_year_only_for_jan_1():
    assert format_date(date(2012, 1, 1)) == "2012"
    assert format_date(date(1997, 5, 11)) == "May 11, 1997"
    assert format_date(None) == ""


def test_rtl_detection():
    assert is_rtl("دورة حياة مشروع تعلم الآلة")
    assert not is_rtl("Machine Learning Lifecycle")
    assert not is_rtl("")
    assert not is_rtl("12345")


def test_format_refs_compresses_runs():
    assert format_refs([1, 2, 3]) == "1–3"
    assert format_refs([1, 4, 7]) == "1, 4, 7"
    assert format_refs([1, 2, 5, 6, 7]) == "1, 2, 5–7"
    assert format_refs([]) == ""


# ------------------------------------------------------------------ view model
def test_kind_normalisation_and_fallback():
    assert normalize_kind(" Timeline ") == "timeline"
    assert normalize_kind("infographic") == "statistics"      # unknown -> statistics layout
    vm = build_view_model(make_plan(kind="Weird Report"))
    assert vm["kind"] == "statistics" and vm["kind_label"] == "Weird Report"


def test_process_rows():
    plan6 = load("process")
    vm = build_view_model(plan6)
    assert vm["cols"] == 3 and [len(r) for r in vm["rows"]] == [3, 3]
    vm4 = build_view_model(make_plan(items=[item(f"i{n}", f"S{n}") for n in range(4)]))
    assert vm4["cols"] == 4 and len(vm4["rows"]) == 1


def test_timeline_sorted_chronologically_and_unknown_dates_last():
    plan = make_plan("timeline", items=[
        item("c", "Late", "2020-01-01"), item("x", "Undated"), item("a", "Early", "1990-03-04"),
    ])
    vm = build_view_model(plan)
    assert [i["title"] for i in vm["entries"]] == ["Early", "Late", "Undated"]
    assert [i["number"] for i in vm["entries"]] == [1, 2, 3]
    assert [i["side"] for i in vm["entries"]] == ["start", "end", "start"]
    assert vm["entries"][2]["date_label"] == ""                # never invented


def test_comparison_matrix_union_and_missing_cells():
    plan = make_plan("comparison", items=[
        item("a", "A", metrics=[("Cost", 10, "USD"), ("Speed", "fast", None)]),
        item("b", "B", metrics=[("cost", 20, "USD")]),         # name matches case-insensitively
    ])
    vm = build_view_model(plan)
    assert vm["matrix"] == [{"name": "Cost", "cells": ["$10", "$20"]},
                            {"name": "Speed", "cells": ["fast", None]}]


def test_comparison_width_grows_with_items_and_is_capped():
    many = make_plan("comparison", items=[item(f"i{n}", f"I{n}") for n in range(12)])
    assert build_view_model(many)["width"] == 2400
    assert build_view_model(load("comparison"))["width"] == 1200


def test_statistics_charts_percent_scale_and_tiles():
    vm = build_view_model(load("statistics"))
    names = [c["name"] for c in vm["charts"]]
    assert names == ["Number of people", "Usage percentage", "Average one-way commute", "Monthly cost"]
    pct = next(c for c in vm["charts"] if c["name"] == "Usage percentage")
    assert pct["bars"][0]["pct"] == 32.0                       # % is drawn against 100, not against the max
    cost = next(c for c in vm["charts"] if c["name"] == "Monthly cost")
    assert max(b["pct"] for b in cost["bars"]) == 100.0
    assert [b["pct"] for b in cost["bars"] if b["display"] == "$0"] == [0.0]
    assert [t["title"] for t in vm["tiles"]] == ["Bus"]        # only the item that has a description


def test_statistics_single_metric_becomes_tile_not_chart():
    plan = make_plan("statistics", items=[
        item("a", "A", metrics=[("Only here", 5, "kg")]),
        item("b", "B", metrics=[("Different", 6, "kg")]),
    ])
    vm = build_view_model(plan)
    assert vm["charts"] == [] and [t["title"] for t in vm["tiles"]] == ["A", "B"]


def test_source_numbering_ignores_unknown_refs():
    plan = make_plan(items=[item("a", "A", refs=["src_2", "src_missing"]), item("b", "B")],
                     sources=[{"id": "src_1", "label": "L", "page": None, "excerpt": "e"},
                              {"id": "src_2", "label": "L", "page": None, "excerpt": "e"}])
    vm = build_view_model(plan)
    assert vm["entries"][0]["refs"] == [2]
    assert vm["source_groups"] == [{"label": "L", "page": None, "numbers": [1, 2], "numbers_label": "1, 2"}]


# ------------------------------------------------------------------ HTML
@pytest.mark.parametrize("name", ["process", "timeline", "comparison", "statistics", "arabic_process", "stress_process"])
def test_every_sample_renders(name):
    plan = load(name)
    html = render_html(plan)
    assert html.startswith("<!DOCTYPE html>") and "</html>" in html
    assert plan.title.split()[0] in html
    assert "<style>" in html and "http" not in html.split("<style>")[0]    # self-contained, no remote assets


def test_html_is_escaped_never_executed():
    evil = "<script>alert(1)</script>"
    plan = make_plan(items=[item("a", evil, desc="<img src=x onerror=alert(1)>"), item("b", "B")], title=evil)
    html = render_html(plan)
    assert "<script>" not in html and "<img src=x" not in html
    assert "&lt;script&gt;" in html


def test_rtl_sets_direction():
    assert 'dir="rtl"' in render_html(load("arabic_process"))
    assert 'dir="ltr"' in render_html(load("process"))


def test_empty_optional_parts_are_omitted():
    html = render_html(make_plan())                            # no subtitle, no sources
    assert 'class="subtitle"' not in html and 'class="sources"' not in html


def test_unsupported_format_rejected():
    with pytest.raises(RenderingError):
        render_infographic(load("process"), "gif")


# ------------------------------------------------------------------ PNG (needs Chromium)
def _chromium_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.chromium.launch().close()
        return True
    except Exception:
        return False


needs_chromium = pytest.mark.skipif(not _chromium_available(), reason="Playwright/Chromium not installed")


@needs_chromium
@pytest.mark.parametrize("name,width", [("process", 1200), ("timeline", 1100), ("statistics", 1200)])
def test_png_export(name, width):
    result = render_infographic(load(name), "png", scale=1)
    png = result.content
    assert result.media_type == "image/png" and png[:8] == b"\x89PNG\r\n\x1a\n"
    w, h = struct.unpack(">II", png[16:24])
    assert w == width and h > 300


@needs_chromium
def test_png_scale_doubles_pixels():
    w1 = struct.unpack(">II", render_infographic(load("process"), "png", 1).content[16:24])[0]
    w2 = struct.unpack(">II", render_infographic(load("process"), "png", 2).content[16:24])[0]
    assert w2 == 2 * w1
