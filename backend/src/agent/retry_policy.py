"""Deterministic, opt-in contextual retrieval for short referential follow-ups."""

import re

_REFERENTIAL = re.compile(r"它|这个|那个|上述|(?<!应)该|其(?!他|中|实)|前者|后者|这些|那项")
_ELIGIBILITY_MS = 3000


def retry_query(question: str, history: str, enabled: bool, elapsed_ms: float, cancelled: bool = False) -> str | None:
    if not enabled or cancelled or elapsed_ms >= _ELIGIBILITY_MS:
        return None
    current = question.strip()
    if not current or len(current) > 120 or not _REFERENTIAL.search(current):
        return None
    previous = [line.removeprefix("用户: ").strip() for line in history.splitlines() if line.startswith("用户: ")]
    if not previous:
        return None
    context = previous[-1][:200]
    return f"{context} {current}" if context and context != current else None


def merge_evidence(original: list[dict], additional: list[dict], limit: int = 8) -> list[dict]:
    merged: list[dict] = []
    seen: set[str] = set()
    for item in original + additional:
        key = item.get("id") or f"{item.get('source', '')}\0{item.get('text', '')}"
        if key not in seen:
            seen.add(key)
            merged.append(item)
            if len(merged) >= limit:
                break
    return merged
