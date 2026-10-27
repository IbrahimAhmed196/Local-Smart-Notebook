"""Chart and table tool: the LLM only names a sheet and columns, pandas computes the values.

Nothing here calls an LLM. The slide writer (agents/slide_content_agent.py) uses it to
  1. describe the notebook's CSV/XLSX files to the LLM (names and column kinds, never the values), and
  2. turn the LLM's ChartSpec / TableSpec into ChartData / TableData read from the real file.
A spec that names a missing file, sheet or column raises ChartToolError, so a wrong guess
becomes a dropped chart, never invented numbers.
"""
import logging
import math
import numbers
import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional, Sequence, Tuple

import pandas as pd
from openpyxl import load_workbook

from app.core.config import settings
from app.core.exceptions import AppError
from app.schemas.slide_content import ChartData, ChartSpec, SeriesData, TableData, TableSpec

log = logging.getLogger(__name__)

EXCEL_EXTENSIONS = (".xlsx", ".xlsm")
DATA_EXTENSIONS = (".csv",) + EXCEL_EXTENSIONS

# Week 6 presentation edits (ARC-07): these limits are set in core/config.py (.env), not here.
MAX_BAR_CATEGORIES = settings.chart_max_bar_categories  # default 12
MAX_PIE_SLICES = settings.chart_max_pie_slices  # default 8
MAX_LINE_POINTS = settings.chart_max_line_points  # default 24
MAX_TABLE_ROWS = settings.table_max_rows  # default 15
MAX_TABLE_COLUMNS = settings.table_max_columns  # default 6

# limits for what is described to the LLM (keeps the prompt small)
CATALOG_MAX_FILES = settings.catalog_max_files  # default 5
CATALOG_MAX_SHEETS = settings.catalog_max_sheets  # default 5
CATALOG_MAX_COLUMNS = settings.catalog_max_columns  # default 15
CATALOG_SAMPLE_ROWS = settings.catalog_sample_rows  # default 50; rows read only to detect the column kinds

# Week 6 presentation edits (DAT-04): how sheets are read.
HEADER_SEARCH_ROWS = 10  # the header must be in the first rows of the sheet
HEADER_MIN_FILL = 0.5  # a header row fills at least this share of the widest row (and 2+ cells)
TEXT_COLUMN_MIN_SHARE = 0.8  # a text column counts as numbers / dates if this share of its cells parse


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


def _read_csv(path: Path) -> pd.DataFrame:
    # sep=None sniffs "," ";" or tab (CSV files saved by Excel in some locales use ";")
    return _clean(pd.read_csv(path, sep=None, engine="python", encoding="utf-8-sig", encoding_errors="replace"))


def _header_row(raw: pd.DataFrame) -> int:
    """Position of the header row. A title above the table fills 1 cell; the header fills most."""
    filled = raw.head(HEADER_SEARCH_ROWS).notna().sum(axis=1).tolist()
    widest = max(filled, default=0)
    needed = max(min(2, widest), math.ceil(widest * HEADER_MIN_FILL))  # a lone title cell is not a header
    return next((i for i, count in enumerate(filled) if widest and count >= needed), 0)


def _tidy_sheet(raw: pd.DataFrame) -> pd.DataFrame:
    """A sheet read with header=None -> a frame with the real header row as its columns."""
    raw = raw.dropna(axis=0, how="all").dropna(axis=1, how="all")
    if raw.empty:
        return raw
    position = _header_row(raw)
    names, seen = [], {}
    for value in raw.iloc[position]:
        name = "" if pd.isna(value) else _label(value).strip()
        seen[name] = seen.get(name, 0) + 1
        names.append(name if seen[name] == 1 or not name else f"{name} {seen[name]}")
    frame = raw.iloc[position + 1:].copy()
    frame.columns = names
    frame = frame.loc[:, [bool(n) for n in names]]  # a column without a header name is dropped
    # the header text made every column "object": give numbers and dates their real type back
    return frame.reset_index(drop=True).infer_objects()


# One cache entry per file: {sheet name (None for CSV): DataFrame}. A file is read once per deck
# (generate_presentation_content clears it), not once for the catalog and again for every chart/table.
_SHEET_CACHE: Dict[tuple, Dict[Optional[str], pd.DataFrame]] = {}


