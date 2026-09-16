import unittest

from backend.src.services.graph_query import format_graph_evidence, graph_query
from backend.src.services.graph_service import GraphService


class FakeSession:
    def __init__(self):
        self.query = ""
        self.params = {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return None

    def run(self, query, **params):
        self.query = query
        self.params = params
        return [{"source": "张三", "relation": "负责", "target": "项目A"}]


class FakeDriver:
    def __init__(self):
        self.fake_session = FakeSession()

    def session(self):
        return self.fake_session


class GraphServiceTests(unittest.TestCase):
    def test_query_is_parameterized_and_scoped_to_knowledge_base(self):
        query, params = graph_query("它们有什么关系", "kb-1")
        self.assertIn("$kb_id", query)
        self.assertNotIn("kb-1", query)
        self.assertEqual(params["kb_id"], "kb-1")

    def test_graph_record_is_normalized_as_evidence(self):
        evidence = format_graph_evidence(
            {"source": "张三", "relation": "负责", "target": "项目A"},
            index=2,
        )
        self.assertEqual(evidence["id"], "graph_2")
        self.assertEqual(evidence["text"], "张三 -[负责]-> 项目A")
        self.assertEqual(evidence["source"], "知识图谱")
        self.assertEqual(evidence["type"], "graph")

    def test_search_passes_kb_scope_and_returns_evidence(self):
        service = GraphService()
        service._driver = FakeDriver()
        result = service.search("有什么关系", kb_id="kb-1")
        self.assertEqual(service._driver.fake_session.params, {"kb_id": "kb-1"})
        self.assertEqual(result[0]["text"], "张三 -[负责]-> 项目A")


if __name__ == "__main__":
    unittest.main()
