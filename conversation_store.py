# -*- coding: utf-8 -*-
"""SQLite persistence for conversations and shared serialization helpers.

This module owns chat history storage. It has no dependency on the Tkinter
application shell, so persistence can be tested and evolved independently.
"""
from __future__ import annotations

import json
import re
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def pretty_time(value: str | None) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value).astimezone().strftime("%d.%m.%Y %H:%M")
    except (ValueError, TypeError):
        return value


def load_json(path: Path, default: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return default

class Store:
    """SQLite storage for chats, messages and user memories."""
    def __init__(self, path: Path) -> None:
        self.path = path
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.execute("PRAGMA journal_mode = WAL")
        self._create_schema()

    def _create_schema(self) -> None:
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            role TEXT NOT NULL CHECK(role IN ('user','assistant','system')),
            content TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            sync_id TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id, id);
        """)
        columns = {str(row[1]) for row in self.db.execute("PRAGMA table_info(messages)")}
        if "sync_id" not in columns:
            self.db.execute("ALTER TABLE messages ADD COLUMN sync_id TEXT")
        rows = self.db.execute("SELECT id FROM messages WHERE sync_id IS NULL OR sync_id='' ").fetchall()
        for row in rows:
            self.db.execute("UPDATE messages SET sync_id=? WHERE id=?", (uuid.uuid4().hex, row["id"]))
        self.db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_sync_id ON messages(sync_id)")
        self.db.commit()

    def create_conversation(self, title: str = "Новый диалог") -> str:
        identifier = uuid.uuid4().hex
        stamp = now_iso()
        self.db.execute("INSERT INTO conversations(id,title,created_at,updated_at) VALUES(?,?,?,?)", (identifier, title, stamp, stamp))
        self.db.commit()
        return identifier

    def ensure_conversation(self) -> str:
        row = self.db.execute("SELECT id FROM conversations ORDER BY updated_at DESC LIMIT 1").fetchone()
        return str(row["id"]) if row else self.create_conversation()

    def list_conversations(self, search: str = "") -> list[sqlite3.Row]:
        if search.strip():
            pattern = f"%{search.strip()}%"
            return list(self.db.execute("SELECT * FROM conversations WHERE title LIKE ? ORDER BY updated_at DESC", (pattern,)))
        return list(self.db.execute("SELECT * FROM conversations ORDER BY updated_at DESC"))

    def conversation_ids(self) -> set[str]:
        """Return conversation IDs without treating sqlite3.Row as a dict."""
        return {str(row["id"]) for row in self.list_conversations()}

    def get_conversation(self, identifier: str) -> sqlite3.Row | None:
        return self.db.execute("SELECT * FROM conversations WHERE id=?", (identifier,)).fetchone()

    def rename_conversation(self, identifier: str, title: str) -> None:
        self.db.execute("UPDATE conversations SET title=?,updated_at=? WHERE id=?", (title.strip()[:100] or "Новый диалог", now_iso(), identifier))
        self.db.commit()

    def delete_conversation(self, identifier: str) -> None:
        self.db.execute("DELETE FROM conversations WHERE id=?", (identifier,))
        self.db.commit()

    def add_message(self, conversation_id: str, role: str, content: str, source: str = "", sync_id: str | None = None) -> None:
        stamp = now_iso()
        self.db.execute("INSERT INTO messages(conversation_id,role,content,source,created_at,sync_id) VALUES(?,?,?,?,?,?)", (conversation_id, role, content, source, stamp, sync_id or uuid.uuid4().hex))
        self.db.execute("UPDATE conversations SET updated_at=? WHERE id=?", (stamp, conversation_id))
        self.db.commit()
        if role == "user":
            row = self.db.execute("SELECT title FROM conversations WHERE id=?", (conversation_id,)).fetchone()
            if row and row["title"] == "Новый диалог":
                title = re.sub(r"\s+", " ", content.split("\n\n[Контекст файла", 1)[0]).strip()
                if title:
                    self.rename_conversation(conversation_id, (title[:57] + "…") if len(title) > 58 else title)

    def get_messages(self, conversation_id: str, limit: int | None = None) -> list[sqlite3.Row]:
        if limit:
            rows = self.db.execute("SELECT * FROM (SELECT * FROM messages WHERE conversation_id=? ORDER BY id DESC LIMIT ?) ORDER BY id", (conversation_id, limit))
        else:
            rows = self.db.execute("SELECT * FROM messages WHERE conversation_id=? ORDER BY id", (conversation_id,))
        return list(rows)

    def clear_messages(self, conversation_id: str) -> None:
        self.db.execute("DELETE FROM messages WHERE conversation_id=?", (conversation_id,))
        self.db.execute("UPDATE conversations SET title='Новый диалог',updated_at=? WHERE id=?", (now_iso(), conversation_id))
        self.db.commit()

    def export_markdown(self, conversation_id: str) -> str:
        conversation = self.get_conversation(conversation_id)
        title = conversation["title"] if conversation else "Диалог"
        lines = [f"# {title}", "", f"Экспортировано: {pretty_time(now_iso())}", ""]
        for row in self.get_messages(conversation_id):
            if row["role"] == "user":
                label = "Вы"
            elif row["role"] == "assistant":
                label = "ИИ"
            else:
                continue
            lines += [f"## {label} · {pretty_time(row['created_at'])}", "", row["content"], ""]
        return "\n".join(lines)

    def import_legacy_history(self, history_path: Path) -> None:
        count = self.db.execute("SELECT COUNT(*) AS n FROM conversations").fetchone()["n"]
        if count:
            return
        legacy = load_json(history_path, [])
        if not isinstance(legacy, list) or not legacy:
            self.create_conversation()
            return
        cid = self.create_conversation("Импортированная история")
        for item in legacy:
            if isinstance(item, dict) and item.get("role") in ("user", "assistant") and isinstance(item.get("content"), str):
                self.add_message(cid, item["role"], item["content"])

    def close(self) -> None:
        self.db.close()
