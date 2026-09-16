"""Normalize Tavily results; transport errors must reach the tool boundary."""


def search_web(question: str, client) -> list[dict]:
    response = client.search(query=question, search_depth="basic", max_results=3)
    return [
        {"id": f"web_{index}", "text": item.get("content", ""), "source": item.get("url", ""), "score": item.get("score", 0), "type": "web"}
        for index, item in enumerate(response.get("results", []))
    ]
