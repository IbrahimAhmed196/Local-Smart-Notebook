"""Chart specs -> ChartData: pandas computes the categories and values, and every problem found is listed.

Week 6 presentation edits (DAT-02): check_chart returns a CheckResult (data + a list of issues) instead of stopping at
the first problem. Checking and building are ONE pass; build_chart_data keeps the old behaviour (raise SlideDataError on an
error) for callers that do not need the warnings."""

from typing import List, Sequence

import numpy as np
import pandas as pd
from pydantic import ValidationError

from app.presentations.schemas.slide_content import ChartData, ChartSpec, SeriesData

from . import limits
from .cleaning import _as_numbers, _kind, _label
from .models import CheckResult, DataSource, Issue, SlideDataError
from .reader import _column, _find_source, _formula_hint, _load_frame, _unique


def _x_order(index: pd.Index, kind: str) -> np.ndarray:
    """Positions that sort a line chart's x values by date or by number (empty values go last)."""
    if kind == "date":
        keys = pd.to_datetime(pd.Series(index), errors="coerce", format="mixed").to_numpy()
    else:
        keys = _as_numbers(pd.Series(index)).to_numpy()
    return np.argsort(keys, kind="stable")


def check_chart(spec: ChartSpec, sources: Sequence[DataSource]) -> CheckResult:
    """Compute the chart's categories and values from the real file and list every problem found."""
    issues: List[Issue] = []

    def fail(code: str, message: str, hint: str = "") -> CheckResult:
        issues.append(Issue(code, "error", message, hint))
        return CheckResult(None, issues)

    def warn(code: str, message: str, hint: str = "") -> None:
        issues.append(Issue(code, "warning", message, hint))

    try:
        source = _find_source(sources, spec.document_id)
        loaded = _load_frame(source, spec.sheet)
        frame, label = loaded.frame, loaded.label
        x_column = _column(frame, spec.x_column)
        y_columns = [c for c in _unique([_column(frame, c) for c in spec.y_columns]) if c != x_column]
    except SlideDataError as exc:
        return CheckResult(None, [exc.issue])
    if not y_columns:
        return fail(
            "no_value_column",
            "A chart needs at least one value column besides the x column.",
            "Choose a numeric column that is not the x column.",
        )
    if spec.chart_type == "pie" and len(y_columns) > 1:
        warn(
            "pie_extra_series",
            f"A pie chart shows one series, so only '{y_columns[0]}' is used.",
            "Use a bar chart to compare several columns.",
        )
        y_columns = y_columns[:1]
    elif len(y_columns) > limits.MAX_CHART_SERIES:
        warn(
            "too_many_series",
            f"The chart has {len(y_columns)} series; only the first {limits.MAX_CHART_SERIES} are shown.",
            "Split the columns over several charts.",
        )
        y_columns = y_columns[: limits.MAX_CHART_SERIES]

    data = frame[[x_column, *y_columns]].dropna(subset=[x_column]).copy()
    if spec.aggregation != "count":
        for column in y_columns:
            data[column] = _as_numbers(data[column])  # '$1,200' and '12%' count as numbers
            filled = int(data[column].notna().sum())
            if filled == 0:
                return fail(
                    "no_numbers",
                    f"Column '{column}' has no numbers, so it cannot be charted." + _formula_hint(loaded, source),
                    "Choose a column that holds numbers.",
                )
            if filled / len(data) < limits.MOSTLY_EMPTY_SHARE:
                warn(
                    "column_mostly_empty",
                    f"Column '{column}' has numbers in only {filled} of {len(data)} rows; the other rows are left out.",
                    "Check that this is the right column.",
                )

    x_kind = _kind(data[x_column])
    if spec.aggregation == "none" and data[x_column].duplicated().any():
        warn(
            "duplicate_x",
            f"Aggregation is 'none' but {int(data[x_column].duplicated().sum())} x value(s) repeat, so the same category appears more than once.",
            "Use aggregation 'sum' or 'mean' to combine the rows.",
        )
    unique_x = int(data[x_column].nunique())
    if spec.chart_type != "line" and x_kind != "date":
        limit = limits.MAX_PIE_SLICES if spec.chart_type == "pie" else limits.MAX_BAR_CATEGORIES
        if unique_x > limit and unique_x / len(data) >= limits.ID_LIKE_UNIQUE_SHARE:
            warn(
                "x_looks_like_id",
                f"Column '{x_column}' has {unique_x} different values in {len(data)} rows, so it looks like an id, not a category.",
                "Choose a column with fewer, repeated categories.",
            )

    if spec.aggregation == "none":
        values = data.set_index(x_column)[y_columns]
    else:
        values = data.groupby(x_column, sort=False)[y_columns].agg(spec.aggregation)
    values = values.dropna()  # never replace a missing number with a made-up 0
    if values.empty:
        return fail(
            "empty_result",
            "No rows left to chart after removing empty cells." + _formula_hint(loaded, source),
            "Check that the chosen columns contain values.",
        )

    if spec.chart_type == "line":
        if x_kind in ("date", "number"):
            values = values.iloc[_x_order(values.index, x_kind)]  # a line needs its x values in order
        else:
            warn(
                "line_x_not_ordered",
                f"Column '{x_column}' holds text categories, so the line has no natural order.",
                "Use a date or number column for x, or choose a bar chart.",
            )
        if len(values) > limits.MAX_LINE_POINTS:
            warn(
                "points_truncated",
                f"The line has {len(values)} points; only the first {limits.MAX_LINE_POINTS} are shown.",
                "Filter the data to the period you want.",
            )
            values = values.head(limits.MAX_LINE_POINTS)
    else:
        limit = limits.MAX_PIE_SLICES if spec.chart_type == "pie" else limits.MAX_BAR_CATEGORIES
        if spec.chart_type == "pie" and (values[y_columns[0]] < 0).any():  # before cutting: the cut would hide it
            return fail(
                "pie_negative",
                "A pie chart cannot show negative values.",
                "Use a bar chart for values that can be negative.",
            )
        if len(values) > limit:  # keep the biggest categories
            warn(
                "categories_truncated",
                f"There are {len(values)} categories; only the {limit} biggest are shown.",
                "Filter the data or group it into fewer categories.",
            )
            values = values.sort_values(y_columns[0], ascending=False).head(limit)

    if spec.chart_type == "pie":
        if values[y_columns[0]].sum() <= 0:
            return fail(
                "pie_total_zero", "A pie chart needs a total above zero.", "Use a bar chart, or choose another column."
            )
    if spec.chart_type in ("pie", "line") and len(values) < 2:
        part = "slices" if spec.chart_type == "pie" else "points"
        return fail(
            "too_few_points",
            f"A {spec.chart_type} chart needs at least 2 {part}, but only {len(values)} is left.",
            "Choose columns with more rows, or use a bar chart.",
        )

    if len(y_columns) > 1:  # series on very different scales: the small one looks flat
        peaks = {c: float(values[c].abs().max()) for c in y_columns}
        positive = {c: peak for c, peak in peaks.items() if peak > 0}
        if len(positive) > 1:
            big, small = max(positive, key=positive.get), min(positive, key=positive.get)
            ratio = positive[big] / positive[small]
            if ratio >= limits.SCALE_RATIO_WARNING:
                warn(
                    "scale_mismatch",
                    f"'{big}' is about {ratio:.0f} times bigger than '{small}', so '{small}' will look flat.",
                    "Chart them separately.",
                )

    try:
        chart = ChartData(
            chart_type=spec.chart_type,
            title=spec.title.strip() or label,
            categories=[_label(v) for v in values.index],
            series=[SeriesData(name=c, values=[round(float(v), 4) for v in values[c]]) for c in y_columns],
            source=label,
        )
    except ValidationError as exc:  # the DAT-01 checks (for example an empty category name)
        return fail(
            "invalid_chart_data",
            f"The chart data is not valid: {exc.errors()[0]['msg']}",
            "Check the category and series names.",
        )
    return CheckResult(chart, issues)


def build_chart_data(spec: ChartSpec, sources: Sequence[DataSource]) -> ChartData:
    """Compute the chart's categories and values from the real file (raises SlideDataError on an error)."""
    return check_chart(spec, sources).unwrap()
