"""The plain data types of the data layer: sources, catalogs, issues and the result of a chart / table check."""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Tuple, Union

import pandas as pd

from app.presentations.schemas.slide_content import ChartData, TableData

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Issue:
    """Week 6 presentation edits (DAT-02): one problem found in a chart or table spec."""

    code: str  # short machine name, such as 'pie_negative'
    severity: str  # "error" = the chart / table cannot be drawn; "warning" = drawn, but the reader should know
    message: str
    hint: str = ""  # what to change


class SlideDataError(ValueError):
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

    def unwrap(self) -> Union[ChartData, TableData]:
        """The data, or SlideDataError for the first error (what build_chart_data / build_table_data do).

        Warnings do not stop anything: they are only logged here."""
        if not self.ok:
            first = self.errors[0]
            raise SlideDataError(first.message, first.code, first.hint)
        for warning in self.warnings:
            log.info("%s: %s", warning.code, warning.message)
        return self.data


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


class LoadedSheet(NamedTuple):
    frame: pd.DataFrame
    label: str  # such as 'sales.xlsx / Q1'
    sheet: Optional[str]  # None for a CSV file
