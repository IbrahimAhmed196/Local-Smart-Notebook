import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.infographic.router as router_module
from app.infographic.rendering import RenderingError
from app.infographic.schema import InfographicPlan
from tests.test_infographic_rendering import _chromium_available, load

PLAN_JSON = (Path(router_module.__file__).parent / "samples" / "process.json").read_text(encoding="utf-8")

app = FastAPI()
app.include_router(router_module.router)
client = TestClient(app)

needs_chromium = pytest.mark.skipif(not _chromium_available(), reason="Playwright/Chromium not installed")


def post_report(path, content=b"report text", name="r.txt", **kw):
    return client.post(path, files={"file": (name, content, "text/plain")}, **kw)


# ---------- original endpoints keep their behaviour
def test_validate_still_works():
    assert client.post("/api/infographic/validate", json=json.loads(PLAN_JSON)).status_code == 200
    assert client.post("/api/infographic/validate", json={"title": "x"}).status_code == 422


def test_generate_validation_errors_unchanged():
    assert post_report("/api/infographic/generate", name="r.pdf").status_code == 415
    assert post_report("/api/infographic/generate", content=b"").status_code == 400
    assert post_report("/api/infographic/generate", content=b"   \n").status_code == 400
    assert post_report("/api/infographic/generate", content=b"\xff\xfe\x00bad").status_code == 400


def test_generate_success_and_error_mapping(monkeypatch):
    plan = load("process")
    monkeypatch.setattr(router_module, "generate_infographic_plan", lambda report: plan)
    r = post_report("/api/infographic/generate")
    assert r.status_code == 200 and r.json()["data"]["title"] == plan.title

    def boom(_): raise ValueError("Data verification failed")
    monkeypatch.setattr(router_module, "generate_infographic_plan", boom)
    assert post_report("/api/infographic/generate").status_code == 422

    def down(_): raise RuntimeError("Ollama is not running")
    monkeypatch.setattr(router_module, "generate_infographic_plan", down)
    assert post_report("/api/infographic/generate").status_code == 502


# ---------- new endpoints
def test_render_html():
    r = client.post("/api/infographic/render?format=html", content=PLAN_JSON, headers={"Content-Type": "application/json"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert "Machine Learning Lifecycle" in r.text


@needs_chromium
def test_render_png():
    r = client.post("/api/infographic/render?scale=1", content=PLAN_JSON, headers={"Content-Type": "application/json"})
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert 'infographic.png' in r.headers["content-disposition"]


def test_render_rejects_bad_input():
    h = {"Content-Type": "application/json"}
    assert client.post("/api/infographic/render", content='{"title": "x"}', headers=h).status_code == 422
    assert client.post("/api/infographic/render?format=gif", content=PLAN_JSON, headers=h).status_code == 422
    assert client.post("/api/infographic/render?scale=9", content=PLAN_JSON, headers=h).status_code == 422


def test_render_failure_maps_to_502(monkeypatch):
    def fail(*a, **k): raise RenderingError("Chromium missing")
    monkeypatch.setattr(router_module, "render_infographic", fail)
    r = client.post("/api/infographic/render", content=PLAN_JSON, headers={"Content-Type": "application/json"})
    assert r.status_code == 502 and "Chromium missing" in r.json()["detail"]["details"]


@needs_chromium
def test_generate_image_end_to_end(monkeypatch):
    monkeypatch.setattr(router_module, "generate_infographic_plan", lambda report: load("statistics"))
    r = post_report("/api/infographic/generate-image?scale=1")
    assert r.status_code == 200 and r.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_generate_image_html_and_errors(monkeypatch):
    monkeypatch.setattr(router_module, "generate_infographic_plan", lambda report: load("timeline"))
    r = post_report("/api/infographic/generate-image?format=html")
    assert r.status_code == 200 and "Milestones in Artificial Intelligence" in r.text
    assert post_report("/api/infographic/generate-image", name="r.docx").status_code == 415

    def boom(_): raise ValueError("bad facts")
    monkeypatch.setattr(router_module, "generate_infographic_plan", boom)
    assert post_report("/api/infographic/generate-image").status_code == 422
