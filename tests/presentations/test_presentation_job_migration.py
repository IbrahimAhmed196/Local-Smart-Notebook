"""DB-01: the job-columns migration keeps old presentations and can be undone."""

import json
import logging
import sqlite3
from pathlib import Path

import pytest
from alembic.config import Config

from alembic import command

BACKEND = Path(__file__).resolve().parents[2] / "backend"
BEFORE = "850466258613"  # presentations table exists, no job columns
AFTER = "46cbb90e5c28"  # DB-01 (use your generated revision id)
NEW = {"outline", "context", "progress", "cancel_requested", "slide_versions"}


@pytest.fixture(autouse=True)
def _restore_logging():
    """Alembic's env.py calls logging.config.fileConfig(), which disables every logger that already exists and
    replaces the root handlers. Put them back, or later tests that read caplog would see nothing."""
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    loggers = {
        name: (lg.disabled, lg.level, lg.propagate, lg.handlers[:])
        for name, lg in logging.Logger.manager.loggerDict.items()
        if isinstance(lg, logging.Logger)
    }
    yield
    root.handlers[:] = handlers
    root.setLevel(level)
    for name, (disabled, lg_level, propagate, lg_handlers) in loggers.items():
        lg = logging.getLogger(name)
        lg.disabled, lg.propagate, lg.handlers[:] = disabled, propagate, lg_handlers
        lg.setLevel(lg_level)


def _config(db_file: Path) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_file.as_posix()}")
    return cfg


def _columns(db_file: Path) -> set[str]:
    with sqlite3.connect(db_file) as conn:
        return {r[1] for r in conn.execute("PRAGMA table_info(presentations)")}


def _seed_legacy_rows(db_file: Path) -> None:
    insert = "INSERT INTO presentations (id, notebook_id, title, status, stage, options) VALUES (?, 1, ?, ?, ?, ?)"
    with sqlite3.connect(db_file) as conn:
        conn.execute("INSERT INTO users (id, email, hashed_password) VALUES (1, 'a@x.com', 'x')")
        conn.execute("INSERT INTO notebooks (id, title, user_id) VALUES (1, 'nb', 1)")
        for pid, status, stage in [(1, "COMPLETED", "done"), (2, "FAILED", "outline")]:
            conn.execute(insert, (pid, f"p{pid}", status, stage, json.dumps({"topic": "t"})))


def test_upgrade_keeps_presentations_and_downgrade_restores_schema(tmp_path):
    db_file = tmp_path / "legacy.db"
    cfg = _config(db_file)

    command.upgrade(cfg, BEFORE)
    _seed_legacy_rows(db_file)
    assert not NEW & _columns(db_file)

    command.upgrade(cfg, AFTER)
    assert NEW <= _columns(db_file)
    with sqlite3.connect(db_file) as conn:
        rows = conn.execute(
            "SELECT id, status, stage, outline, progress, cancel_requested FROM presentations ORDER BY id"
        ).fetchall()
    assert rows == [(1, "COMPLETED", "done", None, None, 0), (2, "FAILED", "outline", None, None, 0)]

    command.downgrade(cfg, BEFORE)
    assert not NEW & _columns(db_file)
    with sqlite3.connect(db_file) as conn:
        assert conn.execute("SELECT COUNT(*) FROM presentations").fetchone()[0] == 2
