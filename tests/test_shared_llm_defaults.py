"""Feature model settings must not leak into shared client defaults."""
from unittest.mock import Mock
import pytest
from app.agents import slide_content_agent as agent
from app.core.config import Settings, settings
from app.llm.ollama_client import OllamaChatClient, OllamaJSONClient
from app.schemas.slides import PresentationOutlineResponse, SlideOutlineItem
from app.services import chat_service
from tests.fake_llm import ScriptedLLMClient
from app.presentations import generator as deck_generation

@pytest.mark.parametrize("client_type", [OllamaJSONClient, OllamaChatClient])
def test_shared_clients_use_generic_settings(monkeypatch, client_type):
    monkeypatch.setattr(settings, "ollama_model", "shared-model")
    monkeypatch.setattr(settings, "presentation_model", "slides-model")
    monkeypatch.setattr(settings, "chat_model", "chat-model")
    monkeypatch.setattr(settings, "ollama_base_url", "http://shared-host:11434/")
    client = client_type()
    assert client.model_name == "shared-model"
    assert client.base_url == "http://shared-host:11434"
    monkeypatch.setattr(settings, "presentation_model", "another-slides-model")
    assert client_type().model_name == "shared-model"

@pytest.mark.parametrize("client_type", [OllamaJSONClient, OllamaChatClient])
def test_explicit_model_and_url_override_defaults(monkeypatch, client_type):
    monkeypatch.setattr(settings, "ollama_model", "shared-model")
    client = client_type(model_name="chosen-model", base_url="http://chosen-host:11434/")
    assert client.model_name == "chosen-model"
    assert client.base_url == "http://chosen-host:11434"

def test_feature_factories_choose_their_own_models(monkeypatch):
    monkeypatch.setattr(settings, "ollama_model", "shared-model")
    monkeypatch.setattr(settings, "presentation_model", "slides-model")
    monkeypatch.setattr(settings, "chat_model", "chat-model")
    assert deck_generation.get_generator().client.model_name == "slides-model"
    assert chat_service.get_chat_client().model_name == "chat-model"

@pytest.mark.parametrize("whole_deck", [False, True])
def test_slide_writer_default_still_uses_presentation_model(monkeypatch, whole_deck):
    monkeypatch.setattr(settings, "ollama_model", "shared-model")
    monkeypatch.setattr(settings, "presentation_model", "slides-model")
    fake = ScriptedLLMClient({"subtitle": "Hello"})
    factory = Mock(return_value=fake)
    monkeypatch.setattr(agent, "OllamaJSONClient", factory)
    item = SlideOutlineItem(slide_number=1, title="Title", purpose="Introduce", layout_type="title")
    if whole_deck:
        outline = PresentationOutlineResponse(
            presentation_title="Title", target_audience="Team", slides=[item]
        )
        agent.generate_presentation_content(outline)
    else:
        agent.generate_slide_content(item, presentation_title="Title", audience="Team")
    factory.assert_called_once_with(model_name="slides-model")
    fake.assert_finished()

@pytest.mark.parametrize("env_name", ["OLLAMA_MODEL", "LSN_OLLAMA_MODEL"])
def test_generic_model_environment_setting_is_independent(monkeypatch, env_name):
    for name in ("OLLAMA_MODEL", "LSN_OLLAMA_MODEL", "LSN_PRESENTATION_MODEL", "LSN_CHAT_MODEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(env_name, "shared-model")
    monkeypatch.setenv("PRESENTATION_MODEL", "slides-model")
    monkeypatch.setenv("CHAT_MODEL", "chat-model")
    config = Settings(_env_file=None)
    assert (config.ollama_model, config.presentation_model, config.chat_model) == (
        "shared-model", "slides-model", "chat-model",
    )