"""The data catalog: what the model may choose from (file names, sheets, column kinds and short profiles, never a computed value)."""

import logging
import warnings
from typing import Optional, Sequence

import pandas as pd

from . import limits
from .cleaning import _as_numbers, _kind, _label
from .models import Catalog, ColumnProfile, DataSource, SheetCatalog, SourceCatalog
from .reader import DATA_EXTENSIONS, _read_sheets

log = logging.getLogger(__name__)


def describe_sources(sources: Sequence[DataSource]) -> Catalog:
    """Names, column kinds and a short profile of the CSV/XLSX files: what the LLM may choose from.

    Week 6 presentation edits (DAT-05): a sheet also has its row count, and a column its number of distinct values
    plus example labels (text) or the smallest and biggest value (number, date). Anything that was left out because of
    a limit is counted, so the prompt can say so. The LLM still never receives a computed value (a sum, an average ...):
    those reach it only as DATA FACTS (DAT-06).
    A file that cannot be read is skipped (and logged); it must not stop the whole deck.
    """
    catalog = Catalog()
    catalog.files_left_out = max(0, len(sources) - limits.CATALOG_MAX_FILES)
    for source in list(sources)[: limits.CATALOG_MAX_FILES]:
        if source.path.suffix.lower() not in DATA_EXTENSIONS:
            continue
        try:
            all_sheets = list(_read_sheets(source).items())
            sheets = [_sheet_catalog(name, frame) for name, frame in all_sheets[: limits.CATALOG_MAX_SHEETS]]
        except Exception:
            log.exception("Could not read %s for the slide data catalog", source.filename)
            continue
        sheets = [s for s in sheets if s.columns]
        if sheets:
            left_out = max(0, len(all_sheets) - limits.CATALOG_MAX_SHEETS)
            catalog.append(SourceCatalog(source.document_id, source.filename, sheets, sheets_left_out=left_out))
    return catalog


def _sheet_catalog(name: Optional[str], frame: pd.DataFrame) -> SheetCatalog:
    listed = list(frame.columns[: limits.CATALOG_MAX_COLUMNS])
    sample = frame.head(limits.CATALOG_SAMPLE_ROWS)  # the kind of a column is detected from the first rows only
    columns = [(c, _kind(sample[c])) for c in listed]
    profiles = {}
    for column, kind in columns:
        try:
            profiles[column] = _profile(frame[column], kind)
        except Exception:  # a profile is a nice-to-have: the column is still listed without it
            log.exception("Could not profile column %s", column)
    return SheetCatalog(
        name=name,
        columns=columns,
        rows=len(frame),
        profiles=profiles,
        columns_left_out=max(0, len(frame.columns) - len(listed)),
    )


def _profile(series: pd.Series, kind: str) -> ColumnProfile:
    """How many different values a column has, and example labels (text) or its range (number, date)."""
    values = series.dropna()
    distinct = int(values.nunique())
    if kind == "text":
        labels = values.astype(str).str.strip()
        top = labels[labels != ""].value_counts().head(limits.CATALOG_EXAMPLE_LABELS).index
        return ColumnProfile(distinct, examples=tuple(str(label)[: limits.CATALOG_LABEL_CHARS] for label in top))
    if kind == "number":
        found = (values if pd.api.types.is_numeric_dtype(values) else _as_numbers(values)).dropna()
    else:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            found = pd.to_datetime(values, errors="coerce", format="mixed").dropna()
    if found.empty:
        return ColumnProfile(distinct)
    return ColumnProfile(distinct, low=_label(found.min()), high=_label(found.max()))
