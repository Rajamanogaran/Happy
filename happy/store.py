"""SQLite persistence for the single-user workspace."""

import json
import os
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB = Path(os.getenv("HAPPY_DB", "happy.sqlite3"))


def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB, timeout=20)
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE IF NOT EXISTS knowledge (
            id INTEGER PRIMARY KEY, title TEXT, content TEXT, source TEXT,
            created TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS conversation (
            id INTEGER PRIMARY KEY, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS research (
            id TEXT PRIMARY KEY, payload TEXT NOT NULL,
            created TEXT DEFAULT CURRENT_TIMESTAMP);
    """)
    return db


@contextmanager
def transaction():
    db = connect()
    try:
        with db:
            yield db
    finally:
        db.close()


def save(title, content, source="Note"):
    with transaction() as db:
        cur = db.execute(
            "INSERT INTO knowledge(title,content,source) VALUES (?,?,?)",
            (title, content, source),
        )
        return cur.lastrowid


def notes(query=""):
    with transaction() as db:
        rows = [dict(r) for r in db.execute("SELECT * FROM knowledge ORDER BY id DESC")]
    terms = query.casefold().split()
    return [
        n
        for n in rows
        if all(t in (n["title"] + " " + n["content"]).casefold() for t in terms)
    ]


def retrieve(query):
    words = set(re.findall(r"\w{3,}", query.casefold())) - {
        "the",
        "and",
        "that",
        "this",
        "what",
        "with",
        "from",
        "about",
        "please",
        "tell",
    }
    ranked = []
    for note in notes():
        title = set(re.findall(r"\w+", note["title"].casefold()))
        content = set(re.findall(r"\w+", note["content"].casefold()))
        score = len(words & title) * 3 + len(words & content)
        if score:
            ranked.append((score, note))
    return [
        note for _, note in sorted(ranked, key=lambda item: item[0], reverse=True)[:3]
    ]


def import_notes(items):
    added = 0
    with transaction() as db:
        for item in items:
            values = (item["title"], item["content"], item["source"])
            if not db.execute(
                "SELECT 1 FROM knowledge WHERE title=? AND content=? AND source=?",
                values,
            ).fetchone():
                db.execute(
                    "INSERT INTO knowledge(title,content,source) VALUES (?,?,?)", values
                )
                added += 1
    return added


def append_exchange(user, assistant):
    with transaction() as db:
        for message in (user, assistant):
            db.execute(
                "INSERT INTO conversation(payload) VALUES (?)", (json.dumps(message),)
            )


def conversation():
    with transaction() as db:
        return [
            json.loads(r["payload"])
            for r in db.execute("SELECT payload FROM conversation ORDER BY id")
        ]


def save_job(job):
    with transaction() as db:
        db.execute(
            "INSERT INTO research(id,payload) VALUES (?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
            (job["id"], json.dumps(job)),
        )


def research():
    with transaction() as db:
        return [
            json.loads(r["payload"])
            for r in db.execute(
                "SELECT payload FROM research ORDER BY created DESC, rowid DESC"
            )
        ]
