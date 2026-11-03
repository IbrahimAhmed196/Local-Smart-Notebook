"""Turning cell values into numbers, column kinds and JSON-safe labels (no file access here)."""

import math
import numbers
import re
import warnings
from typing import Any, Optional

import pandas as pd

from . import limits


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
    return bool(len(values)) and sum(1 for v in values if test(v)) / len(values) >= limits.TEXT_COLUMN_MIN_SHARE


def _kind(series: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(series):
        return "text"
    if pd.api.types.is_numeric_dtype(series):
        return "number"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "date"
    values = series.dropna().head(limits.CATALOG_SAMPLE_ROWS)
    if _is_mostly(values, lambda v: _parse_number(v) is not None):
        return "number"
    # text dates: only strings with a digit are tried, so 'North' or 'May' are never dates
    texts = values.astype(str)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        parsed = pd.to_datetime(texts, errors="coerce", format="mixed")
    if len(texts) and (parsed.notna() & texts.str.contains(r"\d")).mean() >= limits.TEXT_COLUMN_MIN_SHARE:
        return "date"
    return "text"


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
