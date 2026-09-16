import hashlib


def document_chunk_id(kb_id: str, source: str, chunk_index: int, text: str) -> str:
    """Build a deterministic ID scoped to one knowledge base and source."""

    payload = f"{kb_id}\0{source}\0{chunk_index}\0{text}".encode("utf-8")
    return f"doc_{hashlib.sha256(payload).hexdigest()[:32]}"
