import unittest
import json
from pathlib import Path

from evals.metrics import aggregate, score_case
from evals.run import run_cases


class EvaluationMetricTests(unittest.TestCase):
    def test_demo_corpus_has_30_valid_cases_and_real_source_files(self):
        root = Path(__file__).resolve().parents[2] / "evals"
        cases = json.loads((root / "questions.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(cases), 30)
        self.assertEqual(len({case["id"] for case in cases}), len(cases))
        for case in cases:
            self.assertTrue(case["question"])
            self.assertIn(case["category"], {"fact", "cross_document", "relation", "followup", "refusal"})
            self.assertIsInstance(case["should_refuse"], bool)
            for source in case["expected_sources"]:
                self.assertTrue((root / "fixtures" / source).is_file())
            if case["category"] == "cross_document":
                self.assertGreaterEqual(len(case["required_fragments"]), 2)

    def test_source_hit_uses_actual_returned_evidence(self):
        case = {"category": "fact", "expected_sources": ["policy.txt"], "reference": "每年 12 天", "should_refuse": False}
        hit = score_case(case, "年假每年 12 天。", [{"source": "policy.txt", "text": "年假每年 12 天"}])
        miss = score_case(case, "年假每年 12 天。", [{"source": "other.txt", "text": "无关"}])
        self.assertTrue(hit["source_hit"])
        self.assertFalse(miss["source_hit"])

    def test_cross_document_match_requires_both_answer_fragments(self):
        case = {"category": "cross_document", "expected_sources": ["platform.txt", "operations.txt"], "required_fragments": ["25秒", "4小时"], "should_refuse": False}
        self.assertFalse(score_case(case, "网关超时25秒。", [])["reference_match"])
        self.assertTrue(score_case(case, "网关超时25秒，恢复目标4小时。", [])["reference_match"])

    def test_refusal_and_reference_are_separate_signals(self):
        case = {"category": "refusal", "expected_sources": [], "reference": "", "should_refuse": True}
        result = score_case(case, "参考资料中未提及。", [])
        self.assertTrue(result["refusal_ok"])
        self.assertIsNone(result["reference_match"])

        answerable = {"category": "fact", "expected_sources": ["policy.txt"], "reference": "12天", "should_refuse": False}
        self.assertEqual(score_case(answerable, "参考资料中未提及。", [])["refusal_ok"], False)

    def test_aggregate_reports_categories_without_averaging_missing_values(self):
        rows = [
            {"category": "fact", "source_hit": True, "reference_match": False, "refusal_ok": None},
            {"category": "fact", "source_hit": False, "reference_match": True, "refusal_ok": None},
            {"category": "refusal", "source_hit": None, "reference_match": None, "refusal_ok": True},
        ]
        report = aggregate(rows)
        self.assertEqual(report["fact"]["source_hit"], {"passed": 1, "total": 2})
        self.assertEqual(report["refusal"]["refusal_ok"], {"passed": 1, "total": 1})
        self.assertEqual(report["refusal"]["reference_match"], {"passed": 0, "total": 0})

    def test_aggregate_reports_mean_latency_only_for_completed_cases(self):
        report = aggregate([
            {"category": "fact", "elapsed_ms": 10},
            {"category": "fact", "elapsed_ms": 30},
            {"category": "fact", "error": "timeout"},
        ])
        self.assertEqual(report["fact"]["mean_elapsed_ms"], 20)

    def test_live_runner_scopes_each_case_and_links_followup_turn(self):
        calls = []

        def transport(payload):
            calls.append(payload)
            return {"answer": "30天", "conversation_id": payload["conversation_id"], "evidence": [{"source": "operations.txt", "text": "备份保留30天"}]}

        cases = [{"id": "u02", "category": "followup", "preceding_question": "备份什么时候执行？", "question": "它保留多久？", "reference": "30天", "expected_sources": ["operations.txt"], "should_refuse": False}]
        rows = run_cases(cases, transport, kb_id="demo-kb", mode="quick")
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["conversation_id"], calls[1]["conversation_id"])
        self.assertEqual(calls[0]["kb_id"], "demo-kb")
        self.assertEqual(rows[0]["id"], "u02")
        self.assertTrue(rows[0]["source_hit"])

    def test_live_runner_can_compare_opt_in_retry_with_default(self):
        calls = []
        cases = [{"id": "f01", "category": "fact", "question": "Q", "reference": "A", "expected_sources": [], "should_refuse": False}]

        def transport(payload):
            calls.append(payload)
            return {"answer": "A", "evidence": []}

        run_cases(cases, transport, "demo", "quick")
        run_cases(cases, transport, "demo", "quick", retry_retrieval=True)
        self.assertEqual([call["retry_retrieval"] for call in calls], [False, True])

    def test_live_runner_does_not_score_generation_failures_as_answers(self):
        cases = [{"id": "f01", "category": "fact", "question": "Q", "reference": "A", "expected_sources": ["platform.txt"], "should_refuse": False}]
        rows = run_cases(cases, lambda payload: {"answer": "生成失败: 服务不可用", "evidence": [{"source": "platform.txt"}]}, "demo-kb", "quick")
        self.assertIn("error", rows[0])
        self.assertNotIn("source_hit", rows[0])

    def test_followup_is_not_scored_when_setup_question_failed(self):
        calls = []
        cases = [{"id": "u02", "category": "followup", "preceding_question": "备份在哪？", "question": "它保留多久？", "reference": "30天", "expected_sources": ["operations.txt"], "should_refuse": False}]

        def transport(payload):
            calls.append(payload)
            return {"answer": "生成失败: 模型不可用", "evidence": []}

        rows = run_cases(cases, transport, "demo-kb", "quick")
        self.assertEqual(len(calls), 1)
        self.assertIn("error", rows[0])
        self.assertNotIn("reference_match", rows[0])


if __name__ == "__main__":
    unittest.main()
