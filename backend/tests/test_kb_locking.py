import threading
import time
import unittest

from backend.src.services.kb_locks import knowledge_base_lock


class KnowledgeBaseLockTests(unittest.TestCase):
    def test_same_knowledge_base_mutations_are_serialized(self):
        active = 0
        max_active = 0
        guard = threading.Lock()

        def mutate():
            nonlocal active, max_active
            with knowledge_base_lock("kb"):
                with guard:
                    active += 1
                    max_active = max(max_active, active)
                time.sleep(0.02)
                with guard:
                    active -= 1

        threads = [threading.Thread(target=mutate) for _ in range(3)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(max_active, 1)

    def test_different_knowledge_bases_do_not_share_a_lock(self):
        self.assertIsNot(knowledge_base_lock("a").lock, knowledge_base_lock("b").lock)


if __name__ == "__main__":
    unittest.main()
