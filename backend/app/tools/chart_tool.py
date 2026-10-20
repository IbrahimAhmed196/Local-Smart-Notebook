"""Chart and table tool: the LLM only names a sheet and columns, pandas computes the values.

Nothing here calls an LLM. The slide writer (agents/slide_content_agent.py) uses it to
  1. describe the notebook's CSV/XLSX files to the LLM (names and column kinds, never the values), and
  2. turn the LLM's ChartSpec / TableSpec into ChartData / TableData read from the real file.
A spec that names a missing file, sheet or column raises ChartToolError, so a wrong guess
becomes a dropped chart, never invented numbers.
"""
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple

import pandas as pd

from app.core.exceptions import AppError
from app.schemas.slide_content import ChartData, ChartSpec, SeriesData, TableData, TableSpec

log = logging.getLogger(__name__)

EXCEL_EXTENSIONS = (".xlsx", ".xlsm")
DATA_EXTENSIONS = (".csv",) + EXCEL_EXTENSIONS

MAX_BAR_CATEGORIES = 12
MAX_PIE_SLICES = 8
MAX_LINE_POINTS = 24
MAX_TABLE_ROWS = 15
MAX_TABLE_COLUMNS = 6

# limits for what is described to the LLM (keeps the prompt small)
CATALOG_MAX_FILES = 5
CATALOG_MAX_SHEETS = 5
CATALOG_MAX_COLUMNS = 15
CATALOG_SAMPLE_ROWS = 50  # rows read only to detect the column kinds


class ChartToolError(ValueError):
    """The spec does not match the real file (unknown file / sheet / column, no numbers ...)."""


@dataclass(frozen=True)
class DataSource:
    """A spreadsheet the notebook owns: where it is on disk and which document it is."""
    document_id: int
    filename: str
    path: Path


@dataclass(frozen=True)
class SheetCatalog:
    name: Optional[str]  # None for a CSV file
    columns: List[Tuple[str, str]]  # (column name, "number" | "date" | "text")


@dataclass(frozen=True)
class SourceCatalog:
    document_id: int
    filename: str
    sheets: List[SheetCatalog] = field(default_factory=list)


# ---------------------------------------------------------------------------
# reading the files
# ---------------------------------------------------------------------------

def _is_excel(path: Path) -> bool:
    return path.suffix.lower() in EXCEL_EXTENSIONS


