def test_health_and_chat_workflow(client, auth, notebook_id):
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}

    created = client.post("/conversations", json={"notebook_id": notebook_id}, headers=auth)
    assert created.status_code == 201
    conversation_id = created.json()["id"]
    sent = client.post(
        f"/conversations/{conversation_id}/messages",
        json={"content": "مرحبا 🌸"},
        headers=auth,
    )
    assert sent.status_code == 201
    assert sent.json()["content"] == "مرحبا 🌸"


def test_full_workflow(client):
    body = {"email": "student@example.com", "password": "secret123"}
    assert client.post("/auth/register", json=body).status_code == 201
    form = {"username": body["email"], "password": body["password"]}
    token = client.post("/auth/login", data=form).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/auth/me", headers=headers).json()["email"] == body["email"]

    notebook = client.post("/notebooks/", json={"title": "Thesis"}, headers=headers).json()
    files = {"file": ("notes.txt", b"hello notebook", "text/plain")}
    upload = client.post("/documents", data={"notebook_id": notebook["id"]}, files=files, headers=headers)
    assert upload.status_code == 201
    document = upload.json()

    conversation = client.post(
        "/conversations", json={"notebook_id": notebook["id"], "title": "Questions"}, headers=headers
    ).json()
    for prompt in ("Summarise my notes", "List the key points"):
        sent = client.post(
            f"/conversations/{conversation['id']}/messages", json={"content": prompt}, headers=headers
        )
        assert sent.status_code == 201
    history = client.get(f"/conversations/{conversation['id']}/messages", headers=headers)
    assert [m["content"] for m in history.json()] == ["Summarise my notes", "List the key points"]

    assert client.get("/documents", headers=headers).json()["total"] == 1
    assert len(client.get("/conversations", headers=headers).json()) == 1
    assert client.delete(f"/notebooks/{notebook['id']}", headers=headers).status_code == 200
    assert client.get(f"/documents/{document['id']}", headers=headers).status_code == 404
    assert client.get(f"/conversations/{conversation['id']}", headers=headers).status_code == 404
    assert client.get("/conversations", headers=headers).json() == []


def test_cors_allows_the_frontend_origin(client):
    from app.core.config import settings

    origin = settings.cors_origins[0]
    preflight = client.options(
        "/conversations",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == origin

    simple = client.get("/health", headers={"Origin": origin})
    assert simple.headers["access-control-allow-origin"] == origin
    assert "x-total-count" in simple.headers["access-control-expose-headers"].lower()


def test_cors_rejects_unknown_origins(client):
    response = client.get("/health", headers={"Origin": "http://evil.example.com"})
    assert "access-control-allow-origin" not in response.headers
