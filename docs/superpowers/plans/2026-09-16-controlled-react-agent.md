# Controlled ReAct Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended) or superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Upgrade deep mode from one-shot route planning to a bounded LangGraph model-tool-observation loop while preserving fast mode and existing SSE evidence contracts.

**Architecture:** A new `react_agent.py` owns a small StateGraph with `decide`, `act`, and `finish` nodes. The decide node asks the LLM for strict JSON containing either a tool name or final action; act runs exactly one allowlisted tool and appends normalized evidence; a conditional edge returns to decide until a final action or three tool turns. Main retrieval invokes this graph only for deep mode and falls back to vector retrieval on model failure.

**Tech Stack:** LangGraph `StateGraph`, LangChain ChatOpenAI, Python unittest, existing SSE progress events.

## Global Constraints

- Fast mode remains unchanged; deep mode is the only ReAct path.
- Maximum three tool turns per request; one tool action per turn; no repeated identical tool consecutively.
- Every vector, graph, and web call uses the incoming `kb_id`; web is unavailable when `use_web` is false or no key exists.
- Tool failures produce an error timeline event and continue to a final answer/fallback; exceptions and secrets never enter evidence or SSE payloads.
- Existing `retry_retrieval` is skipped when deep ReAct is active to avoid duplicate retrieval loops.

---

### Task 1: ReAct state and decision contract

**Files:** Create `backend/src/agent/react_agent.py`, `backend/tests/test_react_agent.py`.

**Interfaces:** `ReactState` TypedDict; `run_react(question, use_web, kb_id, progress=None, cancelled=None, max_turns=3) -> list[dict]`.

- [ ] Write failing tests for strict decision parsing, invalid tool fallback, maximum three turns, repeated-tool suppression, final decision, and cancellation before act.
- [ ] Run the targeted tests and observe missing module/contract failures.
- [ ] Implement pure parsing helpers and the bounded graph with injectable model/tool functions for tests.
- [ ] Run the targeted tests to green.

### Task 2: Tool adapters and application integration

**Files:** Modify `backend/src/main.py`, `backend/src/models.py`, `backend/src/agent/orchestrator.py`; add integration assertions to `backend/tests/test_retry_integration.py` or a new `backend/tests/test_react_integration.py`.

- [ ] Add tests proving deep retrieval invokes the ReAct runner with the same `kb_id`, quick retrieval does not, and a ReAct exception falls back to normal vector retrieval.
- [ ] Wire `run_react` into `_retrieve`; skip `retry_retrieval` when deep mode is active; preserve `track_tool` events.
- [ ] Replace the old deep-mode route call with a compatibility wrapper or leave it as a documented legacy path unused by `_retrieve`.
- [ ] Run targeted backend tests.

### Task 3: Frontend label and documentation

**Files:** Modify `frontend/src/views/HomeView.vue`, `frontend/src/utils/sse.ts`, `README.md`, `docs/local-run-and-test.md`.

- [ ] Add a visible deep-mode label explaining “ReAct 深度检索” and map ReAct tool names to the existing timeline labels.
- [ ] Verify request payloads remain compatible and no new frontend API is required.
- [ ] Document the model → tool → observation loop, limits, fallback, and comparison command.

### Task 4: Verification

**Files:** All changed files.

- [ ] Run full backend unittest discovery, frontend Vitest, frontend build, Python compileall, and `git diff --check`.
- [ ] Run a live deep-mode request against the demo KB when services/LLM are available; otherwise record the precise LLM failure while verifying vector fallback and SSE closure.

## Execution Notes

- The deep path now uses LangGraph `decide → act → observe → decide`, with a hard ceiling of three distinct tools. Tool failures keep prior evidence and continue; decision failures fall back to vector retrieval.
