import asyncio
import shutil
import time
from contextlib import aclosing, asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from httpx import Client
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from sse_starlette.sse import EventSourceResponse

from backend.src.config import settings
from backend.src.agent.retry_policy import merge_evidence, retry_query
from backend.src.models import CreateKBRequest, QueryRequest
from backend.src.rag.retriever import retriever
from backend.src.services import kb_service
from backend.src.services.index_service import index_kb
from backend.src.services.kb_locks import knowledge_base_lock
from backend.src.services.session_service import SessionStore, format_history
from backend.src.services.tool_progress import progress_events, track_tool
from backend.src.services.web_search import search_web
from backend.src.services.sse_manager import sse
from backend.src.utils.helpers import get_logger

logger = get_logger(__name__)
session_store = SessionStore()


@asynccontextmanager
async def lifespan(_: FastAPI):
    import asyncio
    from backend.src.rag.embedder import embedder
    asyncio.create_task(asyncio.to_thread(embedder.warmup))
    logger.info(f"启动 {settings.host}:{settings.port}")
    yield
    from backend.src.services.graph_service import close_graph
    await close_graph()


app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/health/ready")
def health_ready():
    from backend.src.rag.embedder import embedder
    state = embedder.readiness
    return JSONResponse(
        status_code=200 if state == "ready" else 503,
        content={"status": "ready" if state == "ready" else "unavailable" if state == "error" else "warming", "embedding": state},
    )


@app.post("/query")
async def query(req: QueryRequest):
    sid = req.conversation_id or str(uuid4())
    history = format_history(session_store.recent(sid))
    session_store.append(sid, "user", req.question)
    ev = await _retrieve(req.question, req.use_web, req.deep_mode, history, kb_id=req.kb_id, retry_retrieval=req.retry_retrieval)
    ans = await asyncio.to_thread(_generate, req.question, ev, history)
    session_store.append(sid, "assistant", ans, ev)
    return {"answer": ans, "conversation_id": sid, "evidence": ev}


@app.post("/query/stream")
async def query_stream(req: QueryRequest, request: Request):
    sid = req.conversation_id or str(uuid4())

    async def gen():
        if await request.is_disconnected():
            return
        yield sse.start(sid)
        history = format_history(session_store.recent(sid))
        session_store.append(sid, "user", req.question)
        ev: list[dict] = []
        ans = ""
        assistant_saved = False
        try:
            yield sse.status("检索中…")
            async with aclosing(progress_events(
                lambda emit, cancelled: _retrieve(req.question, req.use_web, req.deep_mode, history, kb_id=req.kb_id, progress=emit, cancelled=cancelled, retry_retrieval=req.retry_retrieval)
            )) as events:
                async for event in events:
                    if event["stage"] == "start":
                        yield sse.tool_start(sid, event["tool"])
                    elif event["stage"] == "end":
                        yield sse.tool_end(sid, event["tool"], event["ok"], event["count"], event["elapsed_ms"])
                    else:
                        ev = event["result"]
            if await request.is_disconnected():
                cancelled_answer = _cancelled_answer(ans)
                session_store.append(sid, "assistant", cancelled_answer, ev)
                return
            yield sse.status("生成回答…")
            llm, msg = _build_llm(True), _build_msg(req.question, ev, history)
            async for c in llm.astream(msg):
                if await request.is_disconnected():
                    cancelled_answer = _cancelled_answer(ans)
                    session_store.append(sid, "assistant", cancelled_answer, ev)
                    return
                if t := c.content or "":
                    ans += t
                    yield sse.token(t)
            session_store.append(sid, "assistant", ans, ev)
            assistant_saved = True
            yield sse.done(sid, ans, ev)
        except asyncio.CancelledError:
            if not assistant_saved:
                session_store.append(sid, "assistant", _cancelled_answer(ans), ev)
            raise
        except Exception as e:
            logger.error(f"stream fail: {e}")
            ans = f"生成失败: {e}"
            session_store.append(sid, "assistant", ans, ev)
            yield sse.error(str(e))
            yield sse.done(sid, ans, ev)

    return EventSourceResponse(gen())


