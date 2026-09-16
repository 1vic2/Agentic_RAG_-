from collections.abc import Mapping
from typing import Any


def graph_query(question: str, kb_id: str = "") -> tuple[str, dict[str, str]]:
    """Build a parameterized, knowledge-base-scoped graph query."""

    question_lower = question.lower()
    params = {"kb_id": kb_id}
    scope = "($kb_id = '' OR n.kb_id = $kb_id)"
    relation_scope = "($kb_id = '' OR (a.kb_id = $kb_id AND b.kb_id = $kb_id))"
    if any(word in question_lower for word in ["所有", "全部", "列出"]):
        return (
            "MATCH (n:Entity) "
            f"WHERE {scope} "
            "RETURN n.text AS source, coalesce(n.label, '实体') AS relation, "
            "'' AS target LIMIT 50",
            params,
        )
    return (
        "MATCH (a:Entity)-[r:RELATION]->(b:Entity) "
        f"WHERE {relation_scope} "
        "RETURN a.text AS source, r.type AS relation, b.text AS target LIMIT 50",
        params,
    )


def format_graph_evidence(record: Mapping[str, Any], index: int) -> dict:
    source = str(record.get("source") or "未知实体")
    relation = str(record.get("relation") or "相关")
    target = str(record.get("target") or "")
    text = f"{source} -[{relation}]-> {target}" if target else f"{source}（{relation}）"
    return {
        "id": f"graph_{index}",
        "text": text,
        "source": "知识图谱",
        "score": 1.0,
        "type": "graph",
    }
