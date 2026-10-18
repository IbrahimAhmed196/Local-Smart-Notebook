
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture
def valid_payload():
    return {
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


def test_validate_valid_payload(valid_payload):
    response = client.post(
        "/api/infographic/validate",
        json=valid_payload,
    )

    assert response.status_code == 200

    body = response.json()
    assert body["success"] is True
    assert body["data"]["title"] == "Machine Learning Lifecycle"


def test_reject_invalid_type(valid_payload):
    valid_payload["type"] = "chart"

    response = client.post(
        "/api/infographic/validate",
        json=valid_payload,
    )

    assert response.status_code == 422


def test_reject_missing_required_field(valid_payload):
    del valid_payload["title"]

    response = client.post(
        "/api/infographic/validate",
        json=valid_payload,
    )

    assert response.status_code == 422


def test_reject_unknown_source(valid_payload):
    valid_payload["items"][0]["source_refs"] = ["missing_source"]

    response = client.post(
        "/api/infographic/validate",
        json=valid_payload,
    )

    assert response.status_code == 422


def test_reject_duplicate_item_ids(valid_payload):
    valid_payload["items"][1]["id"] = "step_1"

    response = client.post(
        "/api/infographic/validate",
        json=valid_payload,
    )

    assert response.status_code == 422


def test_reject_timeline_without_dates(valid_payload):
    valid_payload["type"] = "timeline"

    response = client.post(
        "/api/infographic/validate",
        json=valid_payload,
    )

    assert response.status_code == 422
