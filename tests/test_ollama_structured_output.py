"""Week 6 presentation edits (LLM-02): the JSON client sends the real JSON schema in Ollama's "format" field."""
import json
import logging

import pytest
import requests
from pydantic import BaseModel

from app.llm import ollama_client
from app.llm.ollama_client import OllamaError, OllamaInvalidJSONError, OllamaJSONClient
from app.schemas.layouts import SLIDE_LAYOUTS
from app.schemas.slide_content import SlideContentDraft
from app.schemas.slides import PresentationOutlineResponse
from tests.slide_samples import SAMPLES_DIR


class Answer(BaseModel):
    title: str
    count: int


GOOD = '{"title": "Hello", "count": 3}'


class FakeResponse:
    def __init__(self, content=None, status=200):
        self._content = content
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(response=self)

    def json(self):
        return {"message": {"content": self._content}}


def script(monkeypatch, *replies):
    """Make requests.post return the given replies one by one; returns the list of request bodies."""
    sent, queue = [], list(replies)

    def fake_post(url, json=None, timeout=None):
        sent.append(json)
        return queue.pop(0)

    monkeypatch.setattr(ollama_client.requests, "post", fake_post)
    return sent


def old_server(monkeypatch, *replies_for_json_mode):
    """An Ollama that answers 400 to a schema in "format" and works normally for format="json"."""
    sent, queue = [], list(replies_for_json_mode)

    def fake_post(url, json=None, timeout=None):
        sent.append(json)
        if json["format"] != "json":
            return FakeResponse(status=400)
        return queue.pop(0)

    monkeypatch.setattr(ollama_client.requests, "post", fake_post)
    return sent


# ---------------------------------------------------------------- what is sent

def test_the_request_carries_the_json_schema_in_the_format_field(monkeypatch):
    sent = script(monkeypatch, FakeResponse(GOOD))
    OllamaJSONClient().generate_json("p", Answer)
    assert sent[0]["format"] == Answer.model_json_schema()  # a schema object, no longer the word "json"


def test_the_schema_is_still_in_the_system_prompt_for_the_model_to_read(monkeypatch):
    sent = script(monkeypatch, FakeResponse(GOOD))
    OllamaJSONClient().generate_json("p", Answer)
    assert str(Answer.model_json_schema()) in sent[0]["messages"][0]["content"]


@pytest.mark.parametrize("how", ["argument", "setting"])
def test_structured_output_can_be_switched_off_to_get_the_old_mode_back(monkeypatch, how):
    sent = script(monkeypatch, FakeResponse(GOOD))
    if how == "argument":
        client = OllamaJSONClient(structured_output=False)
    else:
        monkeypatch.setattr(ollama_client.settings, "ollama_structured_output", False)
        client = OllamaJSONClient()
    assert client.generate_json("p", Answer) == Answer(title="Hello", count=3)
    assert sent[0]["format"] == "json"


def test_the_rest_of_the_request_is_unchanged(monkeypatch):
    sent = script(monkeypatch, FakeResponse(GOOD))
    OllamaJSONClient(model_name="m:1b").generate_json("p", Answer, temperature=0.1, num_ctx=8192)
    body = sent[0]
    assert body["model"] == "m:1b" and body["stream"] is False
    assert body["options"] == {"temperature": 0.1, "num_ctx": 8192}
    assert body["messages"][1] == {"role": "user", "content": "p"}


# ---------------------------------------------------------------- an old Ollama: fall back to format="json"

def test_an_old_server_that_rejects_the_schema_gets_the_old_mode_and_the_call_still_works(monkeypatch, caplog):
    sent = old_server(monkeypatch, FakeResponse(GOOD))
    client = OllamaJSONClient()
    with caplog.at_level(logging.WARNING):
        assert client.generate_json("p", Answer) == Answer(title="Hello", count=3)
    assert [isinstance(body["format"], dict) for body in sent] == [True, False]  # schema first, then "json"
    assert sent[1]["format"] == "json"
    assert sent[0]["messages"] == sent[1]["messages"]  # the same prompt, only the format changed
    assert "does not accept a JSON schema" in caplog.text
    assert client.structured_output is False


def test_the_client_remembers_the_rejection_and_does_not_ask_with_a_schema_again(monkeypatch):
    sent = old_server(monkeypatch, FakeResponse(GOOD), FakeResponse(GOOD))
    client = OllamaJSONClient()
    client.generate_json("p", Answer)
    client.generate_json("p", Answer)
    assert [body["format"] == "json" for body in sent] == [False, True, True]  # one rejection in total


def test_the_fallback_does_not_use_up_one_of_the_retry_attempts(monkeypatch):
    sent = old_server(monkeypatch, FakeResponse("nope"), FakeResponse("still nope"))
    client = OllamaJSONClient()
    with pytest.raises(OllamaInvalidJSONError):
        client.generate_json("p", Answer)
    assert len(sent) == 3  # 1 rejected schema + the 2 real attempts (settings.ollama_json_max_attempts)
    assert client.bad_answers == 2


def test_a_400_in_the_old_mode_is_a_real_error_not_a_reason_to_loop(monkeypatch):
    sent = script(monkeypatch, FakeResponse(status=400))
    with pytest.raises(OllamaError, match="HTTP 400"):
        OllamaJSONClient(structured_output=False).generate_json("p", Answer)
    assert len(sent) == 1


