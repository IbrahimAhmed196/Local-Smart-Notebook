"""Table specs -> TableData: the cells are read from the real file, and every problem found is listed (see chart_builder)."""

from typing import List, Sequence

from pydantic import ValidationError

from app.presentations.schemas.slide_content import TableData, TableSpec

from . import limits
from .cleaning import _cell
from .models import CheckResult, DataSource, Issue, SlideDataError
from .reader import _column, _find_source, _formula_hint, _load_frame, _unique


def check_table(spec: TableSpec, sources: Sequence[DataSource]) -> CheckResult:
    """Read the table's cells from the real file and list every problem found."""
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
        requested = _unique([_column(frame, c) for c in spec.columns])
    except SlideDataError as exc:
        return CheckResult(None, [exc.issue])

    columns = requested[: limits.MAX_TABLE_COLUMNS]
    if not columns:
        return fail("no_columns", "A table needs at least one column.", "Choose the columns to show.")
    if len(requested) > limits.MAX_TABLE_COLUMNS:
        warn(
            "columns_truncated",
            f"The table has {len(requested)} columns; only the first {limits.MAX_TABLE_COLUMNS} are shown.",
            "Choose fewer columns.",
        )
    if spec.max_rows > limits.MAX_TABLE_ROWS:
        warn(
            "rows_truncated",
            f"{spec.max_rows} rows were requested; only {limits.MAX_TABLE_ROWS} fit on a slide.",
            "Ask for fewer rows.",
        )
    row_count = max(1, min(spec.max_rows, limits.MAX_TABLE_ROWS))
    data = frame[columns].dropna(how="all").head(row_count)
    if data.empty:
        return fail(
            "no_data",
            "The chosen columns have no data." + _formula_hint(loaded, source),
            "Choose columns that hold values.",
        )
    for column in columns:  # an empty column can be the result of formulas that were never calculated
        if data[column].isna().all():
            if hint := _formula_hint(loaded, source):
                return fail("formulas_not_calculated", f"Column '{column}' is empty." + hint)
            warn("empty_column", f"Column '{column}' is empty in the rows shown.", "Choose a column that has values.")

    rows = [[_cell(v) for v in row] for row in data.itertuples(index=False, name=None)]
    long_cells = sum(1 for row in rows for cell in row if isinstance(cell, str) and len(cell) > limits.MAX_CELL_CHARS)
    if long_cells:
        warn(
            "long_cells",
            f"{long_cells} cell(s) are longer than {limits.MAX_CELL_CHARS} characters and may not fit on the slide.",
            "Choose shorter columns.",
        )
    try:
        table = TableData(title=spec.title.strip() or label, columns=columns, rows=rows, source=label)
    except ValidationError as exc:
        return fail(
            "invalid_table_data", f"The table data is not valid: {exc.errors()[0]['msg']}", "Check the column names."
        )
    return CheckResult(table, issues)


def build_table_data(spec: TableSpec, sources: Sequence[DataSource]) -> TableData:
    """Read the table's cells from the real file (raises SlideDataError on an error)."""
    return check_table(spec, sources).unwrap()