def _cancelled_answer(partial: str) -> str:
    return f"{partial}\n\n已停止生成" if partial else "已停止生成"


def _web_search(q: str) -> list[dict]:
    from tavily import TavilyClient
    return search_web(q, TavilyClient(api_key=settings.tavily_api_key))

async def _retrieve(q: str, use_web: bool = True, deep_mode: bool = False, history: str = "", kb_id: str = "", progress=None, cancelled=None, retry_retrieval: bool = False) -> list[dict]:
    import asyncio
    def _sync():
        started = time.perf_counter()
        ev = None
        if deep_mode:
            from backend.src.agent.react_agent import run_react
            try:
                ev = run_react(q, use_web=use_web, kb_id=kb_id, progress=progress, cancelled=cancelled)
            except Exception as e:
                logger.warning("ReAct agent fail (%s), falling back to vector retrieval", type(e).__name__)
        if ev is None:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            tasks, ev = {"vector": lambda: retriever.retrieve(q, kb_id=kb_id)}, []
            if use_web and settings.tavily_api_key:
                tasks["web"] = lambda: _web_search(q)
            with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
                for f in as_completed([pool.submit(track_tool, name, task, progress, cancelled) for name, task in tasks.items()]):
                    try:
                        ev.extend(f.result())
                    except Exception as e:
                        logger.warning(f"retrieve fail: {e}")
        followup = retry_query(q, history, retry_retrieval and not deep_mode, (time.perf_counter() - started) * 1000, cancelled is not None and cancelled.is_set())
        if followup:
            try:
                additional = track_tool("vector_retry", lambda: retriever.retrieve(followup, kb_id=kb_id), progress, cancelled)
                if additional:
                    ev = merge_evidence(ev, additional)
            except Exception as e:
                logger.warning("vector retry fail: %s", type(e).__name__)
        return ev
    return await asyncio.to_thread(_sync)


def _build_msg(q: str, ev: list[dict], history: str = "") -> list:
    sp = (
        '你是一个知识库问答助手。严格按以下规则回答：\n'
        '1. 严格依据参考资料回答，禁止使用自身知识。资料中没有则直接说"参考资料中未提及"\n'
        '2. 回答要简洁清晰，复杂信息用分点列出\n'
        '3. 不要编造信息，不确定就说"无法确定"'
        '\n4. 使用证据时在对应陈述后标注 [1]、[2] 等编号，只能引用下面确实存在的参考资料编号；没有证据就不要引用'
    )
    user_q = q
    if history:
        sp = f"对话历史:\n{history}\n\n当前问题: {q}\n\n" + sp
        user_q = f"根据对话历史，回答: {q}"
    if ev:
        sp += "\n\n参考资料:\n" + "\n\n".join(f"[{i+1}] {e['source']}\n{e['text']}" for i, e in enumerate(ev))
    return [SystemMessage(content=sp), HumanMessage(content=user_q)]


def _build_llm(streaming: bool = False):
    from backend.src.utils.helpers import get_llm
    llm = get_llm(temperature=0.3)
    if streaming:
        llm = ChatOpenAI(model=settings.llm_model, openai_api_key=settings.openai_api_key, openai_api_base=settings.openai_api_base, temperature=0.3, streaming=True, http_client=Client(proxy=None))
    return llm


def _generate(q: str, ev: list[dict], history: str = "") -> str:
    try:
        return _build_llm().invoke(_build_msg(q, ev, history)).content
    except Exception as e:
        return f"生成失败: {e}"


# ── Knowledge Base API ─────────────────────────────────────────


@app.post("/knowledge-bases")
def create_kb(req: CreateKBRequest):
    return kb_service.create(req.name, req.description)


@app.get("/knowledge-bases")
def list_kbs():
    return {"knowledge_bases": kb_service.list_all()}


