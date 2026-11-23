"""Test infographic generation via chat."""
from pathlib import Path
import pytest

from app.infographic.schema import InfographicPlan
import app.infographic.pipeline as pipeline_module
import app.infographic.rendering as rendering_module
from tests.test_chat import make_conversation


@pytest.fixture()
def mock_infographic(monkeypatch):
    sample_plan = InfographicPlan(
        schema_version="1.0",
        title="Test Infographic",
        subtitle="Test Subtitle",
        type="process",
        summary="A test summary",
        items=[
            {
                "id": "step_1",
                "title": "First Step",
                "description": "Do something",
                "date": None,
                "metrics": [],
                "source_refs": ["src_1"],
            }
        ],
        sources=[
            {
                "id": "src_1",
                "label": "Test Source",
                "page": 1,
                "excerpt": "Do something first",
            }
        ],
    )
    monkeypatch.setattr(pipeline_module, "generate_infographic_plan", lambda report: sample_plan)

    class MockRendered:
        content = b"\x89PNG\r\n\x1a\nfake_png"
        media_type = "image/png"
        extension = "png"

    async def fake_render(plan, output_format="png", scale=2.0):
        return MockRendered()

    monkeypatch.setattr(rendering_module, "render_infographic", fake_render)
    return sample_plan


def test_ask_infographic_generates_and_stores_artifact(client, auth, notebook_id, mock_infographic):
    conv = make_conversation(client, auth, notebook_id)
    r = client.post(
        f"/conversations/{conv['id']}/ask",
        json={"content": "Here is report data: ...", "feature": "infographic"},
        headers=auth,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user_message"]["feature"] == "infographic"
    assert body["assistant_message"]["feature"] == "infographic"
    assert body["assistant_message"]["artifact_path"] is not None
    assert body["assistant_message"]["image_url"] is not None
    assert body["assistant_message"]["image_url"].startswith("/artifacts/")

    # Check artifact retrieval
    art_r = client.get(body["assistant_message"]["image_url"])
    assert art_r.status_code == 200
    assert art_r.headers["content-type"] == "image/png"
    assert art_r.content == b"\x89PNG\r\n\x1a\nfake_png"
