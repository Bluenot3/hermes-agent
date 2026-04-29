"""
Telegram utility helpers.

Provides:
- Message formatting (MarkdownV2 escaping, chunking)
- Inline keyboard builders
- Session management (SQLite-backed)
- User/admin verification
- Rate limiting (in-memory sliding window)
"""

from __future__ import annotations

import asyncio
import html
import json
import re
import sqlite3
import time
from collections import defaultdict, deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Deque, Dict, Generator, List, Optional, Tuple


# ── Telegram message size limits ─────────────────────────────────────────────

MAX_MESSAGE_LENGTH = 4096  # Telegram hard limit for text messages
MAX_CAPTION_LENGTH = 1024  # Limit for photo/document captions


# ── Markdown formatting ────────────────────────────────────────────────────────


_MARKDOWNV2_ESCAPE = re.compile(r"([_*\[\]()~`>#+\-=|{}.!\\])")


def escape_markdown(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2."""
    return _MARKDOWNV2_ESCAPE.sub(r"\\\1", text)


def format_code_block(code: str, language: str = "") -> str:
    """Wrap *code* in a Telegram MarkdownV2 code block."""
    lang = escape_markdown(language) if language else ""
    escaped = code.replace("\\", "\\\\").replace("`", "\\`")
    return f"```{lang}\n{escaped}\n```"


def format_html(text: str) -> str:
    """Convert plain text to Telegram HTML-safe string."""
    return html.escape(text)


def chunk_message(text: str, max_length: int = MAX_MESSAGE_LENGTH) -> List[str]:
    """Split *text* into chunks that fit within Telegram's size limit.

    Splits on newlines where possible to avoid breaking mid-word.
    """
    if len(text) <= max_length:
        return [text]

    chunks: List[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        if len(current) + len(line) > max_length:
            if current:
                chunks.append(current)
            # If a single line exceeds max_length, hard-split it.
            while len(line) > max_length:
                chunks.append(line[:max_length])
                line = line[max_length:]
            current = line
        else:
            current += line
    if current:
        chunks.append(current)
    return chunks


# ── Inline keyboard builders ──────────────────────────────────────────────────


def approval_keyboard(action_id: str) -> List[List[Dict[str, str]]]:
    """Return an inline keyboard with Confirm / Cancel buttons.

    *action_id* is embedded in the callback_data so the handler can
    correlate responses to the original request.
    """
    return [
        [
            {"text": "✅ Confirm", "callback_data": f"approve:{action_id}"},
            {"text": "❌ Cancel", "callback_data": f"deny:{action_id}"},
        ]
    ]


def status_keyboard() -> List[List[Dict[str, str]]]:
    """Return a simple refresh-status inline keyboard."""
    return [[{"text": "🔄 Refresh", "callback_data": "status:refresh"}]]


# ── Session management (SQLite) ────────────────────────────────────────────────


@dataclass
class Session:
    """Represents a per-user conversation session."""

    user_id: int
    chat_id: int
    project: Optional[str] = None
    history: List[Dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class SessionManager:
    """SQLite-backed session store with in-memory cache."""

    def __init__(self, db_path: str = "telegram_sessions.db") -> None:
        self._db_path = db_path
        self._cache: Dict[int, Session] = {}
        self._init_db()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    user_id   INTEGER PRIMARY KEY,
                    chat_id   INTEGER NOT NULL,
                    project   TEXT,
                    history   TEXT NOT NULL DEFAULT '[]',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self._db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def get_or_create(self, user_id: int, chat_id: int) -> Session:
        """Return the existing session or create a new one."""
        if user_id in self._cache:
            return self._cache[user_id]

        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE user_id = ?", (user_id,)
            ).fetchone()
            if row:
                session = Session(
                    user_id=row["user_id"],
                    chat_id=row["chat_id"],
                    project=row["project"],
                    history=json.loads(row["history"]),
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
            else:
                now = time.time()
                session = Session(user_id=user_id, chat_id=chat_id, created_at=now, updated_at=now)
                conn.execute(
                    "INSERT INTO sessions (user_id, chat_id, project, history, created_at, updated_at) "
                    "VALUES (?, ?, ?, '[]', ?, ?)",
                    (user_id, chat_id, None, now, now),
                )

        self._cache[user_id] = session
        return session

    def save(self, session: Session) -> None:
        """Persist *session* to SQLite and update the cache."""
        session.updated_at = time.time()
        self._cache[session.user_id] = session

        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sessions "
                "(user_id, chat_id, project, history, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    session.user_id,
                    session.chat_id,
                    session.project,
                    json.dumps(session.history),
                    session.created_at,
                    session.updated_at,
                ),
            )

    def clear(self, user_id: int) -> None:
        """Clear the session for *user_id* (reset history and project)."""
        session = self._cache.pop(user_id, None)
        with self._connect() as conn:
            conn.execute(
                "UPDATE sessions SET history = '[]', project = NULL, updated_at = ? "
                "WHERE user_id = ?",
                (time.time(), user_id),
            )


# ── Rate limiting ─────────────────────────────────────────────────────────────


class RateLimiter:
    """Sliding-window per-user rate limiter (in-memory)."""

    def __init__(self, messages_per_minute: int = 30) -> None:
        self._limit = messages_per_minute
        self._window = 60.0  # seconds
        self._timestamps: Dict[int, Deque[float]] = defaultdict(deque)

    def is_allowed(self, user_id: int) -> bool:
        """Return True if *user_id* is within the rate limit."""
        now = time.time()
        window_start = now - self._window
        dq = self._timestamps[user_id]

        # Drop events outside the sliding window.
        while dq and dq[0] < window_start:
            dq.popleft()

        if len(dq) >= self._limit:
            return False

        dq.append(now)
        return True

    def seconds_until_reset(self, user_id: int) -> float:
        """Return approximate seconds until the user's limit resets."""
        dq = self._timestamps.get(user_id)
        if not dq:
            return 0.0
        window_start = time.time() - self._window
        oldest = dq[0]
        return max(0.0, oldest - window_start)


# ── File helpers ──────────────────────────────────────────────────────────────


def safe_filename(name: str) -> str:
    """Strip path traversal and shell metacharacters from a filename."""
    name = Path(name).name  # drop any directory component
    name = re.sub(r"[^\w.\-]", "_", name)
    return name or "file"


# ── Text helpers ───────────────────────────────────────────────────────────────


def truncate(text: str, max_chars: int = 200, suffix: str = "…") -> str:
    """Return *text* truncated to *max_chars*, appending *suffix* if cut."""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - len(suffix)] + suffix
