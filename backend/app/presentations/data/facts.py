"""Data facts (DAT-06): simple facts computed from a finished chart or table.

Week 6 presentation edits (DAT-06): after a chart or table is built, simple facts are computed from its numbers
(total, highest / lowest, share of the top item, average, change first -> last, counts). The slide writer shows
them to the model as citable sources D1, D2 ... so a bullet about the data quotes a number that really is in the data."""

from dataclasses import dataclass
from typing import List

from app.presentations.schemas.slide_content import ChartData, TableData

from . import limits


@dataclass(frozen=True)
class DataFact:
    fact_id: str  # "D1", "D2" ...
    text: str  # one full sentence, with the numbers already formatted


def _fmt(value: float) -> str:
    return f"{int(value):,}" if float(value).is_integer() else f"{value:,.2f}"


def _pct(share: float) -> str:
    return f"{share * 100:.1f}%"


def _numbered(texts: List[str]) -> List[DataFact]:
    return [DataFact(f"D{number}", text) for number, text in enumerate(texts[: limits.MAX_FACTS], start=1)]


def compute_chart_facts(chart: ChartData, aggregation: str = "sum") -> List[DataFact]:
    """Facts about a finished chart. They describe the categories that are SHOWN, not the whole sheet.

    A total or an average is only written when it means something: not for aggregation 'mean' (a sum of averages)."""
    count = len(chart.categories)
    if count == 0:
        return []
    line = chart.chart_type == "line"
    unit, item = ("points", "point") if line else ("categories", "category")
    additive = aggregation != "mean"
    texts = [f"The chart shows {count} {unit}: from {chart.categories[0]} to {chart.categories[-1]}."]
    for series in chart.series[: limits.MAX_FACT_SERIES]:
        name = f"count of {series.name}" if aggregation == "count" else series.name
        values, cats = series.values, chart.categories
        total = sum(values)
        high, low = values.index(max(values)), values.index(min(values))
        if additive:
            texts.append(f"Total {name} across the {count} {unit} shown: {_fmt(total)}.")
            if count > 1:
                texts.append(f"Average {name} per {item}: {_fmt(total / count)}.")
        share = f" ({_pct(values[high] / total)} of the total)" if additive and total > 0 and min(values) >= 0 else ""
        texts.append(f"Highest {name}: {cats[high]} with {_fmt(values[high])}{share}.")
        if count > 1:
            texts.append(f"Lowest {name}: {cats[low]} with {_fmt(values[low])}.")
        if line and count > 1:
            change = values[-1] - values[0]
            percent = f" ({'+' if change >= 0 else '-'}{_pct(abs(change) / abs(values[0]))})" if values[0] else ""
            texts.append(
                f"{name} changed from {_fmt(values[0])} ({cats[0]}) to {_fmt(values[-1])} ({cats[-1]}): "
                f"{'+' if change >= 0 else '-'}{_fmt(abs(change))}{percent}."
            )
    return _numbered(texts)


def compute_table_facts(table: TableData) -> List[DataFact]:
    """Facts about a finished table. They describe the rows that are SHOWN, not the whole sheet."""
    count = len(table.rows)
    if count == 0:
        return []
    texts = [f"The table shows {count} rows and {len(table.columns)} columns: {', '.join(table.columns)}."]

    def is_number(cell) -> bool:
        return isinstance(cell, (int, float)) and not isinstance(cell, bool)

    numeric = [
        index
        for index in range(len(table.columns))
        if any(is_number(row[index]) for row in table.rows)
        and all(is_number(row[index]) for row in table.rows if row[index] is not None)
    ]
    label_column = 0 if 0 not in numeric else None  # a text first column names the rows
    for index in numeric[: limits.MAX_FACT_SERIES]:
        name = table.columns[index]
        found = [(position, row[index]) for position, row in enumerate(table.rows) if row[index] is not None]
        total = sum(value for _, value in found)

        def row_name(position: int) -> str:
            return str(table.rows[position][label_column]) if label_column is not None else f"row {position + 1}"

        high = max(found, key=lambda pair: pair[1])
        low = min(found, key=lambda pair: pair[1])
        texts.append(f"Total {name} of the {len(found)} rows shown: {_fmt(total)}.")
        texts.append(f"Highest {name} in the rows shown: {row_name(high[0])} with {_fmt(high[1])}.")
        if len(found) > 1:
            texts.append(f"Lowest {name} in the rows shown: {row_name(low[0])} with {_fmt(low[1])}.")
    return _numbered(texts)
