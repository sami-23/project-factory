import sqlite3
from pathlib import Path
from app.config import get_settings


def _db_path() -> Path:
    p = Path(get_settings().data_dir)
    p.mkdir(exist_ok=True)
    return p / "projects.db"


def init_db():
    conn = sqlite3.connect(_db_path())
    conn.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            date        TEXT NOT NULL,
            title       TEXT,
            description TEXT,
            language    TEXT,
            project_type TEXT,
            github_url  TEXT,
            screenshot_path TEXT,
            status      TEXT NOT NULL DEFAULT 'running',
            log         TEXT DEFAULT '',
            idea_json   TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Migration for existing databases that predate idea_json column
    try:
        conn.execute("ALTER TABLE projects ADD COLUMN idea_json TEXT")
    except Exception:
        pass
    conn.commit()
    conn.close()


def create_run(date: str) -> int:
    conn = sqlite3.connect(_db_path())
    cur = conn.execute("INSERT INTO projects (date) VALUES (?)", (date,))
    conn.commit()
    run_id = cur.lastrowid
    conn.close()
    return run_id


def update_run(run_id: int, **kwargs):
    if not kwargs:
        return
    fields = ", ".join(f"{k} = ?" for k in kwargs)
    conn = sqlite3.connect(_db_path())
    conn.execute(f"UPDATE projects SET {fields} WHERE id = ?", [*kwargs.values(), run_id])
    conn.commit()
    conn.close()


def append_log(run_id: int, line: str):
    conn = sqlite3.connect(_db_path())
    conn.execute(
        "UPDATE projects SET log = COALESCE(log, '') || ? WHERE id = ?",
        (line + "\n", run_id),
    )
    conn.commit()
    conn.close()


def get_run(run_id: int) -> dict | None:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM projects WHERE id = ?", (run_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_runs() -> list[dict]:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_recent_titles(n: int = 30) -> list[str]:
    conn = sqlite3.connect(_db_path())
    rows = conn.execute(
        "SELECT title FROM projects WHERE title IS NOT NULL ORDER BY created_at DESC LIMIT ?",
        (n,),
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def cleanup_stuck_runs():
    """Mark any runs left in 'running' state (from a crashed/restarted server) as failed."""
    conn = sqlite3.connect(_db_path())
    conn.execute("UPDATE projects SET status = 'failed' WHERE status = 'running'")
    conn.commit()
    conn.close()


def get_last_run() -> dict | None:
    """Return the most recently created run regardless of status."""
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM projects ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_run(run_id: int):
    conn = sqlite3.connect(_db_path())
    conn.execute("DELETE FROM projects WHERE id = ?", (run_id,))
    conn.commit()
    conn.close()


def get_current_run() -> dict | None:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM projects WHERE status = 'running' ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return dict(row) if row else None
