import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.src.services import kb_service


class DocumentPathTests(unittest.TestCase):
    def test_safe_document_path_accepts_plain_filename(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(kb_service, "KB_ROOT", Path(tmp)):
            expected = (Path(tmp) / "kb" / "documents" / "file.txt").resolve()
            self.assertEqual(kb_service.safe_document_path("kb", "file.txt"), expected)

    def test_safe_document_path_rejects_parent_escape(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(kb_service, "KB_ROOT", Path(tmp)):
            with self.assertRaises(ValueError):
                kb_service.safe_document_path("kb", "../outside.txt")

    def test_safe_document_path_rejects_nested_path(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(kb_service, "KB_ROOT", Path(tmp)):
            with self.assertRaises(ValueError):
                kb_service.safe_document_path("kb", "nested/file.txt")


if __name__ == "__main__":
    unittest.main()
