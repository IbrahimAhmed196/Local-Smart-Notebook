from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import settings


def do_login(client, email, password):
    form = {"username": email, "password": password}
    return client.post("/auth/login", data=form)


def test_register_login_me(client, login):
    r = client.post(
        "/auth/register", json={"email": "A@Example.com", "password": "secret123"}
    )
    assert r.status_code == 201
    assert "password" not in r.text  # no password or hash is ever returned
    assert r.json()["email"] == "a@example.com"  # stored lower-case

    headers = login("a@example.com")
    me = client.get("/auth/me", headers=headers)
    assert me.status_code == 200 and me.json()["email"] == "a@example.com"


def test_validation_errors(client):
    bad_email = {"email": "nope", "password": "secret123"}
    short_pw = {"email": "a@example.com", "password": "123"}
    assert client.post("/auth/register", json=bad_email).status_code == 422
    assert client.post("/auth/register", json=short_pw).status_code == 422


def test_duplicate_email_and_wrong_credentials(client):
    body = {"email": "a@example.com", "password": "secret123"}
    assert client.post("/auth/register", json=body).status_code == 201
    assert client.post("/auth/register", json=body).status_code == 409

    wrong_pw = do_login(client, "a@example.com", "wrong-pass")
    no_user = do_login(client, "x@example.com", "secret123")
    assert wrong_pw.status_code == no_user.status_code == 401
    assert wrong_pw.json() == no_user.json()  # don't reveal which e-mails exist


def test_protected_routes_need_a_valid_token(client):
    assert client.get("/auth/me").status_code == 401
    garbage = {"Authorization": "Bearer not-a-real-token"}
    assert client.get("/auth/me", headers=garbage).status_code == 401

    # a correctly signed token that has already expired
    expired = jwt.encode(
        {"sub": "1", "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )
    headers = {"Authorization": f"Bearer {expired}"}
    assert client.get("/auth/me", headers=headers).status_code == 401


def test_token_for_a_deleted_user_is_rejected(client, db, login):
    headers = login("gone@example.com")
    from app.database.models import User

    db.query(User).filter(User.email == "gone@example.com").delete()
    db.commit()
    assert client.get("/auth/me", headers=headers).status_code == 401


def test_placeholder_hash_does_not_crash_login(client, db):
    """Task 1's old test user ('fakepassword') must give 401, not a server error."""
    from app.database.models import User

    db.add(User(email="test@example.com", hashed_password="fakepassword"))
    db.commit()
    assert do_login(client, "test@example.com", "fakepassword").status_code == 401
