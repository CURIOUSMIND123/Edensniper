"""SQLite state store.

Everything the pipeline knows lives here, so the process can be killed at
any moment (phone sleeps, laptop reboots, quota wall) and pick up exactly
where it left off.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS topics (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint TEXT UNIQUE NOT NULL,
    title      TEXT NOT NULL,
    angle      TEXT,
    status     TEXT NOT NULL DEFAULT 'new',   -- new | used | rejected
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS videos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id    INTEGER REFERENCES topics(id),
    title       TEXT NOT NULL,
    description TEXT,
    tags        TEXT,                          -- JSON list
    status      TEXT NOT NULL DEFAULT 'scripted',
    -- scripted | generating | assembled | synced | uploaded | failed
    render_path TEXT,
    youtube_id  TEXT,
    error       TEXT,
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS clips (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id    INTEGER NOT NULL REFERENCES videos(id),
    idx         INTEGER NOT NULL,
    prompt      TEXT NOT NULL,
    narration   TEXT,
    caption     TEXT,
    status      TEXT NOT NULL DEFAULT 'pending',  -- pending | done | failed
    path        TEXT,
    attempts    INTEGER NOT NULL DEFAULT 0,
    last_error  TEXT,
    updated_at  REAL NOT NULL,
    UNIQUE (video_id, idx)
);

CREATE INDEX IF NOT EXISTS idx_clips_status ON clips(status);
CREATE INDEX IF NOT EXISTS idx_videos_status ON videos(status);
"""


def fingerprint(text: str) -> str:
    """Stable id for a topic so we never make the same video twice."""
    normalized = " ".join(text.lower().split())
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # -- meta -------------------------------------------------------
    def get_meta(self, key: str, default: Any = None) -> Any:
        row = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

    def set_meta(self, key: str, value: Any) -> None:
        self.conn.execute(
            "INSERT INTO meta(key, value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value)),
        )
        self.conn.commit()

    # -- topics -----------------------------------------------------
    def add_topic(self, title: str, angle: str = "") -> int | None:
        """Insert a topic. Returns None if we've already covered it."""
        try:
            cur = self.conn.execute(
                "INSERT INTO topics(fingerprint, title, angle, status, created_at) "
                "VALUES(?,?,?,'new',?)",
                (fingerprint(title), title, angle, time.time()),
            )
            self.conn.commit()
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None

    def next_topic(self) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM topics WHERE status='new' ORDER BY id LIMIT 1"
        ).fetchone()

    def mark_topic(self, topic_id: int, status: str) -> None:
        self.conn.execute("UPDATE topics SET status=? WHERE id=?", (status, topic_id))
        self.conn.commit()

    def known_topic_titles(self, limit: int = 200) -> list[str]:
        rows = self.conn.execute(
            "SELECT title FROM topics ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [row["title"] for row in rows]

    def count_topics(self, status: str = "new") -> int:
        return self.conn.execute(
            "SELECT COUNT(*) AS n FROM topics WHERE status=?", (status,)
        ).fetchone()["n"]

    # -- videos -----------------------------------------------------
    def create_video(
        self, topic_id: int | None, title: str, description: str, tags: Iterable[str]
    ) -> int:
        now = time.time()
        cur = self.conn.execute(
            "INSERT INTO videos(topic_id, title, description, tags, status, created_at, updated_at) "
            "VALUES(?,?,?,?,'scripted',?,?)",
            (topic_id, title, description, json.dumps(list(tags)), now, now),
        )
        self.conn.commit()
        return cur.lastrowid

    def add_clip(
        self, video_id: int, idx: int, prompt: str, narration: str, caption: str
    ) -> int:
        cur = self.conn.execute(
            "INSERT INTO clips(video_id, idx, prompt, narration, caption, updated_at) "
            "VALUES(?,?,?,?,?,?)",
            (video_id, idx, prompt, narration, caption, time.time()),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_video(self, video_id: int) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM videos WHERE id=?", (video_id,)
        ).fetchone()

    def set_video_status(self, video_id: int, status: str, **fields: Any) -> None:
        cols = ["status=?", "updated_at=?"]
        vals: list[Any] = [status, time.time()]
        for key, value in fields.items():
            cols.append(f"{key}=?")
            vals.append(value)
        vals.append(video_id)
        self.conn.execute(f"UPDATE videos SET {', '.join(cols)} WHERE id=?", vals)
        self.conn.commit()

    def videos_by_status(self, *statuses: str) -> list[sqlite3.Row]:
        marks = ",".join("?" * len(statuses))
        return self.conn.execute(
            f"SELECT * FROM videos WHERE status IN ({marks}) ORDER BY id", statuses
        ).fetchall()

    def count_videos(self, *statuses: str) -> int:
        marks = ",".join("?" * len(statuses))
        return self.conn.execute(
            f"SELECT COUNT(*) AS n FROM videos WHERE status IN ({marks})", statuses
        ).fetchone()["n"]

    # -- clips ------------------------------------------------------
    def next_pending_clip(self, max_attempts: int) -> sqlite3.Row | None:
        """Oldest unfinished clip, oldest video first, so videos complete in order."""
        return self.conn.execute(
            "SELECT c.* FROM clips c "
            "JOIN videos v ON v.id = c.video_id "
            "WHERE c.status='pending' AND c.attempts < ? "
            "AND v.status IN ('scripted','generating') "
            "ORDER BY c.video_id, c.idx LIMIT 1",
            (max_attempts,),
        ).fetchone()

    def clips_for(self, video_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM clips WHERE video_id=? ORDER BY idx", (video_id,)
        ).fetchall()

    def complete_clip(self, clip_id: int, path: str) -> None:
        self.conn.execute(
            "UPDATE clips SET status='done', path=?, last_error=NULL, updated_at=? WHERE id=?",
            (path, time.time(), clip_id),
        )
        self.conn.commit()

    def fail_clip(self, clip_id: int, error: str, max_attempts: int) -> None:
        self.conn.execute(
            "UPDATE clips SET attempts=attempts+1, last_error=?, updated_at=?, "
            "status=CASE WHEN attempts+1 >= ? THEN 'failed' ELSE 'pending' END "
            "WHERE id=?",
            (error[:500], time.time(), max_attempts, clip_id),
        )
        self.conn.commit()

    def video_is_complete(self, video_id: int) -> bool:
        row = self.conn.execute(
            "SELECT COUNT(*) AS total, SUM(status='done') AS done "
            "FROM clips WHERE video_id=?",
            (video_id,),
        ).fetchone()
        return bool(row["total"]) and row["total"] == (row["done"] or 0)

    def stats(self) -> dict[str, Any]:
        def scalar(sql: str, args: tuple = ()) -> int:
            return self.conn.execute(sql, args).fetchone()[0]

        return {
            "topics_queued": scalar("SELECT COUNT(*) FROM topics WHERE status='new'"),
            "topics_used": scalar("SELECT COUNT(*) FROM topics WHERE status='used'"),
            "clips_done": scalar("SELECT COUNT(*) FROM clips WHERE status='done'"),
            "clips_pending": scalar("SELECT COUNT(*) FROM clips WHERE status='pending'"),
            "clips_failed": scalar("SELECT COUNT(*) FROM clips WHERE status='failed'"),
            "videos_in_progress": scalar(
                "SELECT COUNT(*) FROM videos WHERE status IN ('scripted','generating')"
            ),
            "videos_done": scalar(
                "SELECT COUNT(*) FROM videos WHERE status IN ('assembled','synced','uploaded')"
            ),
            "videos_uploaded": scalar("SELECT COUNT(*) FROM videos WHERE status='uploaded'"),
        }
