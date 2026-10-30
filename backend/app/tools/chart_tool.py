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
from typing import Any, Dict, List, NamedTuple, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd
from openpyxl import load_workbook
from pydantic import ValidationError

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

# Week 6 presentation edits (DAT-02): limits of the chart / table checks. The first three are set in core/config.py (.env).
MAX_CHART_SERIES = settings.chart_max_series  # default 4
SCALE_RATIO_WARNING = settings.chart_scale_ratio_warning  # default 100
MAX_CELL_CHARS = settings.table_max_cell_chars  # default 60
MOSTLY_EMPTY_SHARE = 0.5  # a value column with numbers in fewer rows than this share is flagged
ID_LIKE_UNIQUE_SHARE = 0.9  # an x column whose values are this unique (and over the limit) looks like an id

# Week 6 presentation edits (DAT-05): examples shown for a text column (set in core/config.py) and their length.
CATALOG_EXAMPLE_LABELS = settings.catalog_example_labels  # default 5
CATALOG_LABEL_CHARS = 30

# Week 6 presentation edits (DAT-06): at most this many data facts per slide (keeps the prompt short).
MAX_FACTS = 10
MAX_FACT_SERIES = 2  # facts are written for the first two series of a chart


@dataclass(frozen=True)
class Issue:
    """Week 6 presentation edits (DAT-02): one problem found in a chart or table spec."""
    code: str  # short machine name, such as 'pie_negative'
    severity: str  # "error" = the chart / table cannot be drawn; "warning" = drawn, but the reader should know
    message: str
    hint: str = ""  # what to change


class ChartToolError(ValueError):
    """The spec does not match the real file (unknown file / sheet / column, no numbers ...).

    str(error) is the message, as before; DAT-02 adds the code and the hint (see Issue)."""

    def __init__(self, message: str, code: str = "chart_error", hint: str = ""):
        super().__init__(message)
        self.code = code
        self.hint = hint

    @property
    def issue(self) -> Issue:
        return Issue(self.code, "error", str(self), self.hint)


