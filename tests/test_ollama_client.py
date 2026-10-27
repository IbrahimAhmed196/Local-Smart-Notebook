"""Week 6 presentation edits (LLM-01): the Ollama JSON client (timeouts, errors, retry with feedback)."""
import logging

import pytest
import requests
from pydantic import BaseModel

from app.llm import ollama_client
from app.llm.ollama_client import (
    OllamaError,
    OllamaInvalidJSONError,
    OllamaJSONClient,
    OllamaSchemaError,
    OllamaTimeoutError,
    OllamaUnreachableError,
)


class Answer(BaseModel):
    title: str
    count: int


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
    """Make requests.post return / raise the given replies one by one; returns the list of calls."""
    calls, queue = [], list(replies)

    def fake_post(url, json=None, timeout=None):
        calls.append({"url": url, "json": json, "timeout": timeout})
        reply = queue.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(ollama_client.requests, "post", fake_post)
    return calls


GOOD = '{"title": "Hello", "count": 3}'


def test_every_request_has_a_connect_and_a_read_timeout(monkeypatch):
    calls = script(monkeypatch, FakeResponse(GOOD))
    OllamaJSONClient(connect_timeout=2, read_timeout=30).generate_json("p", Answer)
    assert calls[0]["timeout"] == (2, 30)


def test_a_timeout_becomes_a_clean_error_and_is_not_retried(monkeypatch, caplog):
    calls = script(monkeypatch, requests.ReadTimeout("slow"))
    with caplog.at_level(logging.WARNING), pytest.raises(OllamaTimeoutError) as exc:
        OllamaJSONClient(read_timeout=30).generate_json("p", Answer)
    assert "30 seconds" in str(exc.value)
    assert len(calls) == 1  # waiting another 30 s for the same answer would not help
    assert "attempt 1/2 failed" in caplog.text


def test_ollama_not_running_is_a_clear_error(monkeypatch):
    script(monkeypatch, requests.ConnectionError("refused"))
    with pytest.raises(OllamaUnreachableError, match="ollama serve"):
        OllamaJSONClient().generate_json("p", Answer)


def test_a_connect_timeout_counts_as_unreachable_not_as_a_slow_model(monkeypatch):
    script(monkeypatch, requests.ConnectTimeout("no route"))
    with pytest.raises(OllamaUnreachableError):
        OllamaJSONClient().generate_json("p", Answer)


def test_a_missing_model_tells_the_user_what_to_pull(monkeypatch):
    script(monkeypatch, FakeResponse(status=404))
    with pytest.raises(OllamaUnreachableError, match="ollama pull"):
        OllamaJSONClient(model_name="nope:1b").generate_json("p", Answer)


def test_other_http_errors_are_reported_with_their_status(monkeypatch):
    script(monkeypatch, FakeResponse(status=500))
    with pytest.raises(OllamaError, match="HTTP 500"):
        OllamaJSONClient().generate_json("p", Answer)


def test_bad_json_is_retried_once_with_the_error_in_the_prompt_and_then_succeeds(monkeypatch, caplog):
    calls = script(monkeypatch, FakeResponse("this is not json"), FakeResponse(GOOD))
    with caplog.at_level(logging.WARNING):
        result = OllamaJSONClient().generate_json("Write a title.", Answer)
    assert result == Answer(title="Hello", count=3)
    assert len(calls) == 2
    first, second = (c["json"]["messages"][1]["content"] for c in calls)
    assert first == "Write a title."  # the first prompt is not changed
    assert second.startswith("Write a title.") and "previous answer was rejected" in second
    assert "not valid JSON" in second  # ... and says WHY
    assert "attempt 1/2 failed" in caplog.text


def test_schema_mismatch_twice_raises_one_clear_error_with_the_real_reason(monkeypatch, caplog):
    calls = script(monkeypatch, FakeResponse('{"title": "x"}'), FakeResponse('{"title": "x", "count": "many"}'))
    with caplog.at_level(logging.WARNING), pytest.raises(OllamaSchemaError) as exc:
        OllamaJSONClient().generate_json("p", Answer)
    assert len(calls) == 2
    assert "Last error:" in str(exc.value) and "count" in str(exc.value)
    assert "attempt 1/2 failed" in caplog.text and "attempt 2/2 failed" in caplog.text  # every failure is logged


def test_invalid_json_twice_keeps_the_json_error_name(monkeypatch):
    script(monkeypatch, FakeResponse("nope"), FakeResponse("still nope"))
    with pytest.raises(OllamaInvalidJSONError, match="JSONDecodeError"):
        OllamaJSONClient().generate_json("p", Answer)


def test_all_errors_are_runtime_errors_so_old_callers_keep_working():
    for error in (OllamaUnreachableError, OllamaTimeoutError, OllamaInvalidJSONError, OllamaSchemaError):
        assert issubclass(error, OllamaError) and issubclass(error, RuntimeError)
