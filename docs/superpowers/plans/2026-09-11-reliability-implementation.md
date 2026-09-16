# AgenticRAG Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing knowledge-base and chat flow reliable enough for repeatable local demos by fixing session isolation, streamed event parsing, agent routing, and index lifecycle behavior.

**Architecture:** Keep the current FastAPI/Vue/Chroma/LangGraph structure. Extract stateful protocol behavior into small testable units, make identifiers explicit rather than shared, and use stable document-scoped vector IDs so re-index and delete operations are deterministic.

**Tech Stack:** Python 3.11+, FastAPI, standard-library unittest, LangGraph, ChromaDB, Vue 3, TypeScript, Vitest, SSE over fetch.

## Global Constraints

- Preserve all existing uncommitted user changes and build on the current working tree.
- Do not modify existing knowledge-base data during tests.
- Do not read or print API keys.
- Use temporary storage and model/database substitutes in automated tests.
- Do not claim unmeasured answer-quality or performance improvements.
- Keep external LLM, Tavily, and Neo4j integration optional for offline tests.

---

### Task 1: Backend session and SSE isolation

**Files:**
- Create: `backend/src/services/session_service.py`
- Modify: `backend/src/services/sse_manager.py`
- Modify: `backend/src/main.py`
- Create: `backend/tests/test_session_and_sse.py`
- Modify: `backend/requirements.txt`

**Interfaces:**
- Produces: `SessionStore(db_path: Path)`, `append(conversation_id, role, content, evidence=None)`, `recent(conversation_id, limit=8)`, `format_history(messages, max_chars=6000)`.
- Produces: stateless `SSEManager.done(conversation_id, answer, evidence)`.
- Consumes: `QueryRequest.conversation_id` as the authoritative session identifier.

- [ ] **Step 1: Write failing tests for session persistence, conversation isolation, complete role history, and interleaved SSE completion IDs.**

```python
def test_sessions_persist_and_remain_isolated(tmp_path):
    store = SessionStore(tmp_path / "sessions.db")
    store.append("a", "user", "question a")
    store.append("a", "assistant", "answer a")
    store.append("b", "user", "question b")
    reopened = SessionStore(tmp_path / "sessions.db")
    assert [m["content"] for m in reopened.recent("a")] == ["question a", "answer a"]
    assert [m["content"] for m in reopened.recent("b")] == ["question b"]

def test_sse_done_uses_explicit_conversation_id():
    assert json.loads(sse.done("a", "answer", [])["data"])["conversation_id"] == "a"
```

- [x] **Step 2: Run `python -m unittest backend.tests.test_session_and_sse -v` and confirm imports/signatures fail for the missing behavior.**

- [ ] **Step 3: Implement SQLite-backed message persistence with a schema created on first use, parameterized SQL, timestamps, bounded history formatting, and a stateless SSE encoder.**

```python
class SSEManager:
    def done(self, conversation_id: str, answer: str, evidence: list[dict]) -> dict:
        return {"event": "done", "data": json.dumps({
            "answer": answer,
            "conversation_id": conversation_id,
            "evidence": evidence,
        }, ensure_ascii=False)}
```

- [ ] **Step 4: Replace the process-local `sessions` dictionary in both query endpoints with `SessionStore`; append user and assistant messages separately and build history from complete role messages.**

- [x] **Step 5: Run the targeted test, then `python -m unittest discover -s backend/tests -v`; expected result is zero failures.**

### Task 2: Agent routing and graph evidence contract

**Files:**
- Modify: `backend/src/agent/orchestrator.py`
- Modify: `backend/src/services/graph_service.py`
- Create: `backend/tests/test_agent_routing.py`
- Create: `backend/tests/test_graph_service.py`

**Interfaces:**
- Produces: `sanitize_routes(raw, allowed) -> list[str]` with order-preserving deduplication and vector fallback.
- Produces: `GraphService.search(q: str, kb_id: str = "", k: int = 10) -> list[Evidence]`.
- Evidence contract: `{"id": str, "text": str, "source": str, "score": float, "type": str}`.

- [ ] **Step 1: Write failing unit tests showing 1/2/3 planned tools all execute, duplicated/invalid tools are removed, web stays disabled when disallowed, and graph records become textual evidence.**

```python
def test_next_runs_every_planned_tool(self):
    for routes in (["vector"], ["vector", "web"], ["vector", "graph", "web"]):
        self.assertEqual(walk_routes(routes), routes)

def test_routes_are_filtered_by_allowed_tools():
    assert sanitize_routes(["web", "vector", "web", 1], {"vector"}) == ["vector"]
```

- [ ] **Step 2: Run the two test modules and verify the loop-boundary and evidence-shape assertions fail.**

- [ ] **Step 3: Fix the LangGraph continuation condition to compare the already-incremented `idx` directly with route length; validate route JSON as a list and filter against the request-specific allowed set.**

