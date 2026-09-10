# -*- coding: utf-8 -*-
"""SQLite data layer for local dev. Swap for Postgres/Supabase in production by
replacing these helpers; the routers only call the functions below."""
import sqlite3, os, json, time, uuid
from .config import settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, title TEXT,
  channel_url TEXT, language TEXT, style_id TEXT, style_custom TEXT,
  voice_id TEXT, image_provider TEXT, audio_provider TEXT, llm_model TEXT, last_job_id TEXT,
  length_words INTEGER, status TEXT DEFAULT 'draft',
  created_at REAL, updated_at REAL
);
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY, project_id TEXT NOT NULL, user_id TEXT NOT NULL,
  status TEXT DEFAULT 'queued', stage TEXT, progress REAL DEFAULT 0,
  log TEXT DEFAULT '[]', error TEXT, artifacts TEXT DEFAULT '{}',
  created_at REAL, updated_at REAL
);
CREATE TABLE IF NOT EXISTS provider_keys (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, provider TEXT NOT NULL,
  ciphertext TEXT NOT NULL, hint TEXT, created_at REAL,
  UNIQUE(user_id, provider)
);
CREATE TABLE IF NOT EXISTS feedback (
  id TEXT PRIMARY KEY, user_id TEXT, kind TEXT, message TEXT,
  email TEXT, page TEXT, created_at REAL
);
"""


def _conn():
    os.makedirs(os.path.dirname(settings.DB_PATH), exist_ok=True)
    c = sqlite3.connect(settings.DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def init_db():
    with _conn() as c:
        c.executescript(_SCHEMA)
        # lightweight migrations for dev DBs created before a column existed
        for tbl, col, decl in [("projects", "voice_id", "TEXT"),
                               ("projects", "image_provider", "TEXT"),
                               ("projects", "audio_provider", "TEXT"),
                               ("projects", "llm_model", "TEXT"),
                               ("projects", "last_job_id", "TEXT")]:
            try:
                c.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} {decl}")
            except sqlite3.OperationalError:
                pass  # already exists


def new_id(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def now():
    return time.time()


def insert(table, row):
    cols = ",".join(row)
    ph = ",".join("?" for _ in row)
    with _conn() as c:
        c.execute(f"INSERT INTO {table} ({cols}) VALUES ({ph})", list(row.values()))
    return row.get("id")


def update(table, id_, fields):
    fields = dict(fields, updated_at=now())
    sets = ",".join(f"{k}=?" for k in fields)
    with _conn() as c:
        c.execute(f"UPDATE {table} SET {sets} WHERE id=?", list(fields.values()) + [id_])


def fetchone(table, **where):
    clause = " AND ".join(f"{k}=?" for k in where)
    with _conn() as c:
        r = c.execute(f"SELECT * FROM {table} WHERE {clause}", list(where.values())).fetchone()
    return dict(r) if r else None


def fetchall(table, order="created_at DESC", **where):
    with _conn() as c:
        if where:
            clause = " AND ".join(f"{k}=?" for k in where)
            rows = c.execute(f"SELECT * FROM {table} WHERE {clause} ORDER BY {order}",
                             list(where.values())).fetchall()
        else:
            rows = c.execute(f"SELECT * FROM {table} ORDER BY {order}").fetchall()
    return [dict(r) for r in rows]
