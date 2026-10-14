def test_notebooks_require_login(client):
    assert client.get("/notebooks/").status_code == 401
    assert client.post("/notebooks/", json={"title": "x"}).status_code == 401


def test_users_only_see_and_change_their_own_notebooks(client, login):
    alice = login("alice@example.com")
    bob = login("bob@example.com")

    r = client.post("/notebooks/", json={"title": "Alice only"}, headers=alice)
    assert r.status_code == 201
    notebook_id = r.json()["id"]

    assert client.get("/notebooks/", headers=bob).json() == []
    assert len(client.get("/notebooks/", headers=alice).json()) == 1

    url = f"/notebooks/{notebook_id}"
    assert client.put(url, json={"title": "hacked"}, headers=bob).status_code == 404
    assert client.delete(url, headers=bob).status_code == 404

    renamed = client.put(url, json={"title": "renamed"}, headers=alice)
    assert renamed.status_code == 200
    assert client.delete(url, headers=alice).status_code == 200
