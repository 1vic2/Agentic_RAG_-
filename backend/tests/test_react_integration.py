import asyncio
import unittest
from unittest.mock import patch


class ReactIntegrationTests(unittest.TestCase):
    def test_deep_mode_uses_react_with_same_scope(self):
        from backend.src.main import _retrieve

        evidence = [{"id": "react", "source": "doc.txt", "text": "answer"}]
        with patch("backend.src.agent.react_agent.run_react", return_value=evidence) as react:
            with patch("backend.src.main.retriever.retrieve") as vector:
                result = asyncio.run(_retrieve("question", use_web=False, deep_mode=True, kb_id="kb-1"))
        self.assertEqual(result, evidence)
        self.assertEqual(react.call_args.kwargs["kb_id"], "kb-1")
        self.assertFalse(react.call_args.kwargs["use_web"])
        vector.assert_not_called()

    def test_react_failure_falls_back_to_vector(self):
        from backend.src.main import _retrieve

        with patch("backend.src.agent.react_agent.run_react", side_effect=RuntimeError("model unavailable")):
            with patch("backend.src.main.retriever.retrieve", return_value=[{"id": "fallback"}]) as vector:
                result = asyncio.run(_retrieve("question", use_web=False, deep_mode=True, kb_id="kb-1"))
        self.assertEqual(result, [{"id": "fallback"}])
        vector.assert_called_once_with("question", kb_id="kb-1")

    def test_deep_mode_does_not_run_contextual_retry_after_react(self):
        from backend.src.main import _retrieve

        with patch("backend.src.agent.react_agent.run_react", return_value=[{"id": "react"}]) as react:
            with patch("backend.src.main.retriever.retrieve") as vector:
                asyncio.run(_retrieve("它保留多久？", use_web=False, deep_mode=True, history="用户: 备份什么时候执行？", kb_id="kb-1", retry_retrieval=True))
        react.assert_called_once()
        vector.assert_not_called()


if __name__ == "__main__":
    unittest.main()
