"""Every limit of the spreadsheet data layer, in one place.

The first group comes from core/config.py (so `.env` can change it); the rest are fixed thresholds of the
checks. The other modules of this package read them as `limits.NAME` when they run, never `from .limits import
NAME`, so a test (or a script) changes a limit by patching it here, once: `monkeypatch.setattr(limits, "MAX_TABLE_ROWS", 3)`.
"""

from app.core.config import settings

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
