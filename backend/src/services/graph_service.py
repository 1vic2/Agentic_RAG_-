import logging

from backend.src.services.graph_query import format_graph_evidence, graph_query

logger = logging.getLogger(__name__)


class GraphService:
    def __init__(self):
        self._driver = None

    def _connect(self):
        if self._driver:
            return
        from backend.src.config import settings
        from neo4j import GraphDatabase
        self._driver = GraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password))
        self._driver.verify_connectivity()

    def save(self, kb_id: str, nodes: list[dict], edges: list[dict]):
        if not nodes and not edges:
            return
        self._connect()
        with self._driver.session() as s:
            if nodes:
                s.run("UNWIND $ns AS n MERGE (e:Entity {text: n.id, kb_id: $kb}) SET e.label = n.label, e.group = n.group", ns=nodes, kb=kb_id)
            if edges:
                es = [{"src": e["source"], "dst": e["target"], "lbl": e.get("label", "")} for e in edges]
                s.run("UNWIND $es AS e MATCH (a:Entity {text: e.src, kb_id: $kb}) MATCH (b:Entity {text: e.dst, kb_id: $kb}) MERGE (a)-[r:RELATION {type: e.lbl, kb_id: $kb}]->(b)", es=es, kb=kb_id)

    def search(self, q: str, kb_id: str = "", k: int = 10) -> list[dict]:
        self._connect()
        cypher, params = graph_query(q, kb_id)
        try:
            with self._driver.session() as s:
                records = list(s.run(cypher, **params))[:k]
                return [format_graph_evidence(dict(record), i) for i, record in enumerate(records)]
        except Exception as e:
            logger.warning(f"Cypher fail: {e}")
            return []

    def delete(self, kb_id: str):
        self._connect()
        with self._driver.session() as s:
            s.run("MATCH (e:Entity {kb_id: $kb}) DETACH DELETE e", kb=kb_id)

    def close(self):
        if self._driver:
            self._driver.close()
            self._driver = None


graph = GraphService()


# app 关闭时自动释放 Neo4j 连接
async def close_graph():
    graph.close()