```python
def next_step(state: State) -> str:
    return "run" if state["idx"] < len(state["routes"]) else "end"
```

- [ ] **Step 4: Parameterize graph queries with `kb_id`, format each record as evidence, and pass `kb_id` from the orchestrator.**

- [ ] **Step 5: Run targeted tests and the complete backend suite; expected result is zero failures.**

### Task 3: Idempotent document indexing and safe deletion

**Files:**
- Modify: `backend/src/rag/store.py`
- Modify: `backend/src/services/index_service.py`
- Modify: `backend/src/main.py`
- Modify: `backend/src/services/kb_service.py`
- Create: `backend/tests/test_vector_lifecycle.py`
- Create: `backend/tests/test_document_paths.py`

**Interfaces:**
- Produces: stable `document_chunk_id(kb_id, source, chunk_index, text) -> str`.
- Produces: `VectorStore.replace_documents(kb_id, chunks, embeddings)` and `delete_document(kb_id, source)`.
- Produces: `kb_service.safe_document_path(kb_id, filename) -> Path`, rejecting absolute paths and resolved targets outside the documents directory.

- [ ] **Step 1: Write failing tests with an in-memory collection substitute for stable IDs, repeat-index replacement, preservation after failed embedding, document deletion, and path traversal rejection.**

```python
def test_stable_chunk_ids_are_repeatable():
    assert document_chunk_id("kb", "a.txt", 0, "hello") == document_chunk_id("kb", "a.txt", 0, "hello")

def test_document_path_rejects_escape(tmp_path, monkeypatch):
    monkeypatch.setattr(kb_service, "KB_ROOT", tmp_path)
    with self.assertRaises(ValueError):
        kb_service.safe_document_path("kb", "../outside.txt")
```

- [ ] **Step 2: Run the new modules and confirm they fail for missing lifecycle and path APIs.**

- [ ] **Step 3: Store explicit document metadata (`type`, `kb_id`, `source`, `chunk_index`) and replace each successfully prepared source using stable hash IDs. Preserve old vectors until parsing and embedding have succeeded.**

- [ ] **Step 4: Use safe resolved paths in upload/delete handlers; synchronize document deletion with vector deletion and invalidate the local graph file after document mutations.**

- [ ] **Step 5: Make the indexing endpoint run synchronous parsing/embedding through `asyncio.to_thread`, run targeted tests, then the full backend suite.**

### Task 4: Frontend SSE parser, session binding, cancellation, and documentation

**Files:**
- Create: `frontend/src/utils/sseParser.ts`
- Modify: `frontend/src/utils/sse.ts`
- Modify: `frontend/src/stores/chat.ts`
- Modify: `frontend/src/views/HomeView.vue`
- Create: `frontend/src/utils/sseParser.test.ts`
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Modify: `README.md`

**Interfaces:**
- Produces: `createSSEParser(onEvent) -> { push(chunk: string): void; finish(): void }`.
- Produces: `useSSE(...).send(...)` and `useSSE(...).cancel()` with per-chat conversation IDs and abort support.
- Adds `serverId?: string` to `ChatSession`; this ID is sent as `conversation_id` and updated from start/done events.

- [ ] **Step 1: Add Vitest and write failing parser tests for split JSON lines, split UTF-8 decoded text, CRLF, multiple events per chunk, and final buffered event.**

```typescript
it('keeps an event split across chunks', () => {
  const events: SSEEvent[] = []
  const parser = createSSEParser(e => events.push(e))
  parser.push('event: token\ndata: {"tok')
  parser.push('en":"你好"}\n\n')
  expect(events).toEqual([{ event: 'token', data: '{"token":"你好"}' }])
})
```

- [x] **Step 2: Run `npm test` in `frontend` and verify the missing parser behavior fails.**

- [ ] **Step 3: Implement the buffered event parser, integrate streaming decode/final flush, and surface HTTP/SSE/connection errors as assistant messages.**

- [ ] **Step 4: Bind each request to the originating `ChatSession`, persist its backend ID, use `AbortController`, add a stop button, and guarantee `streaming=false` in `finally`.**

- [ ] **Step 5: Update README with actual supported formats, current Agent scope, offline-model setting, test commands, and known limits.**

- [x] **Step 6: Run `npm test`, `npm run build`, `python -m unittest discover -s backend/tests -v`, and inspect `git diff --check`; expected result is zero failures/errors.**

## Plan self-review

- Spec coverage: session/SSE, routing/graph evidence, index lifecycle/path safety, runtime behavior, tests, and documentation each map to one task.
- Scope choice: SQLite persistence is retained because restart-safe history is a core accepted requirement; LLM-based query rewriting and a job queue remain excluded.
- Placeholder scan: no TBD/TODO or unspecified implementation steps remain.
- Type consistency: conversation IDs, evidence fields, route sanitization, and vector lifecycle APIs use the same names across tasks.
