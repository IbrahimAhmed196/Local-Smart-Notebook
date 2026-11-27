"""Exercise the backend analysis route with a locally installed Ollama model and Docker."""
import os
from pathlib import Path

import pytest


@pytest.mark.skipif(
    os.getenv("RUN_ANALYSIS_LIVE_TESTS") != "1",
    reason="Set RUN_ANALYSIS_LIVE_TESTS=1 to test local Ollama and Docker",
)
def test_live_sales_total(client):
    sales = Path(__file__).with_name("sales_test.csv")
    with sales.open("rb") as spreadsheet:
        response = client.post(
            "/analysis/analyze",
            files={"file": (sales.name, spreadsheet, "text/csv")},
            data={
                "question": "Sum the total column across all rows and return the scalar sum.",
            },
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["model"] == "qwen2.5-coder:7b"
    assert body["code"].strip()
    assert body["syntax_error"] is None
    assert body["rows"] == 120
    assert body["result_type"] == "scalar"
    assert body["result"] == pytest.approx(278890.50, rel=0, abs=0.005)
