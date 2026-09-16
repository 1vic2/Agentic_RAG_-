import threading
import unittest

from backend.src.agent.react_agent import parse_decision, run_react


class ReactAgentTests(unittest.TestCase):
    def test_decision_parser_accepts_only_allowlisted_tools(self):
        self.assertEqual(parse_decision('{"action":"tool","tool":"vector"}', {"vector"}, []), {"action": "tool", "tool": "vector"})
        self.assertEqual(parse_decision('{"action":"tool","tool":"web"}', {"vector"}, []), {"action": "tool", "tool": "vector"})
        self.assertEqual(parse_decision('{"action":"final"}', {"vector"}, ["vector"]), {"action": "final"})

    def test_react_loops_model_tool_observation_and_stops_on_final(self):
        decisions = iter(['{"action":"tool","tool":"vector"}', '{"action":"tool","tool":"graph"}', '{"action":"final"}'])
        calls = []

        def model(prompt):
            calls.append(prompt)
            return next(decisions)

        def tool(name, question, kb_id):
            return [{"id": name, "source": f"{kb_id}.txt", "text": name}]

        evidence = run_react("question", False, "kb-1", model=model, tool_runner=tool)
        self.assertEqual([item["id"] for item in evidence], ["vector", "graph"])
        self.assertEqual(len(calls), 3)

    def test_react_never_runs_more_than_three_tools_or_same_tool_twice(self):
        decisions = iter(['{"action":"tool","tool":"vector"}'] * 10)
        calls = []

        def model(_prompt):
            return next(decisions)

        def tool(name, question, kb_id):
            calls.append(name)
            return [{"id": str(len(calls))}]

        run_react("question", True, "kb-1", model=model, tool_runner=tool)
        self.assertLessEqual(len(calls), 3)
        self.assertEqual(calls, ["vector", "graph", "web"])

    def test_cancelled_request_does_not_start_tool(self):
        cancelled = threading.Event()
        cancelled.set()
        calls = []
        result = run_react("question", False, "kb-1", cancelled=cancelled, model=lambda _: '{"action":"tool","tool":"vector"}', tool_runner=lambda *args: calls.append(args) or [])
        self.assertEqual(result, [])
        self.assertEqual(calls, [])

    def test_caller_can_lower_maximum_tool_turns(self):
        calls = []
        run_react(
            "question", True, "kb-1", max_turns=1,
            model=lambda _: '{"action":"tool","tool":"vector"}',
            tool_runner=lambda name, *_: calls.append(name) or [{"id": name}],
        )
        self.assertEqual(calls, ["vector"])

    def test_tool_failure_keeps_previous_evidence_and_allows_final_decision(self):
        decisions = iter(['{"action":"tool","tool":"vector"}', '{"action":"tool","tool":"graph"}', '{"action":"final"}'])

        def tool(name, *_):
            if name == "graph":
                raise RuntimeError("neo4j unavailable")
            return [{"id": "kept", "source": "doc", "text": "evidence"}]

        result = run_react("question", False, "kb-1", model=lambda _: next(decisions), tool_runner=tool)
        self.assertEqual(result, [{"id": "kept", "source": "doc", "text": "evidence"}])


if __name__ == "__main__":
    unittest.main()
