"""DB-01: the job-columns migration keeps old presentations and can be undone."""
import json
import sqlite3
from pathlib import Path
 
from alembic import command
from alembic.config import Config
 
BACKEND = Path(__file__).resolve().parents[1] / "backend"
BEFORE = "850466258613"   # presentations table exists, no job columns
AFTER = "46cbb90e5c28"    # DB-01 (use your generated revision id)
NEW = {"outline", "context", "progress", "cancel_requested", "slide_versions"}
 
 
def _config(db_file: Path) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_file.as_posix()}")
    return cfg
 
 
def _columns(db_file: Path) -> set[str]:
    with sqlite3.connect(db_file) as conn:
        return {r[1] for r in conn.execute("PRAGMA table_info(presentations)")}
 
 
def _seed_legacy_rows(db_file: Path) -> None:
    insert = (
        "INSERT INTO presentations (id, notebook_id, title, status, stage, options) "
        "VALUES (?, 1, ?, ?, ?, ?)"
    )
    with sqlite3.connect(db_file) as conn:
        conn.execute("INSERT INTO users (id, email, hashed_password) "
                     "VALUES (1, 'a@x.com', 'x')")
        conn.execute("INSERT INTO notebooks (id, title, user_id) VALUES (1, 'nb', 1)")
        for pid, status, stage in [(1, "COMPLETED", "done"), (2, "FAILED", "outline")]:
            conn.execute(insert, (pid, f"p{pid}", status, stage,
                                  json.dumps({"topic": "t"})))
 
 
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
            "SELECT id, status, stage, outline, progress, cancel_requested "
            "FROM presentations ORDER BY id"
        ).fetchall()
    assert rows == [(1, "COMPLETED", "done", None, None, 0),
                    (2, "FAILED", "outline", None, None, 0)]
 
    command.downgrade(cfg, BEFORE)
    assert not NEW & _columns(db_file)
    with sqlite3.connect(db_file) as conn:
        assert conn.execute("SELECT COUNT(*) FROM presentations").fetchone()[0] == 2