@app.delete("/knowledge-bases/{kb_id}")
def delete_kb(kb_id: str):
    with knowledge_base_lock(kb_id):
        if not kb_service.get(kb_id):
            raise HTTPException(404, "知识库不存在")
        warnings = _clear_graph_data(kb_id)
        if warnings:
            raise HTTPException(503, {"message": "知识库清理未完成，请重试", "warnings": warnings})
        from backend.src.rag.store import vector_store
        dd = kb_service.docs_dir(kb_id)
        sources = [path.name for path in dd.iterdir() if path.is_file()] if dd.exists() else []
        try:
            for source in sources:
                vector_store.delete_document(kb_id, source)
            vector_store.delete_by_kb(kb_id)
        except Exception as exc:
            logger.error(f"删除知识库向量失败: {exc}")
            raise HTTPException(503, "向量清理未完成，知识库未删除")
        kb_service.delete(kb_id)
        return {"deleted": kb_id}


@app.post("/knowledge-bases/{kb_id}/upload")
async def upload_kb(kb_id: str, files: list[UploadFile] = File(...)):
    if not kb_service.get(kb_id):
        raise HTTPException(404, "知识库不存在")
    return await asyncio.to_thread(_save_uploads, kb_id, files)


def _save_uploads(kb_id: str, files: list[UploadFile]) -> dict:
    with knowledge_base_lock(kb_id):
        if not kb_service.get(kb_id):
            raise HTTPException(404, "知识库不存在")
        dd = kb_service.docs_dir(kb_id); dd.mkdir(parents=True, exist_ok=True)
        saved, rejected = [], []
        for f in files:
            filename = f.filename or ""
            ext = Path(filename).suffix.lower()
            if ext not in kb_service.SUPPORTED:
                rejected.append({"filename": filename, "reason": f"不支持 {ext or '无扩展名文件'}"})
                continue
            try:
                dest = kb_service.safe_document_path(kb_id, filename)
            except ValueError as exc:
                rejected.append({"filename": filename, "reason": str(exc)})
                continue
            temp_dest = dest.with_name(f".{dest.name}.{uuid4().hex}.upload")
            try:
                with open(temp_dest, "wb") as out:
                    shutil.copyfileobj(f.file, out)
                temp_dest.replace(dest)
            finally:
                if temp_dest.exists():
                    temp_dest.unlink()
            saved.append({"filename": filename, "size": dest.stat().st_size})
        warnings = _clear_graph_data(kb_id) if saved else []
        return {"saved": saved, "rejected": rejected, "warnings": warnings}


@app.get("/knowledge-bases/{kb_id}/documents")
def list_docs(kb_id: str):
    if not kb_service.get(kb_id):
        raise HTTPException(404, "知识库不存在")
    dd = kb_service.docs_dir(kb_id)
    docs = [{"filename": f.name, "size": f.stat().st_size, "suffix": f.suffix.lower()} for f in sorted(dd.iterdir()) if f.is_file()] if dd.exists() else []
    # 查已索引的源文件（按 kb_id 过滤）
    idxd: set[str] = set()
    try:
        from backend.src.rag.store import vector_store
        vector_store.load()
        all_meta = vector_store._col.get(where={"kb_id": kb_id}, include=["metadatas"])
        if all_meta and all_meta["metadatas"]:
            idxd = set(m.get("source", "") for m in all_meta["metadatas"] if m.get("source"))
    except Exception:
        pass
    for d in docs:
        d["indexed"] = d["filename"] in idxd
    return {"documents": docs, "total": len(docs)}


