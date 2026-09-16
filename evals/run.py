"""Evaluate the existing /query API against an explicit demo knowledge base.

This command never uploads documents. It requires a previously indexed copy of
evals/fixtures in the knowledge base selected by --kb-id.
"""

import argparse
import json
import time
from pathlib import Path
from urllib.request import Request, urlopen
from uuid import uuid4

from evals.metrics import aggregate, score_case


DATASET = Path(__file__).with_name("questions.json")


def run_cases(cases: list[dict], transport, kb_id: str, mode: str, retry_retrieval: bool = False) -> list[dict]:
    rows = []
    for case in cases:
        sid = f"eval-{uuid4()}"
        base = {"conversation_id": sid, "kb_id": kb_id, "deep_mode": mode == "deep", "use_web": False, "retry_retrieval": retry_retrieval}
        try:
            if case.get("preceding_question"):
                setup = transport({**base, "question": case["preceding_question"]})
                if not setup.get("answer") or setup["answer"].startswith("生成失败:"):
                    raise RuntimeError("追问前置请求未成功生成回答")
            start = time.perf_counter()
            response = transport({**base, "question": case["question"]})
            elapsed_ms = round((time.perf_counter() - start) * 1000)
            answer = response.get("answer", "")
            if answer.startswith("生成失败:"):
                raise RuntimeError(answer)
            evidence = response.get("evidence", [])
            row = {"id": case["id"], "question": case["question"], "answer": answer, "sources": [e.get("source", "") for e in evidence], "elapsed_ms": elapsed_ms, **score_case(case, answer, evidence)}
        except Exception as exc:
            row = {"id": case["id"], "question": case["question"], "category": case["category"], "error": str(exc)}
        rows.append(row)
    return rows


def make_transport(api_url: str, timeout: float):
    endpoint = api_url.rstrip("/") + "/query"

    def post(payload: dict):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(endpoint, data=data, headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=timeout) as response:
            return json.load(response)

    return post


def main():
    parser = argparse.ArgumentParser(description="Run the fixed fictional QA corpus; no automatic ingestion")
    parser.add_argument("--kb-id", help="ID of the manually indexed demo knowledge base")
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--mode", choices=("quick", "deep"), default="quick")
    parser.add_argument("--retry-retrieval", action="store_true", help="opt in to one bounded contextual vector retry for referential follow-ups")
    parser.add_argument("--timeout", type=float, default=90)
    parser.add_argument("--output", type=Path, help="optional JSON report path")
    parser.add_argument("--validate", action="store_true", help="validate the corpus offline without calling the API")
    args = parser.parse_args()
    cases = json.loads(DATASET.read_text(encoding="utf-8"))
    if args.validate:
        print(json.dumps({"cases": len(cases), "categories": {category: sum(c["category"] == category for c in cases) for category in sorted({c["category"] for c in cases})}}, ensure_ascii=False, indent=2))
        return
    if not args.kb_id:
        parser.error("--kb-id is required for live evaluation")
    rows = run_cases(cases, make_transport(args.api_url, args.timeout), args.kb_id, args.mode, retry_retrieval=args.retry_retrieval)
    report = {"mode": args.mode, "retry_retrieval": args.retry_retrieval, "kb_id": args.kb_id, "cases": rows, "categories": aggregate(rows), "errors": sum("error" in row for row in rows)}
    print(json.dumps({"categories": report["categories"], "errors": report["errors"]}, ensure_ascii=False, indent=2))
    if args.output:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
