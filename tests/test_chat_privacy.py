def test_user_cannot_access_another_users_conversation(client, auth, login, make_notebook):
    notebook_id = make_notebook(auth)
    created = client.post("/conversations", json={"notebook_id": notebook_id}, headers=auth)
    conversation_id = created.json()["id"]

    other_user = login("other-chat-user@example.com")
    assert client.get(f"/conversations/{conversation_id}", headers=other_user).status_code == 404
    assert client.post(
        f"/conversations/{conversation_id}/messages",
        json={"content": "private prompt"},
        headers=other_user,
    ).status_code == 404
    assert client.delete(f"/conversations/{conversation_id}", headers=other_user).status_code == 404


def test_every_chat_endpoint_needs_a_login(client):
    assert client.post("/conversations", json={"notebook_id": 1}).status_code == 401
    assert client.get("/conversations").status_code == 401
    assert client.get("/conversations/1").status_code == 401
    assert client.patch("/conversations/1", json={"title": "x"}).status_code == 401
    assert client.delete("/conversations/1").status_code == 401
    assert client.post("/conversations/1/messages", json={"content": "x"}).status_code == 401
    assert client.get("/conversations/1/messages").status_code == 401


def test_users_cannot_touch_each_others_conversations(client, login, make_notebook):
    alice, bob = login("alice-chat@example.com"), login("bob-chat@example.com")
    alice_notebook = make_notebook(alice, "Alice")
    created = client.post("/conversations", json={"notebook_id": alice_notebook}, headers=alice)
    url = f"/conversations/{created.json()['id']}"
    client.post(f"{url}/messages", json={"content": "secret"}, headers=alice)

    assert client.post("/conversations", json={"notebook_id": alice_notebook}, headers=bob).status_code == 404
    assert client.patch(url, json={"title": "hacked"}, headers=bob).status_code == 404
    assert client.get(f"{url}/messages", headers=bob).status_code == 404

    mine = client.get(f"{url}/messages", headers=alice).json()
    assert [m["content"] for m in mine] == ["secret"]
    assert client.get(url, headers=alice).json()["conversation"]["title"] == "secret"


def test_listing_only_returns_my_conversations(client, login, make_notebook):
    alice, bob = login("alice-chat@example.com"), login("bob-chat@example.com")
    alice_notebook, bob_notebook = make_notebook(alice, "Alice"), make_notebook(bob, "Bob")
    client.post("/conversations", json={"notebook_id": alice_notebook, "title": "alice chat"}, headers=alice)
    client.post("/conversations", json={"notebook_id": bob_notebook, "title": "bob chat"}, headers=bob)

    assert [c["title"] for c in client.get("/conversations", headers=alice).json()] == ["alice chat"]
    assert [c["title"] for c in client.get("/conversations", headers=bob).json()] == ["bob chat"]
    other = client.get("/conversations", params={"notebook_id": alice_notebook}, headers=bob)
    assert other.status_code == 200 and other.json() == []