@app.delete("/knowledge-bases/{kb_id}/documents/{filename:path}")
def delete_doc(kb_id: str, filename: str):
    with knowledge_base_lock(kb_id):
        if not kb_service.get(kb_id):
            raise HTTPException(404, "知识库不存在")
        try:
            target = kb_service.safe_document_path(kb_id, filename)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        if not target.exists() or not target.is_file():
            raise HTTPException(404, "文件不存在")
        tombstone = target.with_name(f".{target.name}.{uuid4().hex}.deleting")
        target.replace(tombstone)
        try:
            from backend.src.rag.store import vector_store
            vector_store.delete_document(kb_id, filename)
        except Exception as exc:
            tombstone.replace(target)
            logger.error(f"删除文档向量失败: {exc}")
            raise HTTPException(503, "向量清理失败，文档未删除")
        try:
            warnings = _clear_graph_data(kb_id)
            tombstone.unlink()
        except Exception as exc:
            if tombstone.exists() and not target.exists():
                tombstone.replace(target)
            logger.error(f"删除文档派生数据失败: {exc}")
            raise HTTPException(503, "派生数据清理失败，源文件已保留，请重新索引")
        return {"deleted": filename, "warnings": warnings}


@app.post("/knowledge-bases/{kb_id}/index")
async def index_kb_endpoint(kb_id: str):
    if not kb_service.get(kb_id):
        raise HTTPException(404, "知识库不存在")
    dd = kb_service.docs_dir(kb_id); dd.mkdir(parents=True, exist_ok=True)
    if not any(dd.iterdir()):
        raise HTTPException(400, "知识库中没有文档")
    try:
        return await asyncio.to_thread(_index_kb_locked, kb_id, str(dd))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error(f"索引失败: {e}")
        raise HTTPException(500, f"索引失败: {e}")


def _index_kb_locked(kb_id: str, document_dir: str) -> dict:
    with knowledge_base_lock(kb_id):
        if not kb_service.get(kb_id):
            raise ValueError("知识库不存在")
        return index_kb(kb_id, document_dir)


@app.get("/knowledge-bases/{kb_id}/graph")
def get_graph(kb_id: str):
    if not kb_service.get(kb_id):
        raise HTTPException(404, "知识库不存在")
    return kb_service.load_graph(kb_id)


@app.delete("/knowledge-bases/{kb_id}/graph")
def delete_graph(kb_id: str):
    with knowledge_base_lock(kb_id):
        if not kb_service.get(kb_id):
            raise HTTPException(404, "知识库不存在")
        warnings = _clear_graph_data(kb_id)
        return {"deleted": not warnings, "warnings": warnings}


def _clear_graph_data(kb_id: str) -> list[str]:
    """Invalidate all derived graph data after source documents change."""

    warnings: list[str] = []
    kb_service.save_graph(kb_id, {"nodes": [], "edges": []})
    try:
        from backend.src.rag.store import vector_store
        vector_store.delete_entities(kb_id)
    except Exception as exc:
        logger.warning(f"删除知识库实体向量失败: {exc}")
        warnings.append("实体向量清理未完成")
    try:
        from backend.src.services.graph_service import graph
        graph.delete(kb_id)
    except Exception as exc:
        logger.warning(f"删除 Neo4j 图谱失败: {exc}")
        warnings.append("Neo4j 图谱清理未完成")
    return warnings


@app.post("/knowledge-bases/{kb_id}/graph/build")
async def build_graph(kb_id: str):
    return await asyncio.to_thread(_build_graph_locked, kb_id)


def _build_graph_locked(kb_id: str) -> dict:
    with knowledge_base_lock(kb_id):
        return _build_graph_sync(kb_id)


