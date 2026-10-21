"""Display formatting helpers (pure functions, no I/O).

The renderer must show the validated data WITHOUT changing its meaning, so
nothing here rounds numbers or invents values.
"""
import re
from datetime import date

# Currency units that read naturally as a prefix: ("USD", 30) -> "$30"
_PREFIX_CURRENCY = {"usd": "$", "$": "$", "eur": "€", "€": "€", "gbp": "£", "£": "£"}

_ARABIC = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]")
_LETTER = re.compile(r"[^\W\d_]", re.UNICODE)


def format_number(value: int | float) -> str:
    """1234 -> '1,234' | 38.0 -> '38' | 38.5 -> '38.5'  (never rounds)."""
    if isinstance(value, int):
        return f"{value:,}"
    if value.is_integer() and abs(value) < 1e15:
        return f"{int(value):,}"
    return f"{value:,}"


def format_metric_value(value: bool | int | float | str | None, unit: str | None) -> str:
    """Combine a metric value and unit into display text."""
    if value is None:
        return "N/A"
    if isinstance(value, bool):                       # bool must be tested before int
        return "Yes" if value else "No"

    numeric = isinstance(value, (int, float))
    text = format_number(value) if numeric else str(value)

    unit = (unit or "").strip()
    if not unit:
        return text
    if unit == "%":
        return f"{text}%"
    prefix = _PREFIX_CURRENCY.get(unit.casefold())
    if prefix and numeric:
        return f"{prefix}{text}"
    return f"{text} {unit}"


def format_date(value: date | None) -> str:
    """Jan 1 is treated as 'year only' (an LLM can only express '2012' as 2012-01-01);
    showing 'Jan 1, 2012' would claim precision the source never had."""
    if value is None:
        return ""
    if value.month == 1 and value.day == 1:
        return str(value.year)
    return f"{value.strftime('%b')} {value.day}, {value.year}"   # %-d is not portable to Windows


def is_rtl(*texts: str, threshold: float = 0.4) -> bool:
    """True when most letters in the given texts are Arabic-script."""
    joined = " ".join(t for t in texts if t)
    letters = len(_LETTER.findall(joined))
    if letters == 0:
        return False
    return len(_ARABIC.findall(joined)) / letters >= threshold


def format_refs(numbers: list[int]) -> str:
    """[1, 2, 3, 5] -> '1–3, 5'  (compact source references)."""
    nums = sorted(set(numbers))
    parts, i = [], 0
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
            j += 1
        parts.append(str(nums[i]) if j == i else (f"{nums[i]}, {nums[j]}" if j == i + 1 else f"{nums[i]}–{nums[j]}"))
        i = j + 1
    return ", ".join(parts)
