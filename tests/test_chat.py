def test_conversation_message_history_and_delete(client, auth, notebook_id):
    created = client.post(
        "/conversations", json={"notebook_id": notebook_id}, headers=auth
    )
    assert created.status_code == 201
    conversation_id = created.json()["id"]

    sent = client.post(
        f"/conversations/{conversation_id}/messages",
        json={"content": "  Explain sampling  "},
        headers=auth,
    )
    assert sent.status_code == 201
    assert sent.json()["content"] == "Explain sampling"

    history = client.get(f"/conversations/{conversation_id}/messages", headers=auth)
    assert history.status_code == 200
    assert [message["content"] for message in history.json()] == ["Explain sampling"]

    deleted = client.delete(f"/conversations/{conversation_id}", headers=auth)
    assert deleted.status_code == 204
    assert client.get(f"/conversations/{conversation_id}", headers=auth).status_code == 404


def test_conversation_can_be_renamed(client, auth, notebook_id):
    created = client.post(
        "/conversations", json={"notebook_id": notebook_id}, headers=auth
    )
    conversation_id = created.json()["id"]
    renamed = client.patch(
        f"/conversations/{conversation_id}",
        json={"title": "DIP revision"},
        headers=auth,
    )
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "DIP revision"


def send(client, headers, conversation_id, content):
    return client.post(
        f"/conversations/{conversation_id}/messages", json={"content": content}, headers=headers
    )


def new_conversation(client, headers, notebook_id, **extra):
    body = {"notebook_id": notebook_id, **extra}
    return client.post("/conversations", json=body, headers=headers).json()["id"]


def test_history_is_in_order_and_paginated_with_total_count(client, auth, notebook_id):
    conversation_id = new_conversation(client, auth, notebook_id)
    for n in range(5):
        assert send(client, auth, conversation_id, f"msg {n}").status_code == 201
    url = f"/conversations/{conversation_id}/messages"

    everything = client.get(url, headers=auth)
    assert [m["content"] for m in everything.json()] == [f"msg {n}" for n in range(5)]
    assert everything.headers["x-total-count"] == "5"
    assert all(m["sender"] == "user" for m in everything.json())

    page = client.get(url, params={"limit": 2, "offset": 2}, headers=auth)
    assert [m["content"] for m in page.json()] == ["msg 2", "msg 3"]
    assert page.headers["x-total-count"] == "5"
    assert client.get(url, params={"limit": 0}, headers=auth).status_code == 422


def test_prompt_validation(client, auth, notebook_id):
    conversation_id = new_conversation(client, auth, notebook_id)
    assert send(client, auth, conversation_id, "").status_code == 422
    assert send(client, auth, conversation_id, "   \n ").status_code == 422
    assert send(client, auth, conversation_id, "x" * 10001).status_code == 422
    url = f"/conversations/{conversation_id}/messages"
    assert client.post(url, json={}, headers=auth).status_code == 422
    assert send(client, auth, conversation_id, "x" * 10000).status_code == 201
    assert client.get(url, headers=auth).headers["x-total-count"] == "1"


def test_conversation_title_validation(client, auth, notebook_id):
    for title in ("", "   ", "x" * 201):
        body = {"notebook_id": notebook_id, "title": title}
        assert client.post("/conversations", json=body, headers=auth).status_code == 422
    assert client.post("/conversations", json={"title": "no notebook"}, headers=auth).status_code == 422
    created = client.post(
        "/conversations", json={"notebook_id": notebook_id, "title": "  padded  "}, headers=auth
    )
    assert created.json()["title"] == "padded"
    url = f"/conversations/{created.json()['id']}"
    assert client.patch(url, json={"title": "   "}, headers=auth).status_code == 422


def test_creating_in_a_missing_notebook_is_404(client, auth):
    response = client.post("/conversations", json={"notebook_id": 999999}, headers=auth)
    assert response.status_code == 404


def test_unicode_title_and_prompt_are_kept(client, auth, notebook_id):
    conversation_id = new_conversation(client, auth, notebook_id, title="محادثة 📄")
    assert send(client, auth, conversation_id, "ما هو ملخص هذا المستند؟").status_code == 201
    assert client.get(f"/conversations/{conversation_id}", headers=auth).json()["conversation"]["title"] == "محادثة 📄"
    history = client.get(f"/conversations/{conversation_id}/messages", headers=auth).json()
    assert history[0]["content"] == "ما هو ملخص هذا المستند؟"


def test_list_conversations_with_and_without_a_notebook(client, auth, make_notebook, notebook_id):
    other_notebook = make_notebook(auth, "Second")
    new_conversation(client, auth, notebook_id, title="in first")
    new_conversation(client, auth, other_notebook, title="in second")

    everything = client.get("/conversations", headers=auth)
    assert everything.status_code == 200
    assert sorted(c["title"] for c in everything.json()) == ["in first", "in second"]

    only = client.get("/conversations", params={"notebook_id": other_notebook}, headers=auth)
    assert [c["title"] for c in only.json()] == ["in second"]

    page = client.get("/conversations", params={"limit": 1, "offset": 1}, headers=auth)
    assert len(page.json()) == 1
    assert client.get("/conversations", params={"limit": 0}, headers=auth).status_code == 422


def test_untitled_conversation_is_named_after_its_first_prompt(client, auth, notebook_id):
    conversation_id = new_conversation(client, auth, notebook_id)
    send(client, auth, conversation_id, "What is in\nthis   report?")
    send(client, auth, conversation_id, "A second question")
    url = f"/conversations/{conversation_id}"
    assert client.get(url, headers=auth).json()["conversation"]["title"] == "What is in this report?"

    long_id = new_conversation(client, auth, notebook_id)
    send(client, auth, long_id, "word " * 40)
    title = client.get(f"/conversations/{long_id}", headers=auth).json()["conversation"]["title"]
    assert len(title) <= 50 and "\n" not in title


def test_a_title_chosen_by_the_user_is_never_replaced(client, auth, notebook_id):
    for title in ("Untitled", "My thesis"):
        conversation_id = new_conversation(client, auth, notebook_id, title=title)
        send(client, auth, conversation_id, "hello there")
        shown = client.get(f"/conversations/{conversation_id}", headers=auth)
        assert shown.json()["conversation"]["title"] == title


def test_deleting_a_conversation_removes_its_messages(client, auth, db, notebook_id):
    from app.database.models import Message

    conversation_id = new_conversation(client, auth, notebook_id)
    send(client, auth, conversation_id, "bye")
    assert client.delete(f"/conversations/{conversation_id}", headers=auth).status_code == 204
    assert db.query(Message).filter(Message.conversation_id == conversation_id).count() == 0
    assert send(client, auth, conversation_id, "again").status_code == 404
    assert client.get(f"/conversations/{conversation_id}/messages", headers=auth).status_code == 404


def test_deleting_a_notebook_removes_its_conversations_and_messages(client, auth, db, notebook_id):
    from app.database.models import Conversation, Message

    conversation_id = new_conversation(client, auth, notebook_id)
    send(client, auth, conversation_id, "hi")
    assert client.delete(f"/notebooks/{notebook_id}", headers=auth).status_code == 200
    assert client.get(f"/conversations/{conversation_id}", headers=auth).status_code == 404
    assert db.query(Conversation).count() == 0
    assert db.query(Message).count() == 0
