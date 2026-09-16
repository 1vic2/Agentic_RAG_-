import json


class SSEManager:
    def start(self, sid: str):
        return {"event": "start", "data": json.dumps({"conversation_id": sid}, ensure_ascii=False)}

    def token(self, t: str) -> dict:
        return {"event": "token", "data": json.dumps({"token": t})}

    def done(self, conversation_id: str, answer: str, evidence: list[dict]) -> dict:
        return {
            "event": "done",
            "data": json.dumps(
                {
                    "answer": answer,
                    "conversation_id": conversation_id,
                    "evidence": evidence,
                },
                ensure_ascii=False,
            ),
        }

    def status(self, msg: str) -> dict:
        return {"event": "status", "data": json.dumps({"status": msg})}

    def tool_start(self, conversation_id: str, tool: str) -> dict:
        return {"event": "tool_start", "data": json.dumps({"conversation_id": conversation_id, "tool": tool})}

    def tool_end(self, conversation_id: str, tool: str, ok: bool, count: int, elapsed_ms: int) -> dict:
        return {"event": "tool_end", "data": json.dumps({"conversation_id": conversation_id, "tool": tool, "ok": ok, "count": count, "elapsed_ms": elapsed_ms})}

    def error(self, msg: str) -> dict:
        return {"event": "error", "data": json.dumps({"error": msg})}


sse = SSEManager()
