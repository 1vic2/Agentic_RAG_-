"""Request-local progress notifications for synchronous retrieval tools."""

import time
import asyncio
import threading
from collections.abc import Callable
from collections.abc import AsyncIterator, Awaitable
from typing import Any


def track_tool(tool: str, fn: Callable[[], list[dict]], emit: Callable[[dict], Any] | None = None, cancelled: threading.Event | None = None) -> list[dict]:
    if cancelled is not None and cancelled.is_set():
        return []
    if emit is None:
        return fn()
    start = time.perf_counter()
    emit({"stage": "start", "tool": tool})
    ok = False
    count = 0
    try:
        if cancelled is not None and cancelled.is_set():
            return []
        result = fn()
        count = len(result)
        ok = True
        return result
    finally:
        emit({"stage": "end", "tool": tool, "ok": ok, "count": count, "elapsed_ms": round((time.perf_counter() - start) * 1000)})


async def progress_events(work: Callable[[Callable[[dict], None], threading.Event], Awaitable[list[dict]]]) -> AsyncIterator[dict]:
    """Relay worker-thread notifications through a queue owned by this call."""

    queue: asyncio.Queue[dict] = asyncio.Queue()
    loop = asyncio.get_running_loop()
    cancelled = threading.Event()

    def emit(event: dict) -> None:
        if not cancelled.is_set() and not loop.is_closed():
            loop.call_soon_threadsafe(queue.put_nowait, event)

    task = asyncio.create_task(work(emit, cancelled))
    try:
        while not task.done() or not queue.empty():
            try:
                yield await asyncio.wait_for(queue.get(), timeout=0.05)
            except asyncio.TimeoutError:
                continue
        result = await task
        await asyncio.sleep(0)  # flush notifications scheduled just before worker completion
        while not queue.empty():
            yield queue.get_nowait()
        yield {"stage": "result", "result": result}
    finally:
        cancelled.set()
        if not task.done():
            task.cancel()