@pytest.mark.parametrize("status, text", [(404, "ollama pull"), (500, "HTTP 500")])
def test_other_http_errors_with_a_schema_are_reported_as_before(monkeypatch, status, text):
    sent = script(monkeypatch, FakeResponse(status=status))
    client = OllamaJSONClient()
    with pytest.raises(OllamaError, match=text):
        client.generate_json("p", Answer)
    assert len(sent) == 1 and client.structured_output is True  # only a 400 switches the mode


# ---------------------------------------------------------------- the counters used to measure retries

def test_the_client_counts_calls_and_answers_that_were_not_valid(monkeypatch):
    script(monkeypatch, FakeResponse("not json"), FakeResponse(GOOD), FakeResponse(GOOD))
    client = OllamaJSONClient()
    client.generate_json("p", Answer)  # 1 bad answer, then good
    client.generate_json("p", Answer)  # good at once
    assert (client.calls, client.bad_answers) == (2, 1)


# ---------------------------------------------------------------- do our schemas make good constraints?

RESPONSE_SCHEMAS = [PresentationOutlineResponse, SlideContentDraft]


def refs_in(node):
    if isinstance(node, dict):
        if "$ref" in node:
            yield node["$ref"]
        for value in node.values():
            yield from refs_in(value)
    elif isinstance(node, list):
        for value in node:
            yield from refs_in(value)


@pytest.mark.parametrize("model", RESPONSE_SCHEMAS)
def test_the_schema_can_be_sent_as_json_and_every_reference_resolves(model):
    schema = model.model_json_schema()
    json.dumps(schema)  # a schema that cannot be serialised cannot be sent
    definitions = set(schema.get("$defs", {}))
    assert {ref.rsplit("/", 1)[-1] for ref in refs_in(schema)} <= definitions


def test_the_outline_can_only_name_a_real_layout():
    layout = PresentationOutlineResponse.model_json_schema()["$defs"]["SlideOutlineItem"]["properties"]["layout_type"]
    assert layout["enum"] == list(SLIDE_LAYOUTS)  # from the registry (ARC-06), not a second list


def test_the_slide_draft_can_only_name_a_real_chart_type_and_aggregation():
    chart = SlideContentDraft.model_json_schema()["$defs"]["ChartSpec"]["properties"]
    assert chart["chart_type"]["enum"] == ["bar", "line", "pie"]
    assert chart["aggregation"]["enum"] == ["sum", "mean", "count", "none"]


def test_optional_fields_stay_nullable_and_fields_with_defaults_stay_optional():
    schema = SlideContentDraft.model_json_schema()
    for name in ("chart", "table", "subtitle"):  # Optional[...] -> the model may answer null
        assert {"type": "null"} in schema["properties"][name]["anyOf"], name
    assert "required" not in schema  # every field of the draft has a default, so {} is a valid draft
    chart = schema["$defs"]["ChartSpec"]
    assert set(chart["required"]) == {"document_id", "x_column", "y_columns"}  # no default -> required
    assert {"type": "null"} in chart["properties"]["sheet"]["anyOf"]  # a CSV has no sheet


def jsonschema_validate(instance, model):
    jsonschema = pytest.importorskip("jsonschema")
    jsonschema.validate(instance, model.model_json_schema())


def test_the_sample_outline_satisfies_its_own_schema():
    jsonschema_validate(json.loads((SAMPLES_DIR / "sample_outline.json").read_text(encoding="utf-8")), PresentationOutlineResponse)


@pytest.mark.parametrize(
    "draft",
    [
        {},  # everything is optional
        {"bullets": [{"text": "A point", "source_ids": ["S1"]}], "speaker_notes": "Say this."},
        {"subtitle": "One line", "chart": None, "table": None},
        {
            "bullets": [{"text": "Revenue by region"}],
            "chart": {"chart_type": "pie", "document_id": 2, "sheet": None, "x_column": "Region",
                      "y_columns": ["Revenue"], "aggregation": "sum", "title": "Revenue (EGP)"},
        },
        {"table": {"document_id": 2, "sheet": "Q3", "columns": ["Region", "Revenue"], "max_rows": 8}},
    ],
    ids=["empty", "bullets", "nulls", "chart-csv", "table-sheet"],
)
def test_normal_slide_drafts_are_allowed_by_the_schema(draft):
    jsonschema_validate(draft, SlideContentDraft)
    SlideContentDraft.model_validate(draft)  # ... and by the tolerant pydantic model behind it


@pytest.mark.parametrize(
    "draft",
    [
        {"chart": {"chart_type": "donut", "document_id": 1, "x_column": "a", "y_columns": ["b"]}},  # not in the enum
        {"chart": {"document_id": "one", "x_column": "a", "y_columns": ["b"]}},  # an id must be a number
        {"chart": {"document_id": 1, "x_column": "a"}},  # y_columns is required
        {"bullets": "one string"},  # the pydantic model would repair this; the schema simply forbids it
    ],
    ids=["enum", "wrong-type", "missing-required", "string-for-list"],
)
def test_the_schema_is_stricter_than_the_tolerant_validators_and_that_is_the_point(draft):
    jsonschema = pytest.importorskip("jsonschema")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(draft, SlideContentDraft.model_json_schema())


def test_an_outline_with_an_invented_layout_is_not_allowed_by_the_schema():
    jsonschema = pytest.importorskip("jsonschema")
    bad = {
        "presentation_title": "T", "target_audience": "A",
        "slides": [{"slide_number": 1, "title": "x", "purpose": "p", "layout_type": "carousel"}],
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, PresentationOutlineResponse.model_json_schema())
    # ... while the pydantic model still accepts any string, so the old mode and the cleaning code keep working
    assert PresentationOutlineResponse.model_validate(bad).slides[0].layout_type == "carousel"
