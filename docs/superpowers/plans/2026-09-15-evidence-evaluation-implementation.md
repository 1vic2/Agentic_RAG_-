# Evidence, Evaluation and Agent Timeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add reproducible quality measurement, navigable citations, visible tool execution, and one-origin demo deployment without altering existing user data.

**Architecture:** Pure evaluation and citation functions establish contracts; the API emits request-bound tool events; Vue renders evidence IDs and a live timeline; nginx proxies the existing API.

**Tech Stack:** Python unittest, FastAPI, LangGraph, Vue 3, TypeScript, Vitest, Docker Compose.

## Global Constraints

- Preserve existing uncommitted changes and the existing `data/` directory.
- Offline tests use fixtures and substitutes. Never claim real LLM quality without a live evaluation run.
- Citation validity only checks that the referenced evidence exists; answer faithfulness requires a separate judge or review.
- Do not send private documents to an external tracing service.

---

### Task 1: Evaluation contract and demo corpus

**Files:** Create `evals/fixtures/*.txt`, `evals/questions.json`, `evals/metrics.py`, `evals/run.py`, `backend/tests/test_eval_metrics.py`; modify `README.md`.

**Interfaces:** `score_case(case, answer, evidence) -> dict`; CLI reads JSON, calls existing `/query` with explicit `kb_id`, prints per-category aggregates and raw cases.

- [ ] Write failing tests for source hit, missing source, refusal and per-category aggregation; run them and confirm failure is the missing contract.
- [ ] Implement pure metrics and a fixture-only command. Add at least 30 categorized cases with known source files and reference answers.
- [ ] Implement explicit live API runner with timeout and result JSON; never auto-ingest real user data.
- [ ] Run targeted and full backend tests.

### Task 2: Verified navigable citations

**Files:** Create `frontend/src/utils/citations.ts`, `frontend/src/utils/citations.test.ts`; modify `backend/src/main.py`, `frontend/src/components/MarkdownViewer.vue`, `frontend/src/views/HomeView.vue`.

**Interfaces:** `linkCitations(html, count) -> html`; `MarkdownViewer` receives `evidenceCount` and optional `onCitation`; evidence cards have stable numbered DOM targets.

- [ ] Write failing tests for valid/invalid citation markers and repeated references; watch RED.
- [ ] Add explicit numbered evidence instruction to generation prompt and safely link only existing numbered evidence in rendered sanitized Markdown.
- [ ] Click focuses/highlights the evidence card; verify targeted frontend tests and production build.

### Task 3: Request-scoped tool timeline

**Files:** Modify `backend/src/services/sse_manager.py`, `backend/src/agent/orchestrator.py`, `backend/src/main.py`, `frontend/src/utils/sse.ts`, `frontend/src/views/HomeView.vue`, `frontend/src/types/research.ts`; create `backend/tests/test_tool_events.py`, `frontend/src/utils/toolTimeline.test.ts`.

**Interfaces:** `tool_start(sid, tool)`, `tool_end(sid, tool, ok, count, elapsed_ms)`; `useSSE` stores progress on originating session.

- [ ] Write tests proving event IDs are explicit, tools produce start/end even on failure, and another session cannot receive events; watch RED.
- [ ] Route sync retrieval progress through a request-local thread-safe async queue into SSE, with quick and deep mode coverage.
- [ ] Render completed/running/error tools, retaining a per-message snapshot; verify full backend/frontend suites and build.

### Task 4: Optional bounded second retrieval

**Files:** Create `backend/src/agent/retry_policy.py`, `backend/tests/test_retry_policy.py`; modify `backend/src/agent/orchestrator.py`, `backend/src/models.py`, `frontend/src/utils/sse.ts` only when offline policy tests and real evaluation justify the API.

- [ ] Test limits for at most one retry, time budget and kb/web constraints; watch RED.
- [ ] Implement opt-in experiment, default disabled, only after a real baseline run. If external services are unavailable, document this stage as pending evaluation without claiming improvement.

### Task 5: Single-origin demo deployment

**Files:** Create `frontend/Dockerfile`, `frontend/nginx.conf`; modify `docker-compose.yml`, `README.md`.

- [ ] Add nginx SPA fallback and `/api/` proxy; map frontend port 8080 and preserve existing backend/data mounts.
- [ ] Validate Compose syntax if Docker exists, run frontend build and document exact demo/evaluation steps.
- [ ] Run `git diff --check`, complete test suites, and inspect ignored/data status.

## 2026-09-15 执行记录

- Task 1–3：已实现；34 道题的离线校验、评分规则、SSE 工具事件、前端引用和会话归属经过单元测试与构建。
- Task 4：依计划等待真实 LLM/BGE 环境运行固定题集，比较质量、延迟和调用量后再决定是否增加受限二次检索；没有基线时保持关闭。
- Task 5：前端 Dockerfile、nginx 单域名代理、Compose 与配置文档已加入；本机没有 Docker CLI，只完成 YAML/路径静态验证，镜像构建和服务联调待可用环境执行。
- 后端自动化测试 39 项、前端 12 项通过；Python 编译检查、Vite 生产构建与 `git diff --check` 通过。未执行真实外部 LLM、Neo4j、Tavily、Chroma 模型联调。

## 后续第 4/5 阶段调整

用户要求继续优化后，新增默认关闭、仅用于短指代追问的同库向量补检索实验及无 Docker 本地诊断；实现与验证步骤见 `2026-09-15-bounded-retry-local-diagnostics.md`。先前记录反映当时状态。真实 LLM 对照仍待连接恢复后运行，当前不能证明生成质量增益。
