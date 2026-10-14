import pytest

from app.core.config import settings
from app.database.models import Document
from tests.samples import SAMPLES


def upload(client, headers, nb_id, name, content, ctype="application/octet-stream", **form):
    return client.post(
        "/documents",
        data={"notebook_id": nb_id, **form},
        files={"file": (name, content, ctype)},
        headers=headers,
    )


@pytest.mark.parametrize("name", list(SAMPLES))
def test_upload_and_download_all_types(client, auth, notebook_id, name):
    content, ctype = SAMPLES[name]
    r = upload(client, auth, notebook_id, name, content, ctype, description="demo")
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["filename"] == name
    assert doc["file_type"] == name.rsplit(".", 1)[-1]
    assert doc["file_size"] == len(content)
    assert doc["status"] == "UPLOADED" and doc["notebook_id"] == notebook_id
    assert "file_path" not in doc  # the server's disk path is never exposed
    assert doc["download_url"] == f"{settings.api_prefix}/documents/{doc['id']}/download"
    d = client.get(f"/documents/{doc['id']}/download", headers=auth)
    assert d.status_code == 200 and d.content == content


def test_file_stored_then_deleted(client, auth, db, notebook_id):
    doc = upload(client, auth, notebook_id, "a.txt", b"disk check").json()
    path = settings.uploads_dir / db.get(Document, doc["id"]).file_path
    assert path.is_file() and path.parent.name == f"notebook_{notebook_id}"

    assert client.delete(f"/documents/{doc['id']}", headers=auth).status_code == 204
    assert not path.exists()
    assert client.get(f"/documents/{doc['id']}", headers=auth).status_code == 404
    assert client.get(f"/documents/{doc['id']}/download", headers=auth).status_code == 404


def test_list_filter_sort_paginate(client, auth, notebook_id):
    upload(client, auth, notebook_id, "b.txt", b"bbbbbb")
    upload(client, auth, notebook_id, "a.csv", b"x,y\n1,2\n")
    upload(client, auth, notebook_id, "c.txt", b"c")
    q = {"notebook_id": notebook_id}

    def get(**params):
        return client.get("/documents", params={**q, **params}, headers=auth)

    assert get().json()["total"] == 3
    assert get(file_type="txt").json()["total"] == 2
    r = get(sort_by="filename", order="asc").json()
    assert [d["filename"] for d in r["items"]] == ["a.csv", "b.txt", "c.txt"]
    r = get(limit=1, offset=1, sort_by="filename", order="asc").json()
    assert r["total"] == 3 and r["items"][0]["filename"] == "b.txt"
    assert get(search="A.").json()["total"] == 1
    r = client.get("/documents", params={"notebook_id": 999999}, headers=auth)
    assert r.status_code == 404


def test_validation_errors(client, auth, notebook_id):
    def up(*args):
        return upload(client, auth, notebook_id, *args).status_code

    assert up("evil.exe", b"MZ..") == 415
    assert up("fake.pdf", b"just text") == 400
    assert up("fake.docx", b"not a zip") == 400
    assert up("fake.xlsx", SAMPLES["notes.docx"][0]) == 400
    assert up("bin.csv", b"\x00\x01binary") == 400
    assert up("empty.txt", b"") == 400
    assert upload(client, auth, 999999, "a.txt", b"hi").status_code == 404


def test_too_large_cleans_temp(client, auth, notebook_id):
    big = b"x" * (1024 * 1024 + 1)  # the tests set the limit to 1 MB
    assert upload(client, auth, notebook_id, "big.txt", big).status_code == 413
    assert list(settings.temp_dir.glob("*.part")) == []
    r = client.get("/documents", params={"notebook_id": notebook_id}, headers=auth)
    assert r.json()["total"] == 0


def test_duplicates_are_per_notebook(client, auth, make_notebook, notebook_id):
    assert upload(client, auth, notebook_id, "d.txt", b"same").status_code == 201
    assert upload(client, auth, notebook_id, "d2.txt", b"same").status_code == 409
    other = make_notebook(auth, "second notebook")
    assert upload(client, auth, other, "d.txt", b"same").status_code == 201


def test_filename_sanitised(client, auth, notebook_id):
    r = upload(client, auth, notebook_id, "../../etc/pass<wd>.txt", b"traversal")
    assert r.status_code == 201
    name = r.json()["filename"]
    assert "/" not in name and "<" not in name and name.endswith(".txt")


def test_rename_and_describe(client, auth, notebook_id):
    doc = upload(client, auth, notebook_id, "old.txt", b"rename me").json()
    url = f"/documents/{doc['id']}"
    body = {"filename": "new name.txt", "description": "d"}
    r = client.patch(url, json=body, headers=auth)
    assert r.status_code == 200 and r.json()["filename"] == "new name.txt"
    assert client.patch(url, json={"filename": "new.pdf"}, headers=auth).status_code == 400
    r = client.patch(url, json={"description": None}, headers=auth)
    assert r.json()["description"] is None


def test_supported_types(client, auth):
    r = client.get("/documents/supported-types", headers=auth).json()
    assert set(r["extensions"]) == {"pdf", "docx", "txt", "csv", "xlsx"}


def test_deleting_a_notebook_removes_its_documents_and_files(client, auth, notebook_id):
    doc = upload(client, auth, notebook_id, "z.txt", b"zzz").json()
    folder = settings.uploads_dir / f"notebook_{notebook_id}"
    assert folder.exists()

    assert client.delete(f"/notebooks/{notebook_id}", headers=auth).status_code == 200
    assert not folder.exists()  # files are gone from the disk ...
    assert client.get(f"/documents/{doc['id']}", headers=auth).status_code == 404  # ... and DB
