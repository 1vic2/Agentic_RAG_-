import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.src.rag.embedder import BGEEmbeddingFunction


class ModelReadinessTests(unittest.TestCase):
    def test_warmup_failure_reports_error_without_exposing_exception(self):
        model = BGEEmbeddingFunction("nonexistent-local-model")
        with patch.object(model, "_load", side_effect=RuntimeError("private path and credential")):
            model.warmup()
        self.assertEqual(model.readiness, "error")
        self.assertNotIn("private path", str(model.readiness))

    def test_ready_endpoint_distinguishes_model_preheat_from_health(self):
        from backend.src.main import app
        from backend.src.rag.embedder import embedder

        client = TestClient(app)
        with patch.object(embedder, "_model", None), patch.object(embedder, "_warmup_error", None):
            self.assertEqual(client.get("/health").status_code, 200)
            response = client.get("/health/ready")
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json(), {"status": "warming", "embedding": "warming"})
        with patch.object(embedder, "_model", object()), patch.object(embedder, "_warmup_error", None):
            response = client.get("/health/ready")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"status": "ready", "embedding": "ready"})
        with patch.object(embedder, "_model", None), patch.object(embedder, "_warmup_error", "RuntimeError"):
            response = client.get("/health/ready")
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json(), {"status": "unavailable", "embedding": "error"})


if __name__ == "__main__":
    unittest.main()
