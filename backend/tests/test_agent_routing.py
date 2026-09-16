import unittest

from backend.src.agent.routing import next_step, sanitize_routes


class AgentRoutingTests(unittest.TestCase):
    def test_every_planned_tool_is_visited(self):
        for routes in (["vector"], ["vector", "web"], ["vector", "graph", "web"]):
            idx = 0
            visited = []
            while True:
                visited.append(routes[idx])
                idx += 1
                if next_step(idx, routes) == "end":
                    break
            self.assertEqual(visited, routes)

    def test_routes_are_filtered_deduplicated_and_ordered(self):
        self.assertEqual(
            sanitize_routes(["web", "vector", "web", 1, "graph"], {"vector", "graph"}),
            ["vector", "graph"],
        )

    def test_non_list_or_empty_route_falls_back_to_vector(self):
        self.assertEqual(sanitize_routes("web", {"vector", "web"}), ["vector"])
        self.assertEqual(sanitize_routes([], {"vector", "web"}), ["vector"])

    def test_web_cannot_be_selected_when_disallowed(self):
        self.assertEqual(sanitize_routes(["web"], {"vector", "graph"}), ["vector"])


if __name__ == "__main__":
    unittest.main()
