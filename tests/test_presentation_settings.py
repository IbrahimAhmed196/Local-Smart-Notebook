"""Week 6 presentation edits (ARC-07): presentation settings live in core/config.py and can be set in .env."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings, settings
from app.llm.ollama_client import OllamaJSONClient
from app.presentations.outline import generate_outline
from app.schemas.presentations import PresentationCreate

ROOT = Path(__file__).resolve().parents[1]


def fresh(monkeypatch, **env):
    """Settings as the app would build them from these environment variables (and no .env file)."""
    for name, value in env.items():
        monkeypatch.setenv(name, str(value))
    return Settings(_env_file=None)


# ---------------------------------------------------------------- the defaults are the old hard-coded values

def test_the_defaults_are_exactly_the_values_that_used_to_be_hard_coded(monkeypatch):
    for name in ("PRESENTATION_MODEL", "LSN_PRESENTATION_MODEL"):
        monkeypatch.delenv(name, raising=False)
    s = Settings(_env_file=None)
    assert (s.presentation_model, s.ollama_base_url) == ("qwen2.5:3b", "http://localhost:11434")
    assert (s.outline_temperature, s.slide_temperature, s.presentation_num_ctx) == (0.3, 0.1, 8192)
    assert (s.ollama_json_max_attempts, s.slide_max_attempts) == (2, 2)
    assert (s.chart_max_bar_categories, s.chart_max_pie_slices, s.chart_max_line_points) == (12, 8, 24)
    assert (s.table_max_rows, s.table_max_columns) == (15, 6)
    assert (s.catalog_max_files, s.catalog_max_sheets, s.catalog_max_columns, s.catalog_sample_rows) == (5, 5, 15, 50)
    assert s.ollama_structured_output is True


# ---------------------------------------------------------------- .env / environment variables change them

def test_environment_variables_change_every_presentation_setting(monkeypatch):
    s = fresh(
        monkeypatch,
        PRESENTATION_MODEL="qwen2.5:7b-instruct",
        OLLAMA_BASE_URL="http://gpu-box:11434",
        OUTLINE_TEMPERATURE="0.5",
        SLIDE_TEMPERATURE="0.2",
        PRESENTATION_NUM_CTX="16384",
        OLLAMA_JSON_MAX_ATTEMPTS="3",
        SLIDE_MAX_ATTEMPTS="4",
        OLLAMA_STRUCTURED_OUTPUT="false",
        CHART_MAX_BAR_CATEGORIES="20",
        CHART_MAX_PIE_SLICES="5",
        CHART_MAX_LINE_POINTS="36",
        TABLE_MAX_ROWS="10",
        TABLE_MAX_COLUMNS="8",
        CATALOG_MAX_FILES="2",
        CATALOG_MAX_SHEETS="3",
        CATALOG_MAX_COLUMNS="10",
        CATALOG_SAMPLE_ROWS="100",
    )
    assert s.presentation_model == "qwen2.5:7b-instruct" and s.ollama_base_url == "http://gpu-box:11434"
    assert (s.outline_temperature, s.slide_temperature, s.presentation_num_ctx) == (0.5, 0.2, 16384)
    assert (s.ollama_json_max_attempts, s.slide_max_attempts, s.ollama_structured_output) == (3, 4, False)
    assert (s.chart_max_bar_categories, s.chart_max_pie_slices, s.chart_max_line_points) == (20, 5, 36)
    assert (s.table_max_rows, s.table_max_columns) == (10, 8)
    assert (s.catalog_max_files, s.catalog_max_sheets, s.catalog_max_columns, s.catalog_sample_rows) == (2, 3, 10, 100)


def test_the_model_can_also_be_set_with_the_lsn_prefix(monkeypatch):
    assert fresh(monkeypatch, LSN_PRESENTATION_MODEL="llama3.1:8b").presentation_model == "llama3.1:8b"


@pytest.mark.parametrize(
    "name, value",
    [
        ("SLIDE_TEMPERATURE", "9"),  # a typo like this would silently make slides random
        ("OUTLINE_TEMPERATURE", "-1"),
        ("OLLAMA_JSON_MAX_ATTEMPTS", "0"),  # zero attempts would never call the model
        ("SLIDE_MAX_ATTEMPTS", "0"),
        ("PRESENTATION_NUM_CTX", "10"),
        ("TABLE_MAX_ROWS", "0"),
        ("CATALOG_SAMPLE_ROWS", "0"),
    ],
)
def test_a_nonsense_value_stops_the_app_at_start_with_a_clear_error(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError, match=name.lower()):
        Settings(_env_file=None)


# ---------------------------------------------------------------- the code really reads them

def test_the_json_client_takes_model_url_and_attempts_from_settings(monkeypatch):
    monkeypatch.setattr(settings, "presentation_model", "qwen2.5:7b-instruct")
    monkeypatch.setattr(settings, "ollama_base_url", "http://gpu-box:11434/")
    monkeypatch.setattr(settings, "ollama_json_max_attempts", 3)
    client = OllamaJSONClient()
    assert client.model_name == "qwen2.5:7b-instruct"
    assert client.base_url == "http://gpu-box:11434"  # the trailing slash is dropped
    assert client.max_attempts == 3


def test_an_explicit_argument_still_beats_the_setting(monkeypatch):
    monkeypatch.setattr(settings, "presentation_model", "from-settings:1b")
    client = OllamaJSONClient(model_name="from-code:3b", base_url="http://other:11434")
    assert (client.model_name, client.base_url) == ("from-code:3b", "http://other:11434")


def test_the_outline_asks_for_the_temperature_and_context_from_settings(scripted_llm, monkeypatch):
    monkeypatch.setattr(settings, "outline_temperature", 0.55)
    monkeypatch.setattr(settings, "presentation_num_ctx", 4096)
    client = scripted_llm(
        {
            "presentation_title": "T",
            "target_audience": "A",
            "slides": [
                {"slide_number": 1, "title": "Intro", "purpose": "p", "layout_type": "title"},
                {"slide_number": 2, "title": "End", "purpose": "p", "layout_type": "bullet_points"},
            ],
        }
    )
    options = PresentationCreate(topic="Sales review", num_slides=3, include_sources_slide=True).model_dump()
    generate_outline(client, options, chunks=[], data_names=[])
    assert client.calls[0]["temperature"] == 0.55 and client.calls[0]["num_ctx"] == 4096


def test_module_constants_follow_the_environment_when_the_app_starts():
    """The slide agent and the chart tool read their limits once, at import: check with a fresh process."""
    env = {
        "SLIDE_TEMPERATURE": "0.2",
        "PRESENTATION_NUM_CTX": "4096",
        "SLIDE_MAX_ATTEMPTS": "3",
        "CHART_MAX_BAR_CATEGORIES": "20",
        "CHART_MAX_PIE_SLICES": "5",
        "CHART_MAX_LINE_POINTS": "36",
        "TABLE_MAX_ROWS": "10",
        "TABLE_MAX_COLUMNS": "8",
        "CATALOG_MAX_FILES": "2",
        "CATALOG_MAX_SHEETS": "3",
        "CATALOG_MAX_COLUMNS": "10",
        "CATALOG_SAMPLE_ROWS": "100",
    }
    code = (
        "import json, sys; sys.path[:0] = ['.', 'backend']\n"
        "from app.agents import slide_content_agent as a\n"
        "from app.tools import chart_tool as c\n"
        "print(json.dumps([a.TEMPERATURE, a.NUM_CTX, a.MAX_ATTEMPTS, c.MAX_BAR_CATEGORIES, c.MAX_PIE_SLICES,\n"
        "                  c.MAX_LINE_POINTS, c.MAX_TABLE_ROWS, c.MAX_TABLE_COLUMNS, c.CATALOG_MAX_FILES,\n"
        "                  c.CATALOG_MAX_SHEETS, c.CATALOG_MAX_COLUMNS, c.CATALOG_SAMPLE_ROWS]))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, env={**os.environ, **env}, timeout=60
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.strip().splitlines()[-1]) == [0.2, 4096, 3, 20, 5, 36, 10, 8, 2, 3, 10, 100]


def test_the_prompt_shows_the_table_limits_from_settings():
    from app.llm.prompts.slide_content import build_slide_prompt
    from app.tools import chart_tool

    prompt = build_slide_prompt(
        presentation_title="D", audience="A", style=None, slide_number=2, title="T",
        purpose="P", layout="table", sources={},
    )
    assert f"up to {chart_tool.MAX_TABLE_COLUMNS} columns" in prompt
    assert f"up to {chart_tool.MAX_TABLE_ROWS} rows" in prompt
