import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


class SessionStore:
    """Small SQLite-backed conversation history store.

    A connection is opened per operation so FastAPI worker threads do not share
    mutable connection state. SQLite serializes the short writes for us.
    """

    def __init__(self, db_path: str | Path = "data/sessions.sqlite3"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_schema(self) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    evidence_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_conversation "
                "ON messages(conversation_id, id)"
            )
            connection.commit()

    def append(
        self,
        conversation_id: str,
        role: str,
        content: str,
        evidence: list[dict] | None = None,
    ) -> None:
        if role not in {"user", "assistant"}:
            raise ValueError(f"unsupported message role: {role}")
        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO messages
                    (conversation_id, role, content, evidence_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    conversation_id,
                    role,
                    content,
                    json.dumps(evidence or [], ensure_ascii=False),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            connection.commit()

    def recent(self, conversation_id: str, limit: int = 8) -> list[dict]:
        if limit <= 0:
            return []
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT role, content, evidence_json, created_at
                FROM messages
                WHERE conversation_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (conversation_id, limit),
            ).fetchall()
        return [
            {
                "role": row["role"],
                "content": row["content"],
                "evidence": json.loads(row["evidence_json"]),
                "created_at": row["created_at"],
            }
            for row in reversed(rows)
        ]


def format_history(messages: list[dict], max_chars: int = 6000) -> str:
    """Format the newest complete chat history within a character budget."""

    if max_chars <= 0:
        return ""
    labels = {"user": "用户", "assistant": "助手"}
    lines = [
        f"{labels.get(message.get('role', ''), message.get('role', ''))}: "
        f"{str(message.get('content', '')).strip()}"
        for message in messages
        if str(message.get("content", "")).strip()
    ]
    selected: list[str] = []
    used = 0
    for line in reversed(lines):
        separator = 1 if selected else 0
        available = max_chars - used - separator
        if available <= 0:
            break
        if len(line) > available:
            if not selected:
                selected.append(line[-available:])
            break
        selected.append(line)
        used += len(line) + separator
    return "\n".join(reversed(selected))