@dataclass
class CheckResult:
    """Week 6 presentation edits (DAT-02): what check_chart / check_table return instead of raising.

    data is None when there is an error. Warnings never stop the chart; the slide writer adds them to the
    slide's warnings. The errors are what GEN-06 can feed back to the model."""
    data: Optional[Union[ChartData, TableData]]
    issues: List[Issue] = field(default_factory=list)

    @property
    def errors(self) -> List[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> List[Issue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass(frozen=True)
class DataSource:
    """A spreadsheet the notebook owns: where it is on disk and which document it is."""
    document_id: int
    filename: str
    path: Path


@dataclass(frozen=True)
class ColumnProfile:
    """Week 6 presentation edits (DAT-05): what a column looks like, never a sum or an average."""
    distinct: int  # how many different values
    examples: Tuple[str, ...] = ()  # text column: its most common labels
    low: Optional[str] = None  # number / date column: the smallest value
    high: Optional[str] = None  # ... and the biggest


@dataclass(frozen=True)
class SheetCatalog:
    name: Optional[str]  # None for a CSV file
    columns: List[Tuple[str, str]]  # (column name, "number" | "date" | "text")
    # Week 6 presentation edits (DAT-05): row count, a profile per column, and how many columns were left out.
    rows: int = 0
    profiles: Dict[str, ColumnProfile] = field(default_factory=dict)
    columns_left_out: int = 0


@dataclass(frozen=True)
class SourceCatalog:
    document_id: int
    filename: str
    sheets: List[SheetCatalog] = field(default_factory=list)
    sheets_left_out: int = 0  # DAT-05: sheets over the limit that are not described


class Catalog(list):
    """Week 6 presentation edits (DAT-05): a plain list of SourceCatalog that also knows how many files were left out."""
    files_left_out: int = 0


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


def describe_sources(sources: Sequence[DataSource]) -> Catalog:
    """Names, column kinds and a short profile of the CSV/XLSX files: what the LLM may choose from.

    Week 6 presentation edits (DAT-05): a sheet also has its row count, and a column its number of distinct values
    plus example labels (text) or the smallest and biggest value (number, date). Anything that was left out because of
    a limit is counted, so the prompt can say so. The LLM still never receives a computed value (a sum, an average ...):
    those reach it only as DATA FACTS (DAT-06).
    A file that cannot be read is skipped (and logged); it must not stop the whole deck.
    """
    catalog = Catalog()
    catalog.files_left_out = max(0, len(sources) - CATALOG_MAX_FILES)
    for source in list(sources)[:CATALOG_MAX_FILES]:
        if source.path.suffix.lower() not in DATA_EXTENSIONS:
            continue
        try:
            all_sheets = list(_read_sheets(source).items())
            sheets = [_sheet_catalog(name, frame) for name, frame in all_sheets[:CATALOG_MAX_SHEETS]]
        except Exception:
            log.exception("Could not read %s for the slide data catalog", source.filename)
            continue
        sheets = [s for s in sheets if s.columns]
        if sheets:
            left_out = max(0, len(all_sheets) - CATALOG_MAX_SHEETS)
            catalog.append(SourceCatalog(source.document_id, source.filename, sheets, sheets_left_out=left_out))
    return catalog


def _sheet_catalog(name: Optional[str], frame: pd.DataFrame) -> SheetCatalog:
    listed = list(frame.columns[:CATALOG_MAX_COLUMNS])
    sample = frame.head(CATALOG_SAMPLE_ROWS)  # the kind of a column is detected from the first rows only
    columns = [(c, _kind(sample[c])) for c in listed]
    profiles = {}
    for column, kind in columns:
        try:
            profiles[column] = _profile(frame[column], kind)
        except Exception:  # a profile is a nice-to-have: the column is still listed without it
            log.exception("Could not profile column %s", column)
    return SheetCatalog(
        name=name, columns=columns, rows=len(frame), profiles=profiles,
        columns_left_out=max(0, len(frame.columns) - len(listed)),
    )


def _profile(series: pd.Series, kind: str) -> ColumnProfile:
    """How many different values a column has, and example labels (text) or its range (number, date)."""
    values = series.dropna()
    distinct = int(values.nunique())
    if kind == "text":
        labels = values.astype(str).str.strip()
        top = labels[labels != ""].value_counts().head(CATALOG_EXAMPLE_LABELS).index
        return ColumnProfile(distinct, examples=tuple(str(l)[:CATALOG_LABEL_CHARS] for l in top))
    if kind == "number":
        found = (values if pd.api.types.is_numeric_dtype(values) else _as_numbers(values)).dropna()
    else:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            found = pd.to_datetime(values, errors="coerce", format="mixed").dropna()
    if found.empty:
        return ColumnProfile(distinct)
    return ColumnProfile(distinct, low=_label(found.min()), high=_label(found.max()))


def _find_source(sources: Sequence[DataSource], document_id: int) -> DataSource:
    for source in sources:
        if source.document_id == document_id:
            return source
    known = ", ".join(str(s.document_id) for s in sources) or "none"
    raise ChartToolError(
        f"document_id {document_id} is not a spreadsheet of this notebook (known: {known}).",
        "unknown_document", "Use a document_id listed under DATA FILES.",
    )


class LoadedSheet(NamedTuple):
    frame: pd.DataFrame
    label: str  # such as 'sales.xlsx / Q1'
    sheet: Optional[str]  # None for a CSV file


def _load_frame(source: DataSource, sheet: Optional[str]) -> LoadedSheet:
    """The whole sheet as a DataFrame (read once, see _read_sheets) with a label for the slide."""
    try:
        sheets = _read_sheets(source)
    except Exception as exc:
        raise ChartToolError(f"Could not read {source.filename}: {exc}", "unreadable_file", "Upload the file again.") from exc
    if not _is_excel(source.path):
        return LoadedSheet(sheets[None], source.filename, None)
    names = list(sheets)
    if sheet is None or not str(sheet).strip():
        chosen = names[0]
    else:
        by_name = {n.strip().casefold(): n for n in names}
        chosen = by_name.get(str(sheet).strip().casefold())
        if chosen is None:
            raise ChartToolError(
                f"Sheet '{sheet}' not found in {source.filename} (sheets: {', '.join(names)}).",
                "unknown_sheet", "Copy the sheet name exactly from DATA FILES.",
            )
    return LoadedSheet(sheets[chosen], f"{source.filename} / {chosen}", chosen)


def _column(frame: pd.DataFrame, name: str) -> str:
    """The real column name (the LLM may differ in case or spaces)."""
    if name in frame.columns:
        return name
    folded = {str(c).strip().casefold(): c for c in frame.columns}
    found = folded.get(str(name).strip().casefold())
    if found is None:
        raise ChartToolError(
            f"Column '{name}' not found (columns: {', '.join(map(str, frame.columns))}).",
            "unknown_column", "Copy the column name exactly from DATA FILES.",
        )
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

# Week 6 presentation edits (DAT-02): check_chart / check_table return a CheckResult (data + a list of issues)
# instead of stopping at the first problem. build_chart_data / build_table_data below keep the old behaviour
# (raise ChartToolError on an error) for callers that do not need the warnings.

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
    except ChartToolError as exc:
        return CheckResult(None, [exc.issue])
    if not y_columns:
        return fail("no_value_column", "A chart needs at least one value column besides the x column.",
                    "Choose a numeric column that is not the x column.")
    if spec.chart_type == "pie" and len(y_columns) > 1:
        warn("pie_extra_series", f"A pie chart shows one series, so only '{y_columns[0]}' is used.",
             "Use a bar chart to compare several columns.")
        y_columns = y_columns[:1]
    elif len(y_columns) > MAX_CHART_SERIES:
        warn("too_many_series", f"The chart has {len(y_columns)} series; only the first {MAX_CHART_SERIES} are shown.",
             "Split the columns over several charts.")
        y_columns = y_columns[:MAX_CHART_SERIES]

    data = frame[[x_column, *y_columns]].dropna(subset=[x_column]).copy()
    if spec.aggregation != "count":
        for column in y_columns:
            data[column] = _as_numbers(data[column])  # '$1,200' and '12%' count as numbers
            filled = int(data[column].notna().sum())
            if filled == 0:
                return fail("no_numbers", f"Column '{column}' has no numbers, so it cannot be charted." + _formula_hint(loaded, source),
                            "Choose a column that holds numbers.")
            if filled / len(data) < MOSTLY_EMPTY_SHARE:
                warn("column_mostly_empty", f"Column '{column}' has numbers in only {filled} of {len(data)} rows; the other rows are left out.",
                     "Check that this is the right column.")

    x_kind = _kind(data[x_column])
    if spec.aggregation == "none" and data[x_column].duplicated().any():
        warn("duplicate_x", f"Aggregation is 'none' but {int(data[x_column].duplicated().sum())} x value(s) repeat, so the same category appears more than once.",
             "Use aggregation 'sum' or 'mean' to combine the rows.")
    unique_x = int(data[x_column].nunique())
    if spec.chart_type != "line" and x_kind != "date":
        limit = MAX_PIE_SLICES if spec.chart_type == "pie" else MAX_BAR_CATEGORIES
        if unique_x > limit and unique_x / len(data) >= ID_LIKE_UNIQUE_SHARE:
            warn("x_looks_like_id", f"Column '{x_column}' has {unique_x} different values in {len(data)} rows, so it looks like an id, not a category.",
                 "Choose a column with fewer, repeated categories.")

    if spec.aggregation == "none":
        values = data.set_index(x_column)[y_columns]
    else:
        values = data.groupby(x_column, sort=False)[y_columns].agg(spec.aggregation)
    values = values.dropna()  # never replace a missing number with a made-up 0
    if values.empty:
        return fail("empty_result", "No rows left to chart after removing empty cells." + _formula_hint(loaded, source),
                    "Check that the chosen columns contain values.")

    if spec.chart_type == "line":
        if x_kind in ("date", "number"):
            values = values.iloc[_x_order(values.index, x_kind)]  # a line needs its x values in order
        else:
            warn("line_x_not_ordered", f"Column '{x_column}' holds text categories, so the line has no natural order.",
                 "Use a date or number column for x, or choose a bar chart.")
        if len(values) > MAX_LINE_POINTS:
            warn("points_truncated", f"The line has {len(values)} points; only the first {MAX_LINE_POINTS} are shown.",
                 "Filter the data to the period you want.")
            values = values.head(MAX_LINE_POINTS)
    else:
        limit = MAX_PIE_SLICES if spec.chart_type == "pie" else MAX_BAR_CATEGORIES
        if spec.chart_type == "pie" and (values[y_columns[0]] < 0).any():  # before cutting: the cut would hide it
            return fail("pie_negative", "A pie chart cannot show negative values.", "Use a bar chart for values that can be negative.")
        if len(values) > limit:  # keep the biggest categories
            warn("categories_truncated", f"There are {len(values)} categories; only the {limit} biggest are shown.",
                 "Filter the data or group it into fewer categories.")
            values = values.sort_values(y_columns[0], ascending=False).head(limit)

    if spec.chart_type == "pie":
        if values[y_columns[0]].sum() <= 0:
            return fail("pie_total_zero", "A pie chart needs a total above zero.", "Use a bar chart, or choose another column.")
    if spec.chart_type in ("pie", "line") and len(values) < 2:
        part = "slices" if spec.chart_type == "pie" else "points"
        return fail("too_few_points", f"A {spec.chart_type} chart needs at least 2 {part}, but only {len(values)} is left.",
                    "Choose columns with more rows, or use a bar chart.")

    if len(y_columns) > 1:  # series on very different scales: the small one looks flat
        peaks = {c: float(values[c].abs().max()) for c in y_columns}
        positive = {c: peak for c, peak in peaks.items() if peak > 0}
        if len(positive) > 1:
            big, small = max(positive, key=positive.get), min(positive, key=positive.get)
            ratio = positive[big] / positive[small]
            if ratio >= SCALE_RATIO_WARNING:
                warn("scale_mismatch", f"'{big}' is about {ratio:.0f} times bigger than '{small}', so '{small}' will look flat.",
                     "Chart them separately.")

    try:
        chart = ChartData(
            chart_type=spec.chart_type,
            title=spec.title.strip() or label,
            categories=[_label(v) for v in values.index],
            series=[SeriesData(name=c, values=[round(float(v), 4) for v in values[c]]) for c in y_columns],
            source=label,
        )
    except ValidationError as exc:  # the DAT-01 checks (for example an empty category name)
        return fail("invalid_chart_data", f"The chart data is not valid: {exc.errors()[0]['msg']}", "Check the category and series names.")
    return CheckResult(chart, issues)


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
    except ChartToolError as exc:
        return CheckResult(None, [exc.issue])

    columns = requested[:MAX_TABLE_COLUMNS]
    if not columns:
        return fail("no_columns", "A table needs at least one column.", "Choose the columns to show.")
    if len(requested) > MAX_TABLE_COLUMNS:
        warn("columns_truncated", f"The table has {len(requested)} columns; only the first {MAX_TABLE_COLUMNS} are shown.",
             "Choose fewer columns.")
    if spec.max_rows > MAX_TABLE_ROWS:
        warn("rows_truncated", f"{spec.max_rows} rows were requested; only {MAX_TABLE_ROWS} fit on a slide.",
             "Ask for fewer rows.")
    row_count = max(1, min(spec.max_rows, MAX_TABLE_ROWS))
    data = frame[columns].dropna(how="all").head(row_count)
    if data.empty:
        return fail("no_data", "The chosen columns have no data." + _formula_hint(loaded, source), "Choose columns that hold values.")
    for column in columns:  # an empty column can be the result of formulas that were never calculated
        if data[column].isna().all():
            if hint := _formula_hint(loaded, source):
                return fail("formulas_not_calculated", f"Column '{column}' is empty." + hint)
            warn("empty_column", f"Column '{column}' is empty in the rows shown.", "Choose a column that has values.")

    rows = [[_cell(v) for v in row] for row in data.itertuples(index=False, name=None)]
    long_cells = sum(1 for row in rows for cell in row if isinstance(cell, str) and len(cell) > MAX_CELL_CHARS)
    if long_cells:
        warn("long_cells", f"{long_cells} cell(s) are longer than {MAX_CELL_CHARS} characters and may not fit on the slide.",
             "Choose shorter columns.")
    try:
        table = TableData(title=spec.title.strip() or label, columns=columns, rows=rows, source=label)
    except ValidationError as exc:
        return fail("invalid_table_data", f"The table data is not valid: {exc.errors()[0]['msg']}", "Check the column names.")
    return CheckResult(table, issues)


def _raise_first_error(result: CheckResult) -> None:
    if not result.ok:
        first = result.errors[0]
        raise ChartToolError(first.message, first.code, first.hint)
    for warning in result.warnings:
        log.info("%s: %s", warning.code, warning.message)


def build_chart_data(spec: ChartSpec, sources: Sequence[DataSource]) -> ChartData:
    """Compute the chart's categories and values from the real file (raises ChartToolError on an error)."""
    result = check_chart(spec, sources)
    _raise_first_error(result)
    return result.data


def build_table_data(spec: TableSpec, sources: Sequence[DataSource]) -> TableData:
    """Read the table's cells from the real file (raises ChartToolError on an error)."""
    result = check_table(spec, sources)
    _raise_first_error(result)
    return result.data


# ---------------------------------------------------------------------------
# data facts (DAT-06)
# ---------------------------------------------------------------------------
# Week 6 presentation edits (DAT-06): after a chart or table is built, simple facts are computed from its numbers
# (total, highest / lowest, share of the top item, average, change first -> last, counts). The slide writer shows
# them to the model as citable sources D1, D2 ... so a bullet about the data quotes a number that really is in the data.

@dataclass(frozen=True)
class DataFact:
    fact_id: str  # "D1", "D2" ...
    text: str  # one full sentence, with the numbers already formatted


def _fmt(value: float) -> str:
    return f"{int(value):,}" if float(value).is_integer() else f"{value:,.2f}"


def _pct(share: float) -> str:
    return f"{share * 100:.1f}%"


def _numbered(texts: List[str]) -> List[DataFact]:
    return [DataFact(f"D{number}", text) for number, text in enumerate(texts[:MAX_FACTS], start=1)]


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
    for series in chart.series[:MAX_FACT_SERIES]:
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
        index for index in range(len(table.columns))
        if any(is_number(row[index]) for row in table.rows)
        and all(is_number(row[index]) for row in table.rows if row[index] is not None)
    ]
    label_column = 0 if 0 not in numeric else None  # a text first column names the rows
    for index in numeric[:MAX_FACT_SERIES]:
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
