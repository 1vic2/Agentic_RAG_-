"""Bounded model -> tool -> observation loop for deep retrieval."""

import json
import threading
from collections.abc import Callable
from typing import NotRequired, TypedDict

from langgraph.graph import END, StateGraph

from backend.src.config import settings
from backend.src.rag.retriever import retriever
from backend.src.services.graph_service import graph as graph_service
from backend.src.services.tool_progress import track_tool
from backend.src.services.web_search import search_web
from backend.src.utils.helpers import get_llm, get_logger

logger = get_logger(__name__)
MAX_TURNS = 3


class ReactState(TypedDict):
    question: str
    use_web: bool
    kb_id: str
    evidence: list[dict]
    turn: int
    used_tools: list[str]
    max_turns: int
    decision: dict
    model: NotRequired[Callable[[str], str]]
    tool_runner: NotRequired[Callable[[str, str, str], list[dict]]]
    progress: NotRequired[Callable[[dict], None]]
    cancelled: NotRequired[threading.Event]


def _available(state: ReactState) -> list[str]:
    tools = ["vector", "graph"]
    if state.get("use_web") and settings.tavily_api_key and settings.tavily_api_key != "tvly-xxx":
        tools.append("web")
    return tools


def parse_decision(raw: str, allowed: set[str], used: list[str]) -> dict:
    try:
        text = str(raw).strip().removeprefix("```json").removesuffix("```").strip()
        decision = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        decision = {}
    if isinstance(decision, dict) and decision.get("action") == "final":
        return {"action": "final"}
    requested = decision.get("tool") if isinstance(decision, dict) else None
    if isinstance(requested, str) and requested in allowed and requested not in used:
        return {"action": "tool", "tool": requested}
    fallback = next((name for name in ("vector", "graph", "web") if name in allowed and name not in used), None)
    return {"action": "tool", "tool": fallback} if fallback else {"action": "final"}


def _default_model(prompt: str) -> str:
    return str(get_llm(temperature=0.0).invoke(prompt).content)


def _default_tool(name: str, question: str, kb_id: str) -> list[dict]:
    if name == "vector":
        return retriever.retrieve(question, kb_id=kb_id)
    if name == "graph":
        graph_service._connect()
        return graph_service.search(question, kb_id=kb_id)
    from tavily import TavilyClient
    return search_web(question, TavilyClient(api_key=settings.tavily_api_key))


def _decide(state: ReactState) -> dict:
    if state.get("cancelled") is not None and state["cancelled"].is_set():
        return {"decision": {"action": "final"}}
    allowed = set(_available(state))
    observations = "\n".join(f"{item.get('source', '')}: {item.get('text', '')[:500]}" for item in state["evidence"][-6:]) or "（尚无工具结果）"
    prompt = (
        "你是一个受控 RAG ReAct 决策器。只输出 JSON，不要解释。\n"
        f"问题：{state['question']}\n已执行工具：{state['used_tools']}\n"
        f"工具结果：{observations}\n可用工具：{sorted(allowed - set(state['used_tools']))}\n"
        '如果证据足够，输出 {"action":"final"}；否则输出 {"action":"tool","tool":"vector|graph|web"}。'
    )
    model = state.get("model", _default_model)
    return {"decision": parse_decision(model(prompt), allowed, state["used_tools"])}


def _act(state: ReactState) -> dict:
    decision = state["decision"]
    name = decision.get("tool")
    if decision.get("action") != "tool" or not name:
        return {"turn": state["turn"] + 1}
    if state.get("cancelled") is not None and state["cancelled"].is_set():
        return {"turn": state["turn"] + 1}
    runner = state.get("tool_runner", _default_tool)
    progress = state.get("progress")
    try:
        evidence = track_tool(name, lambda: runner(name, state["question"], state["kb_id"]), progress, state.get("cancelled"))
    except Exception as exc:
        logger.warning("ReAct tool %s failed (%s)", name, type(exc).__name__)
        evidence = []
    return {"evidence": state["evidence"] + evidence, "used_tools": state["used_tools"] + [name], "turn": state["turn"] + 1}


def _next(state: ReactState) -> str:
    if state["decision"].get("action") == "final" or state["turn"] >= state["max_turns"]:
        return "end"
    return "act"


def _build():
    graph = StateGraph(ReactState)
    graph.add_node("decide", _decide)
    graph.add_node("act", _act)
    graph.add_node("end", lambda state: {})
    graph.set_entry_point("decide")
    graph.add_conditional_edges("decide", lambda state: "end" if state["decision"].get("action") == "final" else "act", {"act": "act", "end": "end"})
    graph.add_conditional_edges("act", _next, {"act": "decide", "end": "end"})
    graph.add_edge("end", END)
    return graph.compile()


_agent = _build()


def run_react(question: str, use_web: bool, kb_id: str, progress=None, cancelled=None, max_turns: int = MAX_TURNS, model=None, tool_runner=None) -> list[dict]:
    # max_turns is bounded defensively for callers and tests; the graph's hard ceiling remains three.
    state: ReactState = {"question": question, "use_web": use_web, "kb_id": kb_id, "evidence": [], "turn": 0, "used_tools": [], "max_turns": max(1, min(max_turns, MAX_TURNS)), "decision": {}}
    if progress is not None: state["progress"] = progress
    if cancelled is not None: state["cancelled"] = cancelled
    if model is not None: state["model"] = model
    if tool_runner is not None: state["tool_runner"] = tool_runner
    return _agent.invoke(state).get("evidence", [])
