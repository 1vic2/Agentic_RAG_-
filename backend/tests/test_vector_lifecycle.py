import unittest

from backend.src.rag.store import VectorStore
from backend.src.rag.vector_ids import document_chunk_id


class Vectors(list):
    def tolist(self):
        return list(self)


class FakeCollection:
    def __init__(self):
        self.items = {}
        self.fail_upsert = False
        self.fail_delete = False

    def count(self):
        return len(self.items)

    def upsert(self, ids, embeddings, documents, metadatas):
        if self.fail_upsert:
            raise RuntimeError("write failed")
        for item_id, embedding, document, metadata in zip(ids, embeddings, documents, metadatas):
            self.items[item_id] = {
                "embedding": embedding,
                "document": document,
                "metadata": metadata,
            }

    def get(self, where=None, limit=None, offset=0, include=None):
        def matches(metadata, condition):
            if not condition:
                return True
            if "$and" in condition:
                return all(matches(metadata, child) for child in condition["$and"])
            return all(metadata.get(key) == value for key, value in condition.items())

        ids = [item_id for item_id, item in self.items.items() if matches(item["metadata"], where)]
        ids = ids[offset : offset + limit if limit is not None else None]
        return {"ids": ids, "metadatas": [self.items[item_id]["metadata"] for item_id in ids]}

    def delete(self, ids):
        if self.fail_delete:
            raise RuntimeError("delete failed")
        for item_id in ids:
            self.items.pop(item_id, None)


class VectorLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.store = VectorStore("test")
        self.store._col = FakeCollection()

    def test_stable_chunk_ids_are_repeatable_and_content_sensitive(self):
        first = document_chunk_id("kb", "a.txt", 0, "hello")
        self.assertEqual(first, document_chunk_id("kb", "a.txt", 0, "hello"))
        self.assertNotEqual(first, document_chunk_id("kb", "a.txt", 0, "changed"))

    def test_reindex_replaces_old_chunks_instead_of_appending(self):
        self.store.replace_documents(
            ["old one", "old two"],
            ["a.txt", "a.txt"],
            Vectors([[1.0], [2.0]]),
            kb_id="kb",
        )
        self.store.replace_documents(
            ["new one"],
            ["a.txt"],
            Vectors([[3.0]]),
            kb_id="kb",
        )
        self.assertEqual(self.store.count(), 1)
        item = next(iter(self.store._col.items.values()))
        self.assertEqual(item["document"], "new one")
        self.assertEqual(item["metadata"]["type"], "document")
        self.assertEqual(item["metadata"]["chunk_index"], 0)

    def test_reindexing_one_source_preserves_other_sources(self):
        self.store.replace_documents(
            ["a", "b"],
            ["a.txt", "b.txt"],
            Vectors([[1.0], [2.0]]),
            kb_id="kb",
        )
        self.store.replace_documents(
            ["new a"],
            ["a.txt"],
            Vectors([[3.0]]),
            kb_id="kb",
        )
        self.assertEqual(
            {item["metadata"]["source"] for item in self.store._col.items.values()},
            {"a.txt", "b.txt"},
        )

    def test_delete_document_removes_only_matching_source(self):
        self.store.replace_documents(
            ["a", "b"],
            ["a.txt", "b.txt"],
            Vectors([[1.0], [2.0]]),
            kb_id="kb",
        )
        self.store.delete_document("kb", "a.txt")
        self.assertEqual(
            [item["metadata"]["source"] for item in self.store._col.items.values()],
            ["b.txt"],
        )

    def test_reindex_removes_legacy_record_without_kb_id(self):
        self.store._col.items["legacy"] = {
            "embedding": [0.0],
            "document": "legacy text",
            "metadata": {"source": "a.txt"},
        }
        self.store.replace_documents(
            ["new text"],
            ["a.txt"],
            Vectors([[1.0]]),
            kb_id="kb",
        )
        self.assertNotIn("legacy", self.store._col.items)
        self.assertEqual(self.store.count(), 1)

    def test_delete_document_removes_legacy_record_for_source(self):
        self.store._col.items["legacy"] = {
            "embedding": [0.0],
            "document": "legacy text",
            "metadata": {"source": "a.txt"},
        }
        self.store.delete_document("kb", "a.txt")
        self.assertEqual(self.store.count(), 0)

    def test_failed_upsert_preserves_old_record(self):
        self.store.replace_documents(
            ["old text"],
            ["a.txt"],
            Vectors([[1.0]]),
            kb_id="kb",
        )
        old_ids = set(self.store._col.items)
        self.store._col.fail_upsert = True
        with self.assertRaises(RuntimeError):
            self.store.replace_documents(
                ["new text"],
                ["a.txt"],
                Vectors([[2.0]]),
                kb_id="kb",
            )
        self.assertEqual(set(self.store._col.items), old_ids)

    def test_knowledge_base_delete_surfaces_cleanup_failure(self):
        self.store.replace_documents(
            ["text"],
            ["a.txt"],
            Vectors([[1.0]]),
            kb_id="kb",
        )
        self.store._col.fail_delete = True
        with self.assertRaises(RuntimeError):
            self.store.delete_by_kb("kb")


if __name__ == "__main__":
    unittest.main()