def _clean(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.dropna(axis=0, how="all").dropna(axis=1, how="all")
    frame.columns = [str(c).strip() for c in frame.columns]
    return frame.loc[:, [not c.startswith("Unnamed:") for c in frame.columns]]


def _read_csv(path: Path, nrows: Optional[int] = None) -> pd.DataFrame:
    # sep=None sniffs "," ";" or tab (CSV files saved by Excel in some locales use ";")
    return pd.read_csv(path, sep=None, engine="python", encoding="utf-8-sig",
                       encoding_errors="replace", nrows=nrows)


def _sheet_names(path: Path) -> List[str]:
    with pd.ExcelFile(path) as workbook:
        return [str(name) for name in workbook.sheet_names]


def _read_excel(path: Path, sheet: str, nrows: Optional[int] = None) -> pd.DataFrame:
    return pd.read_excel(path, sheet_name=sheet, nrows=nrows)


def _kind(series: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(series):
        return "text"
    if pd.api.types.is_numeric_dtype(series):
        return "number"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "date"
    return "text"


def describe_sources(sources: Sequence[DataSource]) -> List[SourceCatalog]:
    """Names and column kinds of the CSV/XLSX files: what the LLM may choose from.

    The cell values are never included, so the LLM has no numbers it could copy or invent.
    A file that cannot be read is skipped (and logged); it must not stop the whole deck.
    """
    catalog: List[SourceCatalog] = []
    for source in list(sources)[:CATALOG_MAX_FILES]:
        if source.path.suffix.lower() not in DATA_EXTENSIONS:
            continue
        try:
            if _is_excel(source.path):
                sheets = [
                    _sheet_catalog(name, _read_excel(source.path, name, CATALOG_SAMPLE_ROWS))
                    for name in _sheet_names(source.path)[:CATALOG_MAX_SHEETS]
                ]
            else:
                sheets = [_sheet_catalog(None, _read_csv(source.path, CATALOG_SAMPLE_ROWS))]
        except Exception:
            log.exception("Could not read %s for the slide data catalog", source.filename)
            continue
        sheets = [s for s in sheets if s.columns]
        if sheets:
            catalog.append(SourceCatalog(source.document_id, source.filename, sheets))
    return catalog


def _sheet_catalog(name: Optional[str], frame: pd.DataFrame) -> SheetCatalog:
    frame = _clean(frame)
    columns = [(c, _kind(frame[c])) for c in frame.columns[:CATALOG_MAX_COLUMNS]]
    return SheetCatalog(name=name, columns=columns)


def _find_source(sources: Sequence[DataSource], document_id: int) -> DataSource:
    for source in sources:
        if source.document_id == document_id:
            return source
    known = ", ".join(str(s.document_id) for s in sources) or "none"
    raise ChartToolError(f"document_id {document_id} is not a spreadsheet of this notebook (known: {known}).")


def _load_frame(source: DataSource, sheet: Optional[str]) -> Tuple[pd.DataFrame, str]:
    """The whole sheet as a DataFrame, plus a label such as 'sales.xlsx / Q1'."""
    try:
        if _is_excel(source.path):
            names = _sheet_names(source.path)
            if sheet is None or not str(sheet).strip():
                chosen = names[0]
            else:
                by_name = {n.strip().casefold(): n for n in names}
                chosen = by_name.get(str(sheet).strip().casefold())
                if chosen is None:
                    raise ChartToolError(f"Sheet '{sheet}' not found in {source.filename} (sheets: {', '.join(names)}).")
            return _clean(_read_excel(source.path, chosen)), f"{source.filename} / {chosen}"
        return _clean(_read_csv(source.path)), source.filename
    except ChartToolError:
        raise
    except Exception as exc:
        raise ChartToolError(f"Could not read {source.filename}: {exc}") from exc


def _column(frame: pd.DataFrame, name: str) -> str:
    """The real column name (the LLM may differ in case or spaces)."""
    if name in frame.columns:
        return name
    folded = {str(c).strip().casefold(): c for c in frame.columns}
    found = folded.get(str(name).strip().casefold())
    if found is None:
        raise ChartToolError(f"Column '{name}' not found (columns: {', '.join(map(str, frame.columns))}).")
    return found


def _unique(items: Sequence[str]) -> List[str]:
    return list(dict.fromkeys(items))


# ---------------------------------------------------------------------------
# turning values into JSON-safe text / numbers
# ---------------------------------------------------------------------------

def _label(value: Any) -> str:
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat() if value == value.normalize() else value.isoformat(sep=" ")
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _cell(value: Any) -> Any:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return _label(value)
    if isinstance(value, bool):
        return str(value)
    if hasattr(value, "item"):  # numpy scalar -> plain Python
        value = value.item()
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else round(value, 4)
    return str(value)


# ---------------------------------------------------------------------------
# the two tools
# ---------------------------------------------------------------------------

def build_chart_data(spec: ChartSpec, sources: Sequence[DataSource]) -> ChartData:
    """Compute the chart's categories and values from the real file."""
    source = _find_source(sources, spec.document_id)
    frame, label = _load_frame(source, spec.sheet)

    x_column = _column(frame, spec.x_column)
    y_columns = [c for c in _unique([_column(frame, c) for c in spec.y_columns]) if c != x_column]
    if not y_columns:
        raise ChartToolError("A chart needs at least one value column besides the x column.")
    if spec.chart_type == "pie":
        y_columns = y_columns[:1]

    data = frame[[x_column, *y_columns]].dropna(subset=[x_column]).copy()
    if spec.aggregation != "count":
        for column in y_columns:
            data[column] = pd.to_numeric(data[column], errors="coerce")
            if data[column].notna().sum() == 0:
                raise ChartToolError(f"Column '{column}' has no numbers, so it cannot be charted.")

    if spec.aggregation == "none":
        values = data.set_index(x_column)[y_columns]
    else:
        values = data.groupby(x_column, sort=False)[y_columns].agg(spec.aggregation)
    values = values.dropna()  # never replace a missing number with a made-up 0
    if values.empty:
        raise ChartToolError("No rows left to chart after removing empty cells.")

    if spec.chart_type == "line":
        values = values.head(MAX_LINE_POINTS)
    else:
        limit = MAX_PIE_SLICES if spec.chart_type == "pie" else MAX_BAR_CATEGORIES
        if len(values) > limit:  # keep the biggest categories
            values = values.sort_values(y_columns[0], ascending=False).head(limit)
    if spec.chart_type == "pie" and (values[y_columns[0]] < 0).any():
        raise ChartToolError("A pie chart cannot show negative values.")

    return ChartData(
        chart_type=spec.chart_type,
        title=spec.title.strip() or label,
        categories=[_label(v) for v in values.index],
        series=[SeriesData(name=c, values=[round(float(v), 4) for v in values[c]]) for c in y_columns],
        source=label,
    )


def build_table_data(spec: TableSpec, sources: Sequence[DataSource]) -> TableData:
    """Read the table's cells from the real file."""
    source = _find_source(sources, spec.document_id)
    frame, label = _load_frame(source, spec.sheet)

    columns = _unique([_column(frame, c) for c in spec.columns])[:MAX_TABLE_COLUMNS]
    if not columns:
        raise ChartToolError("A table needs at least one column.")
    row_count = max(1, min(spec.max_rows, MAX_TABLE_ROWS))
    data = frame[columns].dropna(how="all").head(row_count)
    if data.empty:
        raise ChartToolError("The chosen columns have no data.")

    return TableData(
        title=spec.title.strip() or label,
        columns=columns,
        rows=[[_cell(v) for v in row] for row in data.itertuples(index=False, name=None)],
        source=label,
    )


def sources_from_documents(documents: Sequence[Any]) -> List[DataSource]:
    """The CSV/XLSX Document rows of a notebook -> DataSource list (for Task 3's service)."""
    from app.services import document_service  # imported here so this tool works without the DB layer

    sources: List[DataSource] = []
    for doc in documents:
        if doc.file_type not in ("csv", "xlsx"):
            continue
        try:
            path = document_service.get_file_path(doc)
        except AppError:
            log.warning("Document %s has no file on disk; skipped for slide data", doc.id)
            continue
        sources.append(DataSource(document_id=doc.id, filename=doc.filename, path=path))
    return sources
