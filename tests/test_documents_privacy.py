from app.core.config import settings
from app.database.models import Document
from tests.samples import SAMPLES

PDF, PDF_TYPE = SAMPLES["report.pdf"]


def upload(client, headers, nb_id, name="a.pdf", content=PDF):
    files = {"file": (name, content, PDF_TYPE)}
    return client.post("/documents", data={"notebook_id": nb_id}, files=files, headers=headers)


def test_every_document_endpoint_needs_a_login(client):
    assert client.post("/documents", data={"notebook_id": 1}).status_code == 401
    assert client.get("/documents").status_code == 401
    assert client.get("/documents/supported-types").status_code == 401
    assert client.get("/documents/1").status_code == 401
    assert client.patch("/documents/1", json={"description": "x"}).status_code == 401
    assert client.get("/documents/1/download").status_code == 401
    assert client.delete("/documents/1").status_code == 401


def test_users_cannot_touch_each_others_documents(client, login, make_notebook, db):
    alice, bob = login("alice@example.com"), login("bob@example.com")
    alice_nb = make_notebook(alice, "Alice")
    doc = upload(client, alice, alice_nb).json()
    url = f"/documents/{doc['id']}"

    # Bob cannot upload into, or list, Alice's notebook (404, not 403)
    assert upload(client, bob, alice_nb, "b.pdf", PDF + b"bob").status_code == 404
    r = client.get("/documents", params={"notebook_id": alice_nb}, headers=bob)
    assert r.status_code == 404

    # Bob cannot read, download, rename or delete Alice's document
    assert client.get(url, headers=bob).status_code == 404
    assert client.get(f"{url}/download", headers=bob).status_code == 404
    assert client.patch(url, json={"description": "x"}, headers=bob).status_code == 404
    assert client.delete(url, headers=bob).status_code == 404

    # ... and Alice's file is still there and still hers
    path = settings.uploads_dir / db.get(Document, doc["id"]).file_path
    assert path.is_file()
    assert client.get(f"{url}/download", headers=alice).content == PDF


def test_listing_without_a_notebook_only_returns_my_documents(client, login, make_notebook):
    alice, bob = login("alice@example.com"), login("bob@example.com")
    upload(client, alice, make_notebook(alice), "alice.pdf")
    upload(client, bob, make_notebook(bob), "bob.pdf", PDF + b"bob")

    mine = client.get("/documents", headers=alice).json()
    assert mine["total"] == 1 and mine["items"][0]["filename"] == "alice.pdf"
    theirs = client.get("/documents", headers=bob).json()
    assert theirs["total"] == 1 and theirs["items"][0]["filename"] == "bob.pdf"
