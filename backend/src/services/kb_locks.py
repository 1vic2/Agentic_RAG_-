import threading


class KnowledgeBaseLock:
    def __init__(self, lock: threading.RLock):
        self.lock = lock

    def __enter__(self):
        self.lock.acquire()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.lock.release()


_locks: dict[str, threading.RLock] = {}
_locks_guard = threading.Lock()


def knowledge_base_lock(kb_id: str) -> KnowledgeBaseLock:
    with _locks_guard:
        lock = _locks.setdefault(kb_id, threading.RLock())
    return KnowledgeBaseLock(lock)
