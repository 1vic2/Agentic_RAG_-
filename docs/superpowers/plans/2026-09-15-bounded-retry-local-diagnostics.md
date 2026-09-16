# Bounded Retry and Local Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide an optional, measurable second vector retrieval for referential follow-ups and checked, manageable Windows local startup.

**Architecture:** A pure policy derives one contextual query from the most recent user question and current referential follow-up; the API executes it once in the same knowledge base after quick/deep retrieval if the elapsed-time and cancellation gates allow. The frontend exposes an opt-in toggle and timeline label. A PowerShell script reports dependency/model/API readiness without printing secrets.

**Tech Stack:** Python unittest, FastAPI, Vue 3, Vitest, PowerShell.

## Global Constraints

- Preserve all existing user data and uncommitted changes; keep retry off by default.
- The retry never calls Tavily, Neo4j, or LLM; use the incoming `kb_id` for both vector calls.
- At most one retry per request; 3 seconds is an eligibility budget, not a hard timeout for an already running model call.
- Source presence and citation validity do not prove answer faithfulness; do not claim quality improvement without live LLM evaluation.

---

### Task 1: Pure policy

**Files:** Create `backend/src/agent/retry_policy.py`, `backend/tests/test_retry_policy.py`.

**Interface:** `retry_query(question, history, enabled, elapsed_ms, cancelled=False) -> str | None`; `merge_evidence(original, additional, limit=8) -> list[dict]`.

- [ ] Write tests that default/disabled/unrelated/no-history/expired/cancelled return `None`, that a referential follow-up uses only the latest user question (at most 200 chars) and that evidence merge preserves order, IDs, and an eight-item cap.
- [ ] Run `python -m unittest backend.tests.test_retry_policy -v` to see missing functions fail.
- [ ] Implement the deterministic query gate and ordered deduplication without LLM or web calls.
- [ ] Run the targeted test to green.

### Task 2: API and timeline integration

**Files:** Modify `backend/src/models.py`, `backend/src/main.py`, `frontend/src/utils/sse.ts`, `frontend/src/views/HomeView.vue`; add `backend/tests/test_retry_integration.py`; modify `frontend/src/utils/sse.test.ts`.

**Interface:** `QueryRequest.retry_retrieval: bool = False`; `_retrieve(..., retry_retrieval=False)`; frontend `send(..., retryRetrieval=false)`.

- [ ] Add failing tests for the default single vector call, opt-in same-`kb_id` second call, elapsed/cancellation skip and `vector_retry` progress; add frontend payload test for the explicit toggle.
- [ ] Run targeted backend and Vitest tests to see expected failure.
- [ ] Measure time in `_retrieve`, apply the pure policy once to quick or deep results, call `track_tool('vector_retry', ...)` and merge evidence; pass the flag from both API endpoints and frontend.
- [ ] Run targeted tests and frontend build to green.

### Task 3: Local diagnostic, process launcher and docs

**Files:** Create `scripts/check-local.ps1`, `scripts/run-local.ps1`; modify `README.md`, `docs/local-run-and-test.md`.

**Interface:** `./scripts/check-local.ps1 -Python <python.exe>` returns nonzero if required imports or model files are missing; prints only boolean/configuration state and API HTTP status.

- [ ] Implement read-only module/model/config/port checks without displaying `.env` values or modifying services.
- [ ] Run with the installed Python 3.12 and DLPR to verify the success and failure paths; verify no secrets in output.
- [ ] Add a foreground PowerShell launcher that starts hidden backend/Vite child processes, waits for both URLs, reuses already running services and on Ctrl+C stops only its own child processes.
- [ ] Actually launch and verify local endpoints; read child logs only if startup fails.
- [ ] Document exact retry scope, diagnostic invocation, and the requirement for a real quick/deep LLM baseline.

### Task 4: Completion checks

**Files:** All changed files.

- [ ] Run backend `unittest discover`, frontend `npm test` and `npm run build`, Python compile checks, and `git diff --check`.
- [ ] Restart the local backend, test `/health/ready`, and inspect worktree status; retain the fictional demo KB for future evaluation.

## 执行记录

- 第 4 阶段：纯策略、同库一次补检索、时间/取消资格检查、证据去重与前端显式开关已实现。策略、默认单检索、SSE 工具事件、深度模式空结果保留原证据均经过先失败后通过的测试；真实演示库追问出现 `vector_retry`，最终证据仍为 4 条。
- 第 5 阶段：`check-local.ps1` 在已装齐依赖的 Python 3.12 下退出码 0、在缺包的 DLPR 下退出码 1；`run-local.ps1` 实测复用服务、启动端口空闲的两个子进程、等待就绪以及 Ctrl+C 清理自己启动的两个进程。
- 后端 50 项、前端 13 项、前端生产构建、Python 编译、34 题题集校验与 `git diff --check` 通过。演示库和已有未提交改动保留。LLM 连接仍失败，暂无回答质量对照。
