"""Signals for a fixed QA corpus; none of these prove factual faithfulness."""

import re


_REFUSAL = re.compile(r"未提及|无法确定|没有足够|资料不足|不知道|not (?:mentioned|enough|available)", re.I)


def _normalized(text: str) -> str:
    return re.sub(r"[\s，。；、,:;.!?！？]+", "", str(text)).casefold()


def score_case(case: dict, answer: str, evidence: list[dict]) -> dict:
    expected = set(case.get("expected_sources", []))
    actual = {item.get("source", "") for item in evidence}
    required = [_normalized(item) for item in case.get("required_fragments", [case.get("reference", "")])]
    required = [item for item in required if item]
    refusal = bool(_REFUSAL.search(answer))
    return {
        "category": case["category"],
        "source_hit": expected.issubset(actual) if expected else None,
        "reference_match": all(item in _normalized(answer) for item in required) if required else None,
        "refusal_ok": refusal == bool(case["should_refuse"]),
        "evidence_count": len(evidence),
    }


def aggregate(rows: list[dict]) -> dict:
    categories: dict[str, dict] = {}
    timings: dict[str, list[int]] = {}
    for row in rows:
        group = categories.setdefault(row["category"], {key: {"passed": 0, "total": 0} for key in ("source_hit", "reference_match", "refusal_ok")})
        for key in group:
            if row.get(key) is not None:
                group[key]["total"] += 1
                group[key]["passed"] += int(bool(row[key]))
        if row.get("elapsed_ms") is not None:
            timings.setdefault(row["category"], []).append(row["elapsed_ms"])
    for category, group in categories.items():
        durations = timings.get(category, [])
        group["mean_elapsed_ms"] = round(sum(durations) / len(durations)) if durations else None
    return categories
