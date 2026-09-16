import unittest

from backend.src.agent.retry_policy import merge_evidence, retry_query


class RetryPolicyTests(unittest.TestCase):
    def test_disabled_or_unrelated_question_never_retries(self):
        history = "用户: 访问令牌有效期是多少？\n助手: 45分钟"
        self.assertIsNone(retry_query("它过期后怎么处理？", history, False, 10))
        self.assertIsNone(retry_query("备份保留多久？", history, True, 10))
        self.assertIsNone(retry_query("应该如何配置？", history, True, 10))
        self.assertIsNone(retry_query("其他平台保留多久？", history, True, 10))
        self.assertIsNone(retry_query("它过期后怎么处理？", "", True, 10))

    def test_time_budget_and_cancelled_request_skip_retry(self):
        history = "用户: 访问令牌有效期是多少？"
        self.assertIsNone(retry_query("它过期后怎么处理？", history, True, 3000))
        self.assertIsNone(retry_query("它过期后怎么处理？", history, True, 10, cancelled=True))

    def test_uses_only_latest_user_question_with_bounded_context(self):
        history = "用户: 不相关的旧问题\n助手: 不相关的回答\n用户: " + "密钥" * 130 + "如何轮换？\n助手: 90天"
        result = retry_query("它多久轮换？", history, True, 10)
        self.assertTrue(result.endswith(" 它多久轮换？"))
        self.assertNotIn("不相关的旧问题", result)
        self.assertLessEqual(len(result), 200 + 1 + len("它多久轮换？"))

    def test_merge_keeps_initial_order_deduplicates_and_caps_count(self):
        original = [{"id": "a", "text": "first"}, {"id": "b", "text": "second"}]
        extra = [{"id": "b", "text": "duplicate"}] + [{"id": str(i), "text": str(i)} for i in range(20)]
        merged = merge_evidence(original, extra, limit=8)
        self.assertEqual([row["id"] for row in merged], ["a", "b", "0", "1", "2", "3", "4", "5"])
        self.assertEqual(merged[1]["text"], "second")


if __name__ == "__main__":
    unittest.main()
