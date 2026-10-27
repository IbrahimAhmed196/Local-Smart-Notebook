from types import SimpleNamespace
from unittest.mock import Mock
import pytest
import requests
from app.llm import ollama_client
from app.llm.errors import LlmUnavailableError
from app.llm.ollama_client import OllamaJSONClient
from app.services import presentation_service as service

@pytest.mark.parametrize("installed_name", ["team-model", "team-model:latest"])
def test_ready_model_is_accepted(monkeypatch, installed_name):
    reply = Mock()
    reply.json.return_value = {"models": [{"name": installed_name}]}
    get = Mock(return_value=reply)
    monkeypatch.setattr(ollama_client.requests, "get", get)
    client = OllamaJSONClient(model_name="team-model", base_url="http://localhost:11434/")

    assert client.check_ready() is None
    get.assert_called_once_with("http://localhost:11434/api/tags", timeout=3)
    reply.raise_for_status.assert_called_once_with()

@pytest.mark.parametrize("failure", [
    requests.ConnectionError("refused"), requests.Timeout("timed out"),
])
def test_unreachable_server_gives_start_command(monkeypatch, failure):
    monkeypatch.setattr(ollama_client.requests, "get", Mock(side_effect=failure))
    with pytest.raises(LlmUnavailableError, match="ollama serve"):
        OllamaJSONClient().check_ready()

def test_http_failure_becomes_readiness_error(monkeypatch):
    reply = Mock()
    reply.raise_for_status.side_effect = requests.HTTPError("503")
    monkeypatch.setattr(ollama_client.requests, "get", Mock(return_value=reply))
    with pytest.raises(LlmUnavailableError, match="ollama serve"):
        OllamaJSONClient().check_ready()

def test_missing_model_gives_exact_pull_command(monkeypatch):
    reply = Mock()
    reply.json.return_value = {"models": [{"name": "another-model:latest"}]}
    monkeypatch.setattr(ollama_client.requests, "get", Mock(return_value=reply))
    with pytest.raises(LlmUnavailableError, match="ollama pull team-model"):
        OllamaJSONClient(model_name="team-model").check_ready()

@pytest.mark.parametrize("payload", [
    None, {}, {"models": None}, {"models": [None]}, {"models": [{"name": 123}]},
])
def test_malformed_model_list_has_readable_error(monkeypatch, payload):
    reply = Mock()
    reply.json.return_value = payload
    monkeypatch.setattr(ollama_client.requests, "get", Mock(return_value=reply))
    with pytest.raises(LlmUnavailableError, match="unreadable model list"):
        OllamaJSONClient().check_ready()

def test_invalid_json_has_readable_error(monkeypatch):
    reply = Mock()
    reply.json.side_effect = ValueError("Invalid JSON")
    monkeypatch.setattr(ollama_client.requests, "get", Mock(return_value=reply))
    with pytest.raises(LlmUnavailableError, match="unreadable model list"):
        OllamaJSONClient().check_ready()

def test_readiness_failure_stops_before_document_processing(scripted_llm, monkeypatch):
    client = scripted_llm()
    check = Mock(side_effect=LlmUnavailableError("Model unavailable"))
    monkeypatch.setattr(client, "check_ready", check)
    build_chunks = Mock()
    monkeypatch.setattr(service.presentation_context, "build_chunks", build_chunks)
    progress = Mock()
    generator = service.LocalLlmDeckGenerator(client=client)

    with pytest.raises(LlmUnavailableError, match="Model unavailable"):
        generator.generate(
            notebook=SimpleNamespace(id=1), options={}, documents=[], progress=progress,
        )

    check.assert_called_once_with()
    build_chunks.assert_not_called()
    progress.assert_not_called()
    assert client.calls == []