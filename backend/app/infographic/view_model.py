"""Turns a validated InfographicPlan into a plain dict that templates only have to DISPLAY.

All decisions (ordering, grouping, bar widths, column counts, number formatting)
are made here in Python so they can be unit-tested; templates contain layout only.
"""
from collections import OrderedDict
from datetime import date
from typing import Any

from app.infographic.formatting import format_date, format_metric_value, format_refs, is_rtl
from app.infographic.schema import InfographicItem, InfographicPlan

KIND_LABELS = {
    "process": "Process",
    "timeline": "Timeline",
    "comparison": "Comparison",
    "statistics": "Statistics",
}
FALLBACK_KIND = "statistics"        # `type` is a free string in schema.py; unknown values use this layout


def normalize_kind(raw_type: str) -> str:
    key = (raw_type or "").strip().casefold()
    return key if key in KIND_LABELS else FALLBACK_KIND


# ----------------------------------------------------------------------------
def build_view_model(plan: InfographicPlan) -> dict[str, Any]:
    kind = normalize_kind(plan.type)
    numbers = {source.id: n for n, source in enumerate(plan.sources, start=1)}

    rtl = is_rtl(plan.title, plan.subtitle, plan.summary, *(i.title for i in plan.items))
    vm: dict[str, Any] = {
        "kind": kind,
        # Known types get a clean label; an unknown type keeps the model's own wording as the badge.
        "kind_label": KIND_LABELS.get(plan.type.strip().casefold(), plan.type.strip().title()),
        "title": plan.title,
        "subtitle": plan.subtitle,
        "summary": plan.summary,
        "dir": "rtl" if rtl else "ltr",
        "lang": "ar" if rtl else "en",
        "width": 1200,
        "entries": [_make_item(i, item, numbers) for i, item in enumerate(plan.items, start=1)],
        "source_groups": _source_groups(plan),
    }
    {
        "process": _process,
        "timeline": _timeline,
        "comparison": _comparison,
        "statistics": _statistics,
    }[kind](vm)
    return vm


# ---------------------------------------------------------------------------- shared
def _make_item(number: int, item: InfographicItem, numbers: dict[str, int]) -> dict[str, Any]:
    refs = sorted({numbers[r] for r in item.source_refs if r in numbers})
    return {
        "number": number,
        "id": item.id,
        "title": item.title,
        "description": item.description,
        "date": item.date,                                   # kept raw for sorting
        "date_label": format_date(item.date),
        "metrics": [
            {"name": m.name, "unit": m.unit, "value": m.value,
             "display": format_metric_value(m.value, m.unit)}
            for m in item.metrics
        ],
        "refs": refs,
        "refs_label": format_refs(refs),
    }


def _source_groups(plan: InfographicPlan) -> list[dict[str, Any]]:
    """Group sources that share (label, page) so 15 sources don't become 15 footer lines."""
    groups: "OrderedDict[tuple, dict[str, Any]]" = OrderedDict()
    for n, source in enumerate(plan.sources, start=1):
        key = (source.label, source.page)
        group = groups.setdefault(key, {"label": source.label, "page": source.page, "numbers": []})
        group["numbers"].append(n)
    for group in groups.values():
        group["numbers_label"] = format_refs(group["numbers"])
    return list(groups.values())


# ---------------------------------------------------------------------------- process
def _process(vm: dict[str, Any]) -> None:
    """Steps in the given order, laid out in rows (<=4 steps: one row; otherwise 3 per row)."""
    items = vm["entries"]
    cols = max(1, min(len(items), 4 if len(items) <= 4 else 3))
    vm["cols"] = cols
    vm["rows"] = [items[i:i + cols] for i in range(0, len(items), cols)]


# ---------------------------------------------------------------------------- timeline
def _timeline(vm: dict[str, Any]) -> None:
    """Chronological order; items WITHOUT a date go last and are labelled (never guessed)."""
    ordered = sorted(vm["entries"], key=lambda it: (it["date"] is None, it["date"] or date.min))
    for n, item in enumerate(ordered, start=1):
        item["number"] = n
        item["side"] = "start" if n % 2 == 1 else "end"      # alternate left/right
    vm["entries"] = ordered
    vm["width"] = 1100


# ---------------------------------------------------------------------------- comparison
def _comparison(vm: dict[str, Any]) -> None:
    """Matrix: one column per item, one row per metric name (union over all items)."""
    names: "OrderedDict[str, str]" = OrderedDict()
    for item in vm["entries"]:
        for metric in item["metrics"]:
            names.setdefault(metric["name"].casefold(), metric["name"])

    rows = []
    for key, name in names.items():
        cells = []
        for item in vm["entries"]:
            match = next((m for m in item["metrics"] if m["name"].casefold() == key), None)
            cells.append(match["display"] if match else None)     # None -> rendered as "—"
        rows.append({"name": name, "cells": cells})

    vm["matrix"] = rows
    # 112px page padding + 200px label column + 250px per compared item (capped)
    vm["width"] = min(2400, max(1200, 112 + 200 + 250 * len(vm["entries"])))


# ---------------------------------------------------------------------------- statistics
def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _statistics(vm: dict[str, Any]) -> None:
    """Bar charts for every (metric name, unit) that at least two items report as a number;
    tiles for whatever is left (other metrics and item descriptions)."""
    groups: "OrderedDict[tuple, list[dict[str, Any]]]" = OrderedDict()
    for item in vm["entries"]:
        seen: set[tuple] = set()
        for metric in item["metrics"]:
            key = (metric["name"].casefold(), (metric["unit"] or "").strip().casefold())
            if _is_number(metric["value"]) and key not in seen:
                seen.add(key)
                groups.setdefault(key, []).append({"item": item, "metric": metric})

    charts, charted = [], set()
    for key, entries in groups.items():
        if len(entries) < 2:
            continue
        values = [e["metric"]["value"] for e in entries]
        unit = (entries[0]["metric"]["unit"] or "").strip()
        # Percentages are drawn against 100 so 32% doesn't look like "full" just because it's the max.
        denominator = 100.0 if unit == "%" and max(values) <= 100 else float(max(values))
        bars = []
        for e in entries:
            value = float(e["metric"]["value"])
            pct = max(0.0, value) / denominator * 100 if denominator > 0 else 0.0
            if value > 0:
                pct = max(pct, 2.0)                           # keep tiny non-zero values visible
            bars.append({
                "title": e["item"]["title"], "refs_label": e["item"]["refs_label"],
                "display": e["metric"]["display"], "pct": round(min(pct, 100.0), 2),
            })
            charted.add((e["item"]["id"], key))
        charts.append({"name": entries[0]["metric"]["name"], "unit": unit, "bars": bars})

    tiles = []
    for item in vm["entries"]:
        rest = [m for m in item["metrics"]
                if (item["id"], (m["name"].casefold(), (m["unit"] or "").strip().casefold())) not in charted]
        if rest or item["description"]:
            tiles.append({**item, "metrics": rest})

    vm["charts"] = charts
    vm["tiles"] = tiles
