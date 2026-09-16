import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from backend.src.rag.vector_ids import document_chunk_id

if TYPE_CHECKING:
    from numpy import ndarray
else:
    ndarray = Any

CHROMA_DIR = Path("data/chroma")

# ChromaDB 单次插入上限，留安全余量
MAX_BATCH_SIZE = 500


class VectorStore:
    def __init__(self, name: str | None = None):
        self.name = name
        self._col = None

    def load(self):
        if self._col:
            return
        if self.name is None:
            from backend.src.config import settings
            self.name = settings.chroma_collection
        import chromadb
        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        cli = chromadb.PersistentClient(path=str(CHROMA_DIR))
        try:
            self._col = cli.get_collection(self.name)
        except Exception:
            self._col = cli.create_collection(self.name, metadata={"hnsw:space": "ip"})

    def replace_documents(self, texts: list[str], sources: list[str], dv: ndarray, kb_id: str = ""):
        """Upsert prepared chunks and remove stale chunks for the same sources.

        All parsing and embedding happens before this method is called. New
        records are written before stale records are removed, so a failed
        write does not erase the previously usable index.
        """

        self.load()
        embeddings = dv.tolist()
        if not (len(texts) == len(sources) == len(embeddings)):
            raise ValueError("texts, sources and embeddings must have equal lengths")

        source_indexes: dict[str, int] = {}
        chunk_indexes = []
        for source in sources:
            chunk_indexes.append(source_indexes.get(source, 0))
            source_indexes[source] = source_indexes.get(source, 0) + 1
        ids = [
            document_chunk_id(kb_id, source, chunk_index, text)
            for text, source, chunk_index in zip(texts, sources, chunk_indexes)
        ]
        meta = [
            {
                "source": source,
                "kb_id": kb_id,
                "type": "document",
                "chunk_index": chunk_index,
            }
            for source, chunk_index in zip(sources, chunk_indexes)
        ]

        old_by_source = self._document_ids_by_source(kb_id, set(sources))

        for i in range(0, len(texts), MAX_BATCH_SIZE):
            end = min(i + MAX_BATCH_SIZE, len(texts))
            self._col.upsert(
                ids=ids[i:end],
                embeddings=embeddings[i:end],
                documents=texts[i:end],
                metadatas=meta[i:end],
            )

        new_by_source: dict[str, set[str]] = {}
        for item_id, source in zip(ids, sources):
            new_by_source.setdefault(source, set()).add(item_id)
        for source, old_ids in old_by_source.items():
            stale_ids = list(old_ids - new_by_source.get(source, set()))
            if stale_ids:
                self._col.delete(ids=stale_ids)

    def insert(self, texts: list[str], sources: list[str], dv: ndarray, kb_id: str = ""):
        """Backward-compatible alias for document replacement."""

        self.replace_documents(texts, sources, dv, kb_id=kb_id)

    def delete_document(self, kb_id: str, source: str) -> None:
        self.load()
        ids = list(self._document_ids_by_source(kb_id, {source}).get(source, set()))
        for index in range(0, len(ids), MAX_BATCH_SIZE):
            self._col.delete(ids=ids[index:index + MAX_BATCH_SIZE])

    def _document_ids_by_source(self, kb_id: str, sources: set[str]) -> dict[str, set[str]]:
        """Find current and legacy document records for selected sources.

        Older versions stored only the source name. Those records are claimed
        by the first explicit rebuild/delete for that source so they cannot
        remain globally searchable forever.
        """

        found = {source: set() for source in sources}
        if not sources:
            return found
        records = self._col.get(include=["metadatas"])
        for item_id, metadata in zip(records.get("ids", []), records.get("metadatas", [])):
            source = metadata.get("source", "")
            if source not in sources or metadata.get("type") == "entity":
                continue
            record_kb_id = metadata.get("kb_id")
            if record_kb_id == kb_id or not record_kb_id:
                found[source].add(item_id)
        return found

    def delete_entities(self, kb_id: str) -> None:
        self.load()
        while True:
            batch = self._col.get(
                where={"$and": [{"kb_id": kb_id}, {"type": "entity"}]},
                limit=MAX_BATCH_SIZE,
            )
            ids = batch.get("ids", [])
            if not ids:
                break
            self._col.delete(ids=ids)
            if len(ids) < MAX_BATCH_SIZE:
                break

    def search_dense(self, qv: ndarray, k: int = 10, filter_: dict | None = None, kb_id: str = "") -> list[dict]:
        self.load()
        kw = {"query_embeddings": qv.tolist(), "n_results": k}
        # ChromaDB where 只能有一个顶层操作符，多条件必须用 $and 包裹
        conditions = []
        if filter_:
            conditions.append(filter_)
        if kb_id:
            conditions.append({"kb_id": kb_id})
        if conditions:
            kw["where"] = {"$and": conditions} if len(conditions) > 1 else conditions[0]
        r = self._col.query(**kw)
        return [
                {"id": r["ids"][0][i],
                "score": r["distances"][0][i],
                "text": r["documents"][0][i],
                "source": r["metadatas"][0][i].get("source", ""),
                "kb_id": r["metadatas"][0][i].get("kb_id", ""),
                "type": r["metadatas"][0][i].get("type", "document"),
                }
                for i in range(len(r["ids"][0]))]

    def count(self) -> int:
        self.load()
        return self._col.count()

    def delete_by_kb(self, kb_id: str):
        """删除指定知识库的所有向量"""
        self.load()
        while True:
            batch = self._col.get(where={"kb_id": kb_id}, limit=MAX_BATCH_SIZE)
            ids = batch["ids"]
            if not ids:
                break
            self._col.delete(ids=ids)
            if len(ids) < MAX_BATCH_SIZE:
                break
        logger.info(f"已删除知识库 {kb_id} 的向量")

    def clear(self):
        """清空当前集合的所有数据（用于重新索引）"""
        self.load()
        if self._col.count() > 0:
            all_ids = self._col.get()["ids"]
            # 分批删除
            for i in range(0, len(all_ids), MAX_BATCH_SIZE):
                self._col.delete(ids=all_ids[i:i + MAX_BATCH_SIZE])


logger = logging.getLogger(__name__)

vector_store = VectorStore()
