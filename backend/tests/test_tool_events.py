import json
import asyncio
import threading
import unittest
from contextlib import aclosing

from backend.src.services.sse_manager import sse
from backend.src.services.tool_progress import progress_events, track_tool
from backend.src.services.web_search import search_web


class ToolEventTests(unittest.TestCase):
    def test_events_carry_explicit_request_id(self):
        start = json.loads(sse.tool_start("a", "vector")["data"])
        end = json.loads(sse.tool_end("b", "graph", True, 2, 25)["data"])
        self.assertEqual(start["conversation_id"], "a")
        self.assertEqual(end["conversation_id"], "b")
        self.assertEqual(end["count"], 2)

    def test_tool_failure_still_emits_completed_error_event(self):
        events = []

        def failing():
            raise RuntimeError("private details")

        with self.assertRaises(RuntimeError):
            track_tool("web", failing, events.append)
        self.assertEqual([event["stage"] for event in events], ["start", "end"])
        self.assertFalse(events[-1]["ok"])
        self.assertNotIn("private details", str(events))

    def test_success_reports_result_count(self):
        events = []
        self.assertEqual(track_tool("vector", lambda: [{"id": "a"}], events.append), [{"id": "a"}])
        self.assertTrue(events[-1]["ok"])
        self.assertEqual(events[-1]["count"], 1)

    def test_web_failure_propagates_to_tool_error_event(self):
        class BrokenClient:
            def search(self, **kwargs):
                raise RuntimeError("rate limited")

        events = []
        with self.assertRaises(RuntimeError):
            track_tool("web", lambda: search_web("question", BrokenClient()), events.append)
        self.assertEqual(events[-1]["stage"], "end")
        self.assertFalse(events[-1]["ok"])


if __name__ == "__main__":
    unittest.main()


class ProgressQueueTests(unittest.IsolatedAsyncioTestCase):
    async def test_parallel_request_queues_do_not_share_tool_events(self):
        async def collect(name):
            async def work(emit, cancelled):
                def sync():
                    emit({"stage": "start", "tool": name})
                    emit({"stage": "end", "tool": name, "ok": True, "count": 1, "elapsed_ms": 1})
                    return [{"id": name}]
                return await asyncio.to_thread(sync)
            return [event async for event in progress_events(work)]

        a, b = await asyncio.gather(collect("vector"), collect("web"))
        self.assertEqual([event["tool"] for event in a[:-1]], ["vector", "vector"])
        self.assertEqual([event["tool"] for event in b[:-1]], ["web", "web"])
        self.assertEqual(a[-1]["result"], [{"id": "vector"}])

    async def test_closing_stream_skips_tools_that_have_not_started(self):
        gate = threading.Event()
        finished = threading.Event()
        second_started = threading.Event()

        async def work(emit, cancelled):
            def sync():
                emit({"stage": "start", "tool": "vector"})
                gate.wait(timeout=2)
                track_tool("web", lambda: second_started.set() or [], emit, cancelled=cancelled)
                finished.set()
                return []
            return await asyncio.to_thread(sync)

        async with aclosing(progress_events(work)) as events:
            self.assertEqual((await anext(events))["tool"], "vector")
        gate.set()
        self.assertTrue(await asyncio.to_thread(finished.wait, 2))
        self.assertFalse(second_started.is_set())