def clear_sheet_cache() -> None:
    _SHEET_CACHE.clear()


def _read_sheets(source: DataSource) -> Dict[Optional[str], pd.DataFrame]:
    stat = source.path.stat()
    key = (str(source.path), stat.st_mtime_ns, stat.st_size)  # a changed file is read again
    if key not in _SHEET_CACHE:
        if _is_excel(source.path):
            raw = pd.read_excel(source.path, sheet_name=None, header=None)
            _SHEET_CACHE[key] = {str(name): _tidy_sheet(frame) for name, frame in raw.items()}
        else:
            _SHEET_CACHE[key] = {None: _read_csv(source.path)}
    return _SHEET_CACHE[key]


def _parse_number(value: Any) -> Optional[float]:
    """A number, or a number written as text ('$1,200', '12%', '(5)', '1.234,5'); None otherwise.

    '12%' is 0.12, the same value Excel stores for a percent cell. A lone dot is a decimal point
    ('1.234' is 1.234); a lone comma followed by exactly 3 digits is a thousands separator.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, numbers.Real):
        return float(value) if math.isfinite(value) else None
    if not isinstance(value, str):
        return None
    text = value.strip().translate(str.maketrans("", "", "$€£¥₹ \u00a0"))
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    percent = text.endswith("%")
    text = text.rstrip("%")
    if not re.fullmatch(r"-?\d[\d.,]*", text):
        return None
    if "," in text and "." in text:  # the separator that comes last is the decimal point
        decimal = "," if text.rfind(",") > text.rfind(".") else "."
        text = text.replace("." if decimal == "," else ",", "").replace(decimal, ".")
    elif "," in text:
        text = text.replace(",", "") if re.fullmatch(r"-?\d{1,3}(,\d{3})+", text) else text.replace(",", ".")
    elif text.count(".") > 1:
        text = text.replace(".", "")
    try:
        number = float(text)
    except ValueError:
        return None
    number = -number if negative else number
    return number / 100 if percent else number


def _as_numbers(series: pd.Series) -> pd.Series:
    """The column as floats; text such as '$1,200' is converted, anything else becomes NaN."""
    return series.map(_parse_number).astype(float)


def _is_mostly(values: pd.Series, test) -> bool:
    return bool(len(values)) and sum(1 for v in values if test(v)) / len(values) >= TEXT_COLUMN_MIN_SHARE


def _kind(series: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(series):
        return "text"
    if pd.api.types.is_numeric_dtype(series):
        return "number"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "date"
    values = series.dropna().head(CATALOG_SAMPLE_ROWS)
    if _is_mostly(values, lambda v: _parse_number(v) is not None):
        return "number"
    # text dates: only strings with a digit are tried, so 'North' or 'May' are never dates
    texts = values.astype(str)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        parsed = pd.to_datetime(texts, errors="coerce", format="mixed")
    if len(texts) and (parsed.notna() & texts.str.contains(r"\d")).mean() >= TEXT_COLUMN_MIN_SHARE:
        return "date"
    return "text"


def _uncalculated_formulas(path: Path, sheet: str) -> int:
    """Formulas in the sheet that have no saved result (the file was never opened and saved in Excel)."""
    try:
        formulas = load_workbook(path, read_only=True, data_only=False)
        values = load_workbook(path, read_only=True, data_only=True)
        try:
            rows = zip(formulas[sheet].iter_rows(values_only=True), values[sheet].iter_rows(values_only=True))
            return sum(
                1
                for formula_row, value_row in rows
                for f, v in zip(formula_row, value_row)
                if isinstance(f, str) and f.startswith("=") and v is None
            )
        finally:
            formulas.close()
            values.close()
    except Exception:
        return 0


def _formula_hint(loaded: "LoadedSheet", source: DataSource) -> str:
    if loaded.sheet is None or not _is_excel(source.path):
        return ""
    if not _uncalculated_formulas(source.path, loaded.sheet):
        return ""
    log.warning("%s has formulas without a saved result", loaded.label)
    return " The sheet has formulas that were never calculated: open the file in Excel, save it, and upload it again."


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
            sheets = [
                _sheet_catalog(name, frame.head(CATALOG_SAMPLE_ROWS))
                for name, frame in list(_read_sheets(source).items())[:CATALOG_MAX_SHEETS]
            ]
        except Exception:
            log.exception("Could not read %s for the slide data catalog", source.filename)
            continue
        sheets = [s for s in sheets if s.columns]
        if sheets:
            catalog.append(SourceCatalog(source.document_id, source.filename, sheets))
    return catalog


def _sheet_catalog(name: Optional[str], frame: pd.DataFrame) -> SheetCatalog:
    columns = [(c, _kind(frame[c])) for c in frame.columns[:CATALOG_MAX_COLUMNS]]
    return SheetCatalog(name=name, columns=columns)


def _find_source(sources: Sequence[DataSource], document_id: int) -> DataSource:
    for source in sources:
        if source.document_id == document_id:
            return source
    known = ", ".join(str(s.document_id) for s in sources) or "none"
    raise ChartToolError(f"document_id {document_id} is not a spreadsheet of this notebook (known: {known}).")


class LoadedSheet(NamedTuple):
    frame: pd.DataFrame
    label: str  # such as 'sales.xlsx / Q1'
    sheet: Optional[str]  # None for a CSV file


def _load_frame(source: DataSource, sheet: Optional[str]) -> LoadedSheet:
    """The whole sheet as a DataFrame (read once, see _read_sheets) with a label for the slide."""
    try:
        sheets = _read_sheets(source)
    except Exception as exc:
        raise ChartToolError(f"Could not read {source.filename}: {exc}") from exc
    if not _is_excel(source.path):
        return LoadedSheet(sheets[None], source.filename, None)
    names = list(sheets)
    if sheet is None or not str(sheet).strip():
        chosen = names[0]
    else:
        by_name = {n.strip().casefold(): n for n in names}
        chosen = by_name.get(str(sheet).strip().casefold())
        if chosen is None:
            raise ChartToolError(f"Sheet '{sheet}' not found in {source.filename} (sheets: {', '.join(names)}).")
    return LoadedSheet(sheets[chosen], f"{source.filename} / {chosen}", chosen)


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
    loaded = _load_frame(source, spec.sheet)
    frame, label = loaded.frame, loaded.label

    x_column = _column(frame, spec.x_column)
    y_columns = [c for c in _unique([_column(frame, c) for c in spec.y_columns]) if c != x_column]
    if not y_columns:
        raise ChartToolError("A chart needs at least one value column besides the x column.")
    if spec.chart_type == "pie":
        y_columns = y_columns[:1]

    data = frame[[x_column, *y_columns]].dropna(subset=[x_column]).copy()
    if spec.aggregation != "count":
        for column in y_columns:
            data[column] = _as_numbers(data[column])  # '$1,200' and '12%' count as numbers
            if data[column].notna().sum() == 0:
                raise ChartToolError(
                    f"Column '{column}' has no numbers, so it cannot be charted." + _formula_hint(loaded, source)
                )

    if spec.aggregation == "none":
        values = data.set_index(x_column)[y_columns]
    else:
        values = data.groupby(x_column, sort=False)[y_columns].agg(spec.aggregation)
    values = values.dropna()  # never replace a missing number with a made-up 0
    if values.empty:
        raise ChartToolError("No rows left to chart after removing empty cells." + _formula_hint(loaded, source))

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
    loaded = _load_frame(source, spec.sheet)
    frame, label = loaded.frame, loaded.label

    columns = _unique([_column(frame, c) for c in spec.columns])[:MAX_TABLE_COLUMNS]
    if not columns:
        raise ChartToolError("A table needs at least one column.")
    row_count = max(1, min(spec.max_rows, MAX_TABLE_ROWS))
    data = frame[columns].dropna(how="all").head(row_count)
    if data.empty:
        raise ChartToolError("The chosen columns have no data." + _formula_hint(loaded, source))
    for column in columns:  # an empty column can be the result of formulas that were never calculated
        if data[column].isna().all() and (hint := _formula_hint(loaded, source)):
            raise ChartToolError(f"Column '{column}' is empty." + hint)

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