def _build_graph_sync(kb_id: str):
    if not kb_service.get(kb_id):
        raise HTTPException(404, "知识库不存在")
    dd = kb_service.docs_dir(kb_id); dd.mkdir(parents=True, exist_ok=True)
    if not any(dd.iterdir()):
        raise HTTPException(400, "知识库中没有文档")
    try:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from backend.src.rag.loader import DocumentLoader
        from backend.src.tools.extraction_tool import extractor
        from backend.src.services.graph_service import graph

        from pathlib import Path as _P
        img_ext = {".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".webp"}
        img_files = [f for f in _P(dd).iterdir() if f.suffix.lower() in img_ext]
        txt_files = [f for f in _P(dd).iterdir() if f.suffix.lower() not in img_ext and f.is_file()]

        chunks = []
        for f in txt_files:
            try: chunks.extend(DocumentLoader(chunk_size=4096).load(str(f)))
            except Exception as e: logger.warning(f"{f.name}: {e}")
        if not chunks and not img_files:
            raise HTTPException(400, "文档解析结果为空")
        all_nodes, all_edges, sn, se = [], [], set(), set()

        def process(t: str) -> dict:
            rels = extractor(t)
            ents: dict[str, int] = {}
            for r in rels:
                for k in ["subject", "object"]:
                    if r[k] not in ents:
                        ents[r[k]] = abs(hash(r[k])) % 10 + 1
            nodes_list = [{"id": k, "group": v} for k, v in ents.items()]
            rels_list = [{"source": r["subject"], "target": r["object"], "label": r["relation"]} for r in rels]
            # 无关系时加少量共现边兜底
            if not rels_list and len(ents) >= 2:
                ids = list(ents.keys())
                rels_list = [{"source": ids[i], "target": ids[i+1], "label": "相关"} for i in range(min(3, len(ids)-1))]
            return {"entities": nodes_list, "relations": rels_list}

        with ThreadPoolExecutor(max_workers=2) as pool:
            for f in as_completed([pool.submit(process, c.text) for c in chunks]):
                d = f.result()
                for n in d["entities"]:
                    if n["id"] not in sn:
                        sn.add(n["id"]); all_nodes.append(n)
                for e in d["relations"]:
                    k = (e["source"], e["target"])
                    if k not in se:
                        se.add(k); all_edges.append(e)
        # 图片文件直接用 VLM 抽取
        for img_f in img_files:
            try:
                rels = extractor.extract_from_image(str(img_f))
                for r in rels:
                    for k in ["subject", "object"]:
                        if r[k] not in sn:
                            sn.add(r[k]); all_nodes.append({"id": r[k], "group": abs(hash(r[k])) % 10 + 1})
                    ek = (r["subject"], r["object"])
                    if ek not in se:
                        se.add(ek); all_edges.append({"source": r["subject"], "target": r["object"], "label": r["relation"]})
            except Exception as e:
                logger.warning(f"图片 {img_f.name} 抽取失败: {e}")
        warnings: list[str] = []
        kb_service.save_graph(kb_id, {"nodes": all_nodes, "edges": all_edges})
        try:
            graph.delete(kb_id)
            graph.save(kb_id, all_nodes, all_edges)
        except Exception as exc:
            logger.warning(f"Neo4j 图谱同步失败: {exc}")
            warnings.append("Neo4j 图谱同步未完成")
        try:
            from backend.src.rag.store import vector_store
            vector_store.delete_entities(kb_id)
            if all_nodes:
                from backend.src.rag.embedder import embedder
                entity_texts = [n["id"] for n in all_nodes]
                entity_dv = embedder.embed_dense(entity_texts)
                vector_store.load()
                eids = [f"ent_{kb_id}_{i}" for i in range(len(entity_texts))]
                emeta = [{"source": n["id"], "type": "entity", "kb_id": kb_id} for n in all_nodes]
                vector_store._col.upsert(ids=eids, embeddings=entity_dv.tolist(), documents=entity_texts, metadatas=emeta)
                logger.info(f"实体向量化完成: {len(entity_texts)} 个")
        except Exception as exc:
            logger.warning(f"实体向量化失败: {exc}")
            warnings.append("实体向量同步未完成")
        return {"chunks": len(chunks), "entities": len(all_nodes), "relations": len(all_edges), "warnings": warnings}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"图谱构建失败: {e}")
        raise HTTPException(500, f"图谱构建失败: {e}")


@app.get("/knowledge-bases/index/status")
def index_status():
    try:
        from backend.src.rag.store import vector_store
        vector_store.load()
        return {"total": vector_store.count()}
    except Exception:
        return {"total": 0}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.src.main:app", host=settings.host, port=settings.port)
