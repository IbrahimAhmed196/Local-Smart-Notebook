def make_conversation(client, headers, notebook_id, title="Chat 1"):
    r = client.post(
        "/conversations", json={"notebook_id": notebook_id, "title": title}, headers=headers
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_create_list_rename_delete(client, auth, notebook_id):
    conv = make_conversation(client, auth, notebook_id)
    assert conv["notebook_id"] == notebook_id and conv["title"] == "Chat 1"

    listed = client.get("/conversations", params={"notebook_id": notebook_id}, headers=auth)
    assert [c["id"] for c in listed.json()] == [conv["id"]]

    r = client.patch(f"/conversations/{conv['id']}", json={"title": "Renamed"}, headers=auth)
    assert r.status_code == 200 and r.json()["title"] == "Renamed"

    assert client.delete(f"/conversations/{conv['id']}", headers=auth).status_code == 204
    assert client.get(f"/conversations/{conv['id']}", headers=auth).status_code == 404


def test_messages_are_saved_in_order(client, auth, notebook_id):
    conv = make_conversation(client, auth, notebook_id)
    for text in ("first", "second"):
        r = client.post(
            f"/conversations/{conv['id']}/messages", json={"content": text}, headers=auth
        )
        assert r.status_code == 201
        assert r.json()["sender"] == "user" and r.json()["content"] == text

    r = client.get(f"/conversations/{conv['id']}/messages", headers=auth)
    assert [m["content"] for m in r.json()] == ["first", "second"]
    assert r.headers["X-Total-Count"] == "2"

    h = client.get(f"/conversations/{conv['id']}", headers=auth).json()
    assert h["conversation"]["id"] == conv["id"] and len(h["messages"]) == 2


def test_empty_message_rejected(client, auth, notebook_id):
    conv = make_conversation(client, auth, notebook_id)
    for bad in ("", "   "):
        r = client.post(
            f"/conversations/{conv['id']}/messages", json={"content": bad}, headers=auth
        )
        assert r.status_code == 422


def test_blank_title_rejected(client, auth, notebook_id):
    r = client.post(
        "/conversations", json={"notebook_id": notebook_id, "title": "  "}, headers=auth
    )
    assert r.status_code == 422


def test_requires_login(client):
    assert client.get("/conversations").status_code == 401


def test_other_users_cannot_touch_conversations(client, login, make_notebook):
    alice, bob = login("alice@example.com"), login("bob@example.com")
    nb = make_notebook(alice)
    conv = make_conversation(client, alice, nb)

    # Bob cannot create a conversation in Alice's notebook ...
    r = client.post("/conversations", json={"notebook_id": nb, "title": "x"}, headers=bob)
    assert r.status_code == 404
    # ... nor read, write, rename or delete hers (404, never 403)
    cid = conv["id"]
    assert client.get(f"/conversations/{cid}", headers=bob).status_code == 404
    assert client.get(f"/conversations/{cid}/messages", headers=bob).status_code == 404
    assert client.post(f"/conversations/{cid}/messages", json={"content": "hi"}, headers=bob).status_code == 404
    assert client.patch(f"/conversations/{cid}", json={"title": "x"}, headers=bob).status_code == 404
    assert client.delete(f"/conversations/{cid}", headers=bob).status_code == 404
    # Bob's list does not include Alice's conversation
    assert client.get("/conversations", headers=bob).json() == []


def test_deleting_notebook_removes_conversations(client, auth, notebook_id):
    conv = make_conversation(client, auth, notebook_id)
    client.post(f"/conversations/{conv['id']}/messages", json={"content": "hi"}, headers=auth)
    assert client.delete(f"/notebooks/{notebook_id}", headers=auth).status_code == 200
    assert client.get(f"/conversations/{conv['id']}", headers=auth).status_code == 404
