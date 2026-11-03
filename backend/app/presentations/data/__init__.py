"""Spreadsheet data for slides: the LLM only names a sheet and columns, pandas computes the values.

Nothing here calls an LLM. The slide writer (presentations/slide_content_agent.py) uses this package to
  1. describe the notebook's CSV/XLSX files to the LLM (names and column kinds, never the values), and
  2. turn the LLM's ChartSpec / TableSpec into ChartData / TableData read from the real file.
A spec that names a missing file, sheet or column is reported as an Issue (or raises SlideDataError from the
build_* functions), so a wrong guess becomes a dropped chart, never invented numbers.

Modules:
  limits         every limit and threshold (read as `limits.NAME` at call time)
  models         Issue, CheckResult, SlideDataError, DataSource and the catalog types
  reader         CSV / XLSX reading, header detection, the sheet cache, sources_from_documents
  cleaning       numbers, column kinds and labels
  catalog        describe_sources: what the model may choose from
  chart_builder  check_chart / build_chart_data (checking and building are one pass)
  table_builder  check_table / build_table_data
  facts          DATA FACTS computed from a finished chart or table

Limits are not re-exported here on purpose: a copy made at import time would not follow a patched `limits.NAME`.
"""

from .catalog import describe_sources
from .chart_builder import build_chart_data, check_chart
from .facts import DataFact, compute_chart_facts, compute_table_facts
from .models import (
    Catalog,
    CheckResult,
    ColumnProfile,
    DataSource,
    Issue,
    LoadedSheet,
    SheetCatalog,
    SlideDataError,
    SourceCatalog,
)
from .reader import clear_sheet_cache, sources_from_documents
from .table_builder import build_table_data, check_table

__all__ = [
    "Catalog",
    "CheckResult",
    "ColumnProfile",
    "DataFact",
    "DataSource",
    "Issue",
    "LoadedSheet",
    "SheetCatalog",
    "SlideDataError",
    "SourceCatalog",
    "build_chart_data",
    "build_table_data",
    "check_chart",
    "check_table",
    "clear_sheet_cache",
    "compute_chart_facts",
    "compute_table_facts",
    "describe_sources",
    "sources_from_documents",
]
