import json
import tempfile
import unittest
from pathlib import Path

from backend.src.services.session_service import SessionStore, format_history
from backend.src.services.sse_manager import sse


class SessionStoreTests(unittest.TestCase):
    def test_sessions_persist_and_remain_isolated(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "sessions.db"
            store = SessionStore(db_path)
            store.append("a", "user", "question a")
            store.append("a", "assistant", "answer a", [{"id": "1"}])
            store.append("b", "user", "question b")

            reopened = SessionStore(db_path)
            self.assertEqual(
                [m["content"] for m in reopened.recent("a")],
                ["question a", "answer a"],
            )
            self.assertEqual(
                [m["content"] for m in reopened.recent("b")],
                ["question b"],
            )
            self.assertEqual(reopened.recent("a")[-1]["evidence"], [{"id": "1"}])

    def test_recent_returns_last_messages_in_chronological_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SessionStore(Path(tmp) / "sessions.db")
            for i in range(5):
                store.append("a", "user", str(i))
            self.assertEqual([m["content"] for m in store.recent("a", limit=2)], ["3", "4"])

    def test_history_contains_both_roles_and_obeys_character_limit(self):
        history = format_history(
            [
                {"role": "user", "content": "first question"},
                {"role": "assistant", "content": "first answer"},
                {"role": "user", "content": "latest question"},
            ],
            max_chars=40,
        )
        self.assertIn("用户: latest question", history)
        self.assertNotIn("first question", history)
        self.assertLessEqual(len(history), 40)


class SSEManagerTests(unittest.TestCase):
    def test_done_uses_explicit_conversation_id(self):
        sse.start("other")
        payload = json.loads(sse.done("a", "answer", [])["data"])
        self.assertEqual(payload["conversation_id"], "a")


if __name__ == "__main__":
    unittest.main()
