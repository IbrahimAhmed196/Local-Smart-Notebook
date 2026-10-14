import pytest
from fastapi import HTTPException

from app.api import deps
from app.database.models import Conversation, Document, Notebook, User


def make_world(db):
    alice = User(email="alice@example.com", hashed_password="x")
    bob = User(email="bob@example.com", hashed_password="x")
    db.add_all([alice, bob])
    db.commit()
    notebook = Notebook(title="Alice's notebook", user_id=alice.id)
    db.add(notebook)
    db.commit()
    document = Document(
        filename="a.txt",
        file_path="/tmp/a.txt",
        file_type="txt",
        notebook_id=notebook.id,
    )
    conversation = Conversation(title="First chat", notebook_id=notebook.id)
    db.add_all([document, conversation])
    db.commit()
    return alice, bob, notebook, document, conversation


def test_owner_gets_access(db):
    alice, _, notebook, document, conversation = make_world(db)
    assert deps.get_owned_notebook(notebook.id, db, alice) is notebook
    assert deps.get_owned_document(document.id, db, alice) is document
    assert deps.get_owned_conversation(conversation.id, db, alice) is conversation


def test_other_users_and_missing_ids_get_404(db):
    _, bob, notebook, document, conversation = make_world(db)
    cases = [
        (deps.get_owned_notebook, notebook.id),
        (deps.get_owned_document, document.id),
        (deps.get_owned_conversation, conversation.id),
    ]
    for dependency, object_id in cases:
        for wanted_id in (object_id, 9999):  # someone else's object / no such object
            with pytest.raises(HTTPException) as err:
                dependency(wanted_id, db, bob)
            assert err.value.status_code == 404
