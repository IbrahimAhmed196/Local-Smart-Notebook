"""Reading the notebook's CSV / XLSX files into pandas frames (each file is read once per deck, see _SHEET_CACHE).

Also: finding the header row, formulas that were never calculated, and the step from the notebook's Document rows to
DataSource objects. The chart and table builders get their sheets from here and never open a file themselves."""

import logging
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd
from openpyxl import load_workbook

from app.core.exceptions import AppError

from . import limits
from .cleaning import _label
from .models import DataSource, LoadedSheet, SlideDataError

log = logging.getLogger(__name__)

EXCEL_EXTENSIONS = (".xlsx", ".xlsm")
DATA_EXTENSIONS = (".csv",) + EXCEL_EXTENSIONS


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
    filled = raw.head(limits.HEADER_SEARCH_ROWS).notna().sum(axis=1).tolist()
    widest = max(filled, default=0)
    needed = max(min(2, widest), math.ceil(widest * limits.HEADER_MIN_FILL))  # a lone title cell is not a header
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
    frame = raw.iloc[position + 1 :].copy()
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


def _find_source(sources: Sequence[DataSource], document_id: int) -> DataSource:
    for source in sources:
        if source.document_id == document_id:
            return source
    known = ", ".join(str(s.document_id) for s in sources) or "none"
    raise SlideDataError(
        f"document_id {document_id} is not a spreadsheet of this notebook (known: {known}).",
        "unknown_document",
        "Use a document_id listed under DATA FILES.",
    )


def _load_frame(source: DataSource, sheet: Optional[str]) -> LoadedSheet:
    """The whole sheet as a DataFrame (read once, see _read_sheets) with a label for the slide."""
    try:
        sheets = _read_sheets(source)
    except Exception as exc:
        raise SlideDataError(
            f"Could not read {source.filename}: {exc}", "unreadable_file", "Upload the file again."
        ) from exc
    if not _is_excel(source.path):
        return LoadedSheet(sheets[None], source.filename, None)
    names = list(sheets)
    if sheet is None or not str(sheet).strip():
        chosen = names[0]
    else:
        by_name = {n.strip().casefold(): n for n in names}
        chosen = by_name.get(str(sheet).strip().casefold())
        if chosen is None:
            raise SlideDataError(
                f"Sheet '{sheet}' not found in {source.filename} (sheets: {', '.join(names)}).",
                "unknown_sheet",
                "Copy the sheet name exactly from DATA FILES.",
            )
    return LoadedSheet(sheets[chosen], f"{source.filename} / {chosen}", chosen)


def _column(frame: pd.DataFrame, name: str) -> str:
    """The real column name (the LLM may differ in case or spaces)."""
    if name in frame.columns:
        return name
    folded = {str(c).strip().casefold(): c for c in frame.columns}
    found = folded.get(str(name).strip().casefold())
    if found is None:
        raise SlideDataError(
            f"Column '{name}' not found (columns: {', '.join(map(str, frame.columns))}).",
            "unknown_column",
            "Copy the column name exactly from DATA FILES.",
        )
    return found


def _unique(items: Sequence[str]) -> List[str]:
    return list(dict.fromkeys(items))


def sources_from_documents(documents: Sequence[Any]) -> List[DataSource]:
    """The CSV/XLSX Document rows of a notebook -> DataSource list (what the deck generator passes on)."""
    from app.services import document_service  # imported here so this module works without the DB layer

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
