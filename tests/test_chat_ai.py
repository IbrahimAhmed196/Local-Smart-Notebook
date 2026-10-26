"""The AI answer in a chat: history + uploaded files go to the model, the answer is stored."""
import pytest

from app.llm.ollama_client import LlmChatError
from app.services import chat_service
from tests.test_chat import make_conversation


class FakeClient:
    def __init__(self, answer="The answer.", error=None):
        self.answer, self.error, self.calls = answer, error, []

    def chat(self, messages, temperature=0.3, num_ctx=None):
        self.calls.append(messages)
        if self.error:
            raise self.error
        return self.answer


@pytest.fixture()
def fake(monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(chat_service, "get_chat_client", lambda: client)
    return client


def ask(client, auth, conv_id, text):
    return client.post(f"/conversations/{conv_id}/ask", json={"content": text}, headers=auth)


def test_ask_stores_question_and_answer(client, auth, notebook_id, fake):
    conv = make_conversation(client, auth, notebook_id)
    r = ask(client, auth, conv["id"], "Hello?")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user_message"]["sender"] == "user"
    assert body["assistant_message"]["sender"] == "assistant"
    assert body["assistant_message"]["content"] == "The answer."
    assert body["error"] is None

    stored = client.get(f"/conversations/{conv['id']}/messages", headers=auth).json()
    assert [m["sender"] for m in stored] == ["user", "assistant"]


def test_model_gets_the_chat_history(client, auth, notebook_id, fake):
    conv = make_conversation(client, auth, notebook_id)
    ask(client, auth, conv["id"], "My name is Sara.")
    ask(client, auth, conv["id"], "What is my name?")
    sent = fake.calls[-1]
    roles = [m["role"] for m in sent]
    assert roles == ["system", "user", "assistant", "user"]
    assert sent[1]["content"] == "My name is Sara."
    assert sent[-1]["content"] == "What is my name?"


def test_model_gets_uploaded_file_text(client, auth, notebook_id, fake):
    r = client.post(
        "/documents",
        data={"notebook_id": notebook_id},
        files={"file": ("facts.txt", b"The pyramid of Khufu is 146 meters tall.", "text/plain")},
        headers=auth,
    )
    assert r.status_code == 201, r.text
    conv = make_conversation(client, auth, notebook_id)
    body = ask(client, auth, conv["id"], "How tall is the pyramid?").json()
    system = fake.calls[-1][0]["content"]
    assert "146 meters" in system and "facts.txt" in system
    assert body["sources"] == ["facts.txt"]


def test_question_is_kept_when_the_model_is_down(client, auth, notebook_id, monkeypatch):
    broken = FakeClient(error=LlmChatError("Cannot reach Ollama"))
    monkeypatch.setattr(chat_service, "get_chat_client", lambda: broken)
    conv = make_conversation(client, auth, notebook_id)
    body = ask(client, auth, conv["id"], "Anyone there?").json()
    assert body["assistant_message"] is None and "Ollama" in body["error"]
    stored = client.get(f"/conversations/{conv['id']}/messages", headers=auth).json()
    assert [m["sender"] for m in stored] == ["user"]


def test_ask_rejects_empty_and_other_users(client, login, make_notebook, fake):
    alice, bob = login("alice@example.com"), login("bob@example.com")
    conv = make_conversation(client, alice, make_notebook(alice))
    assert ask(client, alice, conv["id"], "  ").status_code == 422
    assert ask(client, bob, conv["id"], "hi").status_code == 404
