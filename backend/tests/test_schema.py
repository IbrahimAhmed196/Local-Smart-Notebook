
import pytest
from pydantic import ValidationError

from app.infographic.schema import InfographicPlan


def make_plan(**overrides):
    data = {
        "schema_version": "1.0",
        "title": "Machine Learning Lifecycle",
        "subtitle": "Main project stages",
        "type": "process",
        "summary": "An overview of an ML project.",
        "items": [
            {
                "id": "step_1",
                "title": "Data Collection",
                "description": "Collect relevant data.",
                "date": None,
                "metrics": [],
                "source_refs": ["src_1"],
            },
            {
                "id": "step_2",
                "title": "Data Preparation",
                "description": "Clean the collected data.",
                "date": None,
                "metrics": [],
                "source_refs": ["src_1"],
            },
        ],
        "sources": [
            {
                "id": "src_1",
                "label": "ML Notes",
                "page": 2,
                "excerpt": "Data collection comes first.",
            }
        ],
    }

    data.update(overrides)
    return data


def test_valid_process():
    plan = InfographicPlan.model_validate(make_plan())

    assert plan.type == "process"
    assert len(plan.items) == 2


def test_invalid_type():
    data = make_plan(type="chart")

    with pytest.raises(ValidationError):
        InfographicPlan.model_validate(data)


def test_duplicate_item_ids():
    data = make_plan()
    data["items"][1]["id"] = data["items"][0]["id"]

    with pytest.raises(ValidationError, match="unique"):
        InfographicPlan.model_validate(data)


def test_unknown_source_reference():
    data = make_plan()
    data["items"][0]["source_refs"] = ["missing_source"]

    with pytest.raises(ValidationError, match="unknown source"):
        InfographicPlan.model_validate(data)


def test_timeline_requires_dates():
    data = make_plan(type="timeline")

    with pytest.raises(ValidationError, match="must have a date"):
        InfographicPlan.model_validate(data)


def test_valid_timeline():
    data = make_plan(type="timeline")

    data["items"][0]["date"] = "2020"
    data["items"][1]["date"] = "2024"

    plan = InfographicPlan.model_validate(data)

    assert plan.type == "timeline"


def test_comparison_requires_matching_metrics():
    data = make_plan(type="comparison")

    data["items"][0]["metrics"] = [
        {"label": "Cost", "value": "Low"}
    ]
    data["items"][1]["metrics"] = [
        {"label": "Speed", "value": "High"}
    ]

    with pytest.raises(ValidationError, match="same metric labels"):
        InfographicPlan.model_validate(data)


def test_extra_fields_are_rejected():
    data = make_plan()
    data["unexpected"] = "not allowed"

    with pytest.raises(ValidationError):
        InfographicPlan.model_validate(data)


def test_json_serialization():
    plan = InfographicPlan.model_validate(make_plan())

    json_output = plan.model_dump_json()
    restored = InfographicPlan.model_validate_json(json_output)

    assert restored == plan
