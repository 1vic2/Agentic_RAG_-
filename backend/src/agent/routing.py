from collections.abc import Iterable
from typing import Any


def sanitize_routes(raw: Any, allowed: Iterable[str]) -> list[str]:
    """Return a safe, ordered tool plan for this request."""

    allowed_set = set(allowed)
    routes: list[str] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str) and item in allowed_set and item not in routes:
                routes.append(item)
    if routes:
        return routes
    if "vector" in allowed_set:
        return ["vector"]
    return [next(iter(sorted(allowed_set)))] if allowed_set else []


def next_step(idx: int, routes: list[str]) -> str:
    """Choose the next LangGraph edge after idx has been incremented."""

    return "run" if idx < len(routes) else "end"
