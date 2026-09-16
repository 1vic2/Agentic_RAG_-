import asyncio
import threading
import unittest
from unittest.mock import patch

from backend.src.models import QueryRequest


class RetryIntegrationTests(unittest.TestCase):
    def test_request_defaults_to_one_retrieval(self):
        from backend.src.main import _retrieve
        self.assertFalse(QueryRequest(question="它多久轮换？").retry_retrieval)
        with patch("backend.src.main.retriever.retrieve", return_value=[{"id": "first"}]) as lookup:
            result = asyncio.run(_retrieve("它多久轮换？", use_web=False, history="用户: 服务密钥如何轮换？", kb_id="demo"))
        self.assertEqual(result, [{"id": "first"}])
        lookup.assert_called_once_with("它多久轮换？", kb_id="demo")

    def test_opt_in_retries_once_in_same_kb_and_emits_tool_progress(self):
        from backend.src.main import _retrieve
        calls = []
        events = []

        def retrieve(q, kb_id):
            calls.append((q, kb_id))
            return [{"id": "first", "text": "original"}] if len(calls) == 1 else [{"id": "second", "text": "context"}]

        with patch("backend.src.main.retriever.retrieve", side_effect=retrieve):
            result = asyncio.run(_retrieve("它多久轮换？", use_web=False, history="用户: 服务密钥如何轮换？", kb_id="demo", retry_retrieval=True, progress=events.append))
        self.assertEqual(calls, [("它多久轮换？", "demo"), ("服务密钥如何轮换？ 它多久轮换？", "demo")])
        self.assertEqual([row["id"] for row in result], ["first", "second"])
        self.assertEqual([event["tool"] for event in events if event["stage"] == "start"], ["vector", "vector_retry"])

    def test_cancellation_after_first_lookup_skips_retry(self):
        from backend.src.main import _retrieve
        cancelled = threading.Event()

        def retrieve(q, kb_id):
            cancelled.set()
            return [{"id": "first"}]

        with patch("backend.src.main.retriever.retrieve", side_effect=retrieve) as lookup:
            asyncio.run(_retrieve("它多久轮换？", use_web=False, history="用户: 服务密钥如何轮换？", kb_id="demo", retry_retrieval=True, cancelled=cancelled))
        self.assertEqual(lookup.call_count, 1)

    def test_empty_retry_keeps_all_initial_deep_evidence(self):
        from backend.src.main import _retrieve
        original = [{"id": str(i)} for i in range(10)]
        with patch("backend.src.agent.react_agent.run_react", return_value=original):
            with patch("backend.src.main.retriever.retrieve", return_value=[]):
                result = asyncio.run(_retrieve("它保留多久？", use_web=False, deep_mode=True, history="用户: 备份什么时候执行？", kb_id="demo", retry_retrieval=True))
        self.assertEqual(result, original)


if __name__ == "__main__":
    unittest.main()
