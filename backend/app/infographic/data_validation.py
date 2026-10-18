
import re
from dataclasses import dataclass
from typing import Optional

from app.infographic.schema import InfographicPlan


@dataclass(frozen=True)
class Fact:
    mode: str
    metric: str
    value: float
    unit: str
    evidence: str


# Metric names in the infographic JSON -> canonical fact keys.
METRIC_ALIASES = {
    "usage percentage": "usage_percentage",
    "share in percent": "usage_percentage",
    "percentage of respondents": "usage_percentage",
    "average one-way commute": "commute_minutes",
    "average one-way commute time": "commute_minutes",
    "commute time": "commute_minutes",
    "monthly cost": "monthly_cost",
    "monthly cost per person": "monthly_cost",
    "share in people": "people_count",
    "number of people": "people_count",
    "respondent count": "people_count",
}

SECTION_ALIASES = {
    "transport mode": "transport",
    "transport modes": "transport",
    "average one-way commute": "commute",
    "average one-way commute times": "commute",
    "monthly cost per person": "cost",
}

SECTION_METRICS = {
    "transport": ("people_count", "usage_percentage"),
    "commute": ("commute_minutes",),
    "cost": ("monthly_cost",),
}

MODE_NAMES = ("Bus", "Metro", "Car", "Bicycle", "Walking")


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def parse_number(raw: str) -> float:
    return float(raw.replace(",", ""))


def extract_facts(report: str) -> list[Fact]:
    """
    Extract canonical facts from a section-based transport report.

    Expected examples:
      Transport Mode
      Bus: 320 people (32%)

      Average One-Way Commute
      Bus: 38 minutes

      Monthly Cost Per Person
      Bus: $30
    """
    facts: list[Fact] = []
    current_section: Optional[str] = None

    for raw_line in report.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        heading = re.sub(r"[:#\s]+$", "", line).strip().casefold()
        if heading in SECTION_ALIASES:
            current_section = SECTION_ALIASES[heading]
            continue

        if current_section is None:
            continue

        mode = next(
            (
                name
                for name in MODE_NAMES
                if re.match(
                    rf"^\s*{re.escape(name)}\s*[:|\-]",
                    line,
                    flags=re.IGNORECASE,
                )
            ),
            None,
        )
        if mode is None:
            continue

        body = re.sub(
            rf"^\s*{re.escape(mode)}\s*[:|\-]\s*",
            "",
            line,
            flags=re.IGNORECASE,
        )

        if current_section == "transport":
            # Example: 320 people (32%)
            people_match = re.search(
                r"(?<![\d.])([\d,]+)\s+people\b",
                body,
                re.IGNORECASE,
            )
            percent_match = re.search(
                r"(?<![\d.])([\d.]+)\s*%",
                body,
            )

            if people_match:
                facts.append(
                    Fact(
                        mode=mode.casefold(),
                        metric="people_count",
                        value=parse_number(people_match.group(1)),
                        unit="people",
                        evidence=line,
                    )
                )
            if percent_match:
                facts.append(
                    Fact(
                        mode=mode.casefold(),
                        metric="usage_percentage",
                        value=parse_number(percent_match.group(1)),
                        unit="%",
                        evidence=line,
                    )
                )

        elif current_section == "commute":
            match = re.search(
                r"(?<![\d.])([\d,.]+)\s*(minutes?|mins?)\b",
                body,
                re.IGNORECASE,
            )
            if match:
                facts.append(
                    Fact(
                        mode=mode.casefold(),
                        metric="commute_minutes",
                        value=parse_number(match.group(1)),
                        unit="minutes",
                        evidence=line,
                    )
                )

        elif current_section == "cost":
            match = re.search(
                r"(?:\$\s*([\d,.]+)|([\d,.]+)\s*(?:USD|dollars?))",
                body,
                re.IGNORECASE,
            )
            if match:
                raw_value = match.group(1) or match.group(2)
                facts.append(
                    Fact(
                        mode=mode.casefold(),
                        metric="monthly_cost",
                        value=parse_number(raw_value),
                        unit="USD",
                        evidence=line,
                    )
                )

    return facts


def metric_key(name: str) -> Optional[str]:
    return METRIC_ALIASES.get(normalize(name))


def numeric_equal(left: int | float, right: float) -> bool:
    return abs(float(left) - right) < 1e-9


def validate_infographic_data(
    plan: InfographicPlan,
    original_report: str,
) -> list[str]:
    errors: list[str] = []
    report_normalized = normalize(original_report)

    # A source excerpt must genuinely occur in the original report.
    for source in plan.sources:
        if not source.excerpt.strip():
            errors.append(f"Source {source.id}: excerpt is empty.")
        elif normalize(source.excerpt) not in report_normalized:
            errors.append(
                f"Source {source.id}: excerpt does not match the report."
            )

    facts = extract_facts(original_report)
    facts_by_key: dict[tuple[str, str], list[Fact]] = {}

    for fact in facts:
        key = (fact.mode, fact.metric)
        facts_by_key.setdefault(key, []).append(fact)

    sources_by_id = {source.id: source for source in plan.sources}

    for item in plan.items:
        mode = item.title.strip().casefold()

        # Ensure references exist and their evidence is valid.
        referenced_sources = []
        for source_id in item.source_refs:
            source = sources_by_id.get(source_id)
            if source is None:
                errors.append(
                    f"Item {item.id}: unknown source reference {source_id}."
                )
            else:
                referenced_sources.append(source)

        evidence = " ".join(s.excerpt for s in referenced_sources)

        if not referenced_sources:
            errors.append(
                f"Item {item.id}: no valid source evidence was provided."
            )
        elif normalize(item.title) not in normalize(evidence):
            errors.append(
                f"Item {item.id}: its source evidence does not mention "
                f"'{item.title}'."
            )

        for metric in item.metrics:
            key = metric_key(metric.name)

            # Do not silently claim verification for an unknown metric.
            if key is None:
                errors.append(
                    f"Item {item.id}: metric '{metric.name}' has no "
                    "configured fact mapping."
                )
                continue

            if not isinstance(metric.value, (int, float)) or isinstance(
                metric.value, bool
            ):
                errors.append(
                    f"Item {item.id}, metric '{metric.name}': "
                    "expected a numeric value for this report."
                )
                continue

            matching_facts = facts_by_key.get((mode, key), [])
            if not matching_facts:
                errors.append(
                    f"Item {item.id}, metric '{metric.name}': "
                    f"no matching '{key}' fact for '{item.title}' "
                    "was extracted from the report."
                )
                continue

            if not any(
                numeric_equal(metric.value, fact.value)
                for fact in matching_facts
            ):
                expected = ", ".join(
                    str(f.value) for f in matching_facts
                )
                errors.append(
                    f"Item {item.id}, metric '{metric.name}': "
                    f"received {metric.value}, but the report states "
                    f"{expected} for {item.title}."
                )
                continue

            # The referenced evidence must support the same fact.
            evidence_facts = [
                fact
                for fact in matching_facts
                if normalize(fact.evidence) in normalize(evidence)
            ]
            if not evidence_facts:
                errors.append(
                    f"Item {item.id}, metric '{metric.name}': "
                    "the value exists in the report, but its referenced "
                    "sources do not support this specific fact."
                )

    return errors
