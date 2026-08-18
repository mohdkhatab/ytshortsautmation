import sqlite3
import json
import time
from pathlib import Path
from typing import Optional
import config


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(config.DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            category TEXT,
            source_url TEXT,
            video_path TEXT,
            thumbnail_path TEXT,
            title TEXT,
            description TEXT,
            tags TEXT,
            upload_url TEXT,
            error TEXT,
            metadata TEXT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_tasks_chat ON tasks(chat_id);
        CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
    """)
    conn.commit()
    conn.close()


def create_task(chat_id: int, category: str = "") -> int:
    conn = get_conn()
    now = time.time()
    cur = conn.execute(
        "INSERT INTO tasks (chat_id, status, category, created_at, updated_at) VALUES (?, 'pending', ?, ?, ?)",
        (chat_id, category, now, now),
    )
    task_id = cur.lastrowid
    conn.commit()
    conn.close()
    return task_id


def update_task(task_id: int, **kwargs) -> None:
    conn = get_conn()
    sets = []
    vals = []
    for k, v in kwargs.items():
        if k in ("status", "category", "source_url", "video_path", "thumbnail_path",
                 "title", "description", "tags", "upload_url", "error", "metadata"):
            if k == "metadata" and isinstance(v, dict):
                v = json.dumps(v)
            sets.append(f"{k} = ?")
            vals.append(v)
    if sets:
        sets.append("updated_at = ?")
        vals.append(time.time())
        vals.append(task_id)
        conn.execute(f"UPDATE tasks SET {', '.join(sets)} WHERE id = ?", vals)
        conn.commit()
    conn.close()


def get_task(task_id: int) -> Optional[dict]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    conn.close()
    if row:
        d = dict(row)
        if d.get("metadata"):
            try:
                d["metadata"] = json.loads(d["metadata"])
            except Exception:
                pass
        return d
    return None


def get_pending_tasks() -> list[dict]:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM tasks WHERE status IN ('pending', 'processing') ORDER BY created_at").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_user_tasks(chat_id: int, limit: int = 5) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM tasks WHERE chat_id = ? ORDER BY created_at DESC LIMIT ?",
        (chat_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


init_db()
