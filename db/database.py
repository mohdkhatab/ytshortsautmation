import json
import os
import time
from typing import Optional

import psycopg2
import psycopg2.extras


_DB_URL = os.getenv("DATABASE_URL", "")


def get_conn():
    conn = psycopg2.connect(_DB_URL, sslmode="require")
    conn.autocommit = False
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id SERIAL PRIMARY KEY,
            chat_id BIGINT NOT NULL,
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
            created_at DOUBLE PRECISION NOT NULL,
            updated_at DOUBLE PRECISION NOT NULL
        );
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tasks_chat ON tasks(chat_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);")
    conn.commit()
    conn.close()


def create_task(chat_id: int, category: str = "") -> int:
    conn = get_conn()
    cur = conn.cursor()
    now = time.time()
    cur.execute(
        "INSERT INTO tasks (chat_id, status, category, created_at, updated_at) VALUES (%s, 'pending', %s, %s, %s) RETURNING id",
        (chat_id, category, now, now),
    )
    task_id = cur.fetchone()[0]
    conn.commit()
    conn.close()
    return task_id


def update_task(task_id: int, **kwargs) -> None:
    conn = get_conn()
    cur = conn.cursor()
    sets = []
    vals = []
    for k, v in kwargs.items():
        if k in ("status", "category", "source_url", "video_path", "thumbnail_path",
                 "title", "description", "tags", "upload_url", "error", "metadata"):
            if k == "metadata" and isinstance(v, dict):
                v = json.dumps(v)
            if k == "tags" and isinstance(v, list):
                v = json.dumps(v)
            sets.append(f"{k} = %s")
            vals.append(v)
    if sets:
        sets.append("updated_at = %s")
        vals.append(time.time())
        vals.append(task_id)
        cur.execute(f"UPDATE tasks SET {', '.join(sets)} WHERE id = %s", vals)
        conn.commit()
    conn.close()


def get_task(task_id: int) -> Optional[dict]:
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM tasks WHERE id = %s", (task_id,))
    row = cur.fetchone()
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
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM tasks WHERE status IN ('pending', 'processing') ORDER BY created_at")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_user_tasks(chat_id: int, limit: int = 5) -> list[dict]:
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT * FROM tasks WHERE chat_id = %s ORDER BY created_at DESC LIMIT %s",
        (chat_id, limit),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


init_db()
