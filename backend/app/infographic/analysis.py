
import json
import re
from typing import Any

import requests

# ----------------------------- CONFIG ---------------------------------------

MODEL = "qwen2.5:3b"
OLLAMA_URL = "http://localhost:11434/api/chat"
MAX_RETRIES = 3
SCHEMA_VERSION = "1.0"

# ---------------------------------------------------------------------------

# The model generates content only. Python creates item IDs and sources.
MODEL_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "subtitle": {"type": "string"},
        "type": {
            "type": "string",
            "enum": ["process", "timeline", "comparison", "statistics"],
        },
        "summary": {"type": "string"},
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "date": {"type": ["string", "null"]},
                    "metrics": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "value": {"type": "number"},
                                "unit": {"type": "string"},
                            },
                            "required": ["name", "value", "unit"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": [
                    "title",
                    "description",
                    "date",
                    "metrics",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["title", "subtitle", "type", "summary", "items"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """
You are a strict data-extraction engine. Convert the supplied report to JSON.

ABSOLUTE RULES:
1. Use ONLY information literally supported by the REPORT.
2. Never invent, estimate, round, or calculate numbers.
3. Copy numbers exactly as written.
4. Use null for a date unless a date is attached to that item.
5. The title should represent the report title.
6. The subtitle should represent the report description.
7. Choose the appropriate type: process, timeline, comparison, or statistics.
8. For a transport survey, create one item per mode that actually appears
   in the report, such as Bus, Metro, Car, Bicycle, and Walking.
9. Each metric must have a concise name, a numeric value, and a unit.
10. Use metrics only for measurable facts. Do not put full sentences in metrics.
11. Each description must be one short, evidence-based sentence.
12. The summary should use the KEY FINDINGS section when it exists.
13. Do not create item IDs or sources. Python adds these later.
14. Do not add facts from outside the report.
15. Output ONLY the JSON object.
"""

NUM_RE = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")


def numbers_in(text: str) -> set[float]:
    """Extract numeric values while supporting thousands separators."""
    return {
        float(number.replace(",", ""))
        for number in NUM_RE.findall(text)
    }


def parse_report(report: str) -> list[tuple[str, str]]:
    """Return (section_name, line) for every non-empty report line."""
    result = []
    section = ""

    for raw in report.splitlines():
        line = raw.strip()

        if not line:
            continue

        if line.endswith(":") and line.upper() == line:
            section = line.rstrip(":").title()
            continue

        result.append((section, line))

    return result


def find_line(
    lines: list[tuple[str, str]],
    title: str,
    value: int | float,
) -> tuple[str, str] | None:
    """Find a report line containing both the item title and metric value."""
    title_lower = title.strip().lower()

    if not title_lower:
        return None

    for section, line in lines:
        if (
            title_lower in line.lower()
            and float(value) in numbers_in(line)
        ):
            return section, line

    return None


def call_ollama(report: str, feedback: str = "") -> dict[str, Any]:
    """Call the local Ollama chat API and parse its JSON response."""
    user_message = (
        f'REPORT:\n"""\n{report}\n"""\n\nReturn the JSON now.'
    )

    if feedback:
        user_message += (
            "\n\nYour previous answer had these errors. Fix them:\n"
            + feedback
        )

    payload = {
        "model": MODEL,
        "stream": False,
        "format": MODEL_SCHEMA,
        "options": {
            "temperature": 0,
            "seed": 42,
            "num_ctx": 4096,
        },
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
    }

    response = requests.post(
        OLLAMA_URL,
        json=payload,
        timeout=600,
    )
    response.raise_for_status()

    content = response.json()["message"]["content"]
    data = json.loads(content)

    if not isinstance(data, dict):
        raise ValueError("Ollama output must be a JSON object.")

    return data


def validate(
    data: dict[str, Any],
    report: str,
    lines: list[tuple[str, str]],
) -> list[str]:
    """Check model output for missing fields and unsupported numeric claims."""
    problems = []
    report_numbers = numbers_in(report)

    title = data.get("title")
    subtitle = data.get("subtitle")
    summary = data.get("summary")
    items = data.get("items")

    if not isinstance(title, str) or not title.strip():
        problems.append("Title is empty.")

    if not isinstance(subtitle, str):
        problems.append("Subtitle must be a string.")

    if not isinstance(summary, str) or not summary.strip():
        problems.append("Summary is empty.")

    if not isinstance(items, list) or not items:
        problems.append("No items were produced.")
        return problems

    for item_index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            problems.append(f"Item {item_index} must be an object.")
            continue

        name = item.get("title")
        description = item.get("description")
        metrics = item.get("metrics")

        if not isinstance(name, str) or not name.strip():
            problems.append(f"Item {item_index} has an empty title.")
            continue

        if name.strip().lower() not in report.lower():
            problems.append(
                f'Item "{name}" does not appear in the report.'
            )
            continue

        if not isinstance(description, str):
            problems.append(
                f'Item "{name}" description must be a string.'
            )
        elif any(
            number not in report_numbers
            for number in numbers_in(description)
        ):
            problems.append(
                f'Item "{name}" description contains unsupported numbers.'
            )

        if not isinstance(metrics, list) or not metrics:
            problems.append(f'Item "{name}" has no metrics.')
            continue

        for metric in metrics:
            if not isinstance(metric, dict):
                problems.append(
                    f'Item "{name}" contains an invalid metric.'
                )
                continue

            metric_name = metric.get("name")
            value = metric.get("value")
            unit = metric.get("unit")

            if not isinstance(metric_name, str) or not metric_name.strip():
                problems.append(
                    f'Item "{name}" has a metric with an empty name.'
                )

            if isinstance(value, bool) or not isinstance(value, (int, float)):
                problems.append(
                    f'Item "{name}" has a non-numeric metric value.'
                )
                continue

            if not isinstance(unit, str) or not unit.strip():
                problems.append(
                    f'Item "{name}" has a metric with an empty unit.'
                )

            if not find_line(lines, name, value):
                problems.append(
                    f'Item "{name}": metric "{metric_name}" = {value} '
                    "was not found on a report line containing its title."
                )

    if isinstance(summary, str):
        for number in numbers_in(summary):
            if number not in report_numbers:
                problems.append(
                    f"Summary contains unsupported number {number:g}."
                )

    return problems


def key_findings_summary(report: str) -> str:
    """Build a fallback summary from the report's KEY FINDINGS section."""
    result = []
    active = False

    for raw in report.splitlines():
        line = raw.strip()

        if line.upper().startswith("KEY FINDINGS"):
            active = True
            continue

        if not active:
            continue

        if line.upper().startswith("NOTE"):
            break

        if line.endswith(":") and line.upper() == line:
            break

        if line:
            result.append(re.sub(r"^\d+\.\s*", "", line))

    return " ".join(result)


def sanitize(
    data: dict[str, Any],
    report: str,
    lines: list[tuple[str, str]],
) -> dict[str, Any]:
    """Remove metrics and descriptions that fail the evidence checks."""
    report_numbers = numbers_in(report)
    clean_items = []

    for item in data.get("items", []):
        if not isinstance(item, dict):
            continue

        name = item.get("title", "")
        metrics = item.get("metrics", [])

        if not isinstance(name, str) or not isinstance(metrics, list):
            continue

        clean_metrics = []

        for metric in metrics:
            if not isinstance(metric, dict):
                continue

            value = metric.get("value")
            metric_name = metric.get("name")
            unit = metric.get("unit")

            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isinstance(metric_name, str)
                or not metric_name.strip()
                or not isinstance(unit, str)
                or not unit.strip()
            ):
                continue

            if find_line(lines, name, value):
                clean_metrics.append(metric)

        # Keep only items with at least one supported metric.
        if not clean_metrics:
            continue

        description = item.get("description", "")
        if not isinstance(description, str):
            description = ""

        if any(
            number not in report_numbers
            for number in numbers_in(description)
        ):
            description = ""

        clean_items.append({
            "title": name,
            "description": description,
            "date": item.get("date"),
            "metrics": clean_metrics,
        })

    data["items"] = clean_items

    summary = data.get("summary", "")
    if not isinstance(summary, str) or any(
        number not in report_numbers for number in numbers_in(summary)
    ):
        data["summary"] = ""

    return data


def assemble(
    data: dict[str, Any],
    lines: list[tuple[str, str]],
    report_title: str,
) -> dict[str, Any]:
    """Add IDs and source references to the extracted content."""
    sources = []
    source_id_by_line = {}
    items = []

    for index, item in enumerate(data["items"], start=1):
        refs = []

        for metric in item["metrics"]:
            hit = find_line(lines, item["title"], metric["value"])

            if not hit:
                continue

            section, line = hit

            if line not in source_id_by_line:
                source_id = f"src_{len(sources) + 1}"
                source_id_by_line[line] = source_id

                sources.append({
                    "id": source_id,
                    "label": (
                        f"{report_title} - {section}"
                        if section
                        else report_title
                    ),
                    "page": None,
                    "excerpt": line,
                })

            source_id = source_id_by_line[line]

            if source_id not in refs:
                refs.append(source_id)

        item_date = item.get("date")

        # Preserve only ISO-format dates; the shared Pydantic schema
        # will validate the date format when the plan is created.
        if item_date is not None and not isinstance(item_date, str):
            item_date = None

        items.append({
            "id": f"item_{index}",
            "title": item["title"],
            "description": item["description"],
            "date": item_date,
            "metrics": item["metrics"],
            "source_refs": refs,
        })

    return {
        "schema_version": SCHEMA_VERSION,
        "title": data["title"],
        "subtitle": data["subtitle"],
        "type": data["type"],
        "summary": data["summary"],
        "items": items,
        "sources": sources,
    }


def analyze_report(report: str) -> dict[str, Any]:
    """
    Extract infographic content from report text.

    Returns the complete JSON-compatible dictionary, including generated
    item IDs and source references. Pydantic validation happens in pipeline.py.
    """
    if not report.strip():
        raise ValueError("Report text cannot be empty.")

    lines = parse_report(report)
    report_title = report.strip().splitlines()[0].strip()

    feedback = ""
    data = None
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            data = call_ollama(report, feedback)
        except requests.RequestException as exc:
            last_error = exc
            feedback = f"Ollama request failed: {exc}"
            continue
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            last_error = exc
            feedback = f"The model returned invalid JSON: {exc}"
            continue

        problems = validate(data, report, lines)

        if not problems:
            break

        feedback = "\n".join(f"- {problem}" for problem in problems[:15])
    else:
        if data is None:
            raise RuntimeError(
                "Ollama did not return usable JSON after "
                f"{MAX_RETRIES} attempts."
            ) from last_error

        data = sanitize(data, report, lines)

    # Provide a source-derived fallback if the model's summary is unusable.
    if not isinstance(data.get("summary"), str) or not data["summary"].strip():
        data["summary"] = key_findings_summary(report)

    if not data.get("title", "").strip():
        data["title"] = report_title

    if not isinstance(data.get("subtitle"), str):
        data["subtitle"] = ""

    if not isinstance(data.get("type"), str) or not data["type"].strip():
        data["type"] = "statistics"

    # Fail clearly instead of silently returning an empty infographic.
    if not data.get("items"):
        raise ValueError(
            "No report items with supported metrics could be extracted. "
            "Check the report format and metric evidence."
        )

    if not data["summary"].strip():
        raise ValueError(
            "The report has no usable summary or KEY FINDINGS section."
        )

    return assemble(data, lines, report_title)
