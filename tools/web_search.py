import os
from typing import Any

from dotenv import load_dotenv
from tavily import TavilyClient


load_dotenv()


class WebSearchError(Exception):
    """Raised when web search fails."""


def _get_client() -> TavilyClient:
    api_key = os.getenv("TAVILY_API_KEY")

    if not api_key:
        raise WebSearchError(
            "TAVILY_API_KEY is missing from the environment."
        )

    return TavilyClient(api_key=api_key)


def search_web(
    query: str,
    *,
    max_results: int = 5,
    search_depth: str = "basic",
    topic: str = "general",
) -> list[dict[str, Any]]:
    """
    Search the web and return normalized search results.
    """

    if not query or not query.strip():
        raise ValueError("Search query cannot be empty.")

    if not 1 <= max_results <= 20:
        raise ValueError("max_results must be between 1 and 20.")

    client = _get_client()

    try:
        response = client.search(
            query=query.strip(),
            search_depth=search_depth,
            topic=topic,
            max_results=max_results,
            include_answer=False,
            include_raw_content=False,
        )
    except Exception as exc:
        raise WebSearchError(
            f"Web search failed: {exc}"
        ) from exc

    results = []

    for result in response.get("results", []):
        results.append(
            {
                "title": result.get("title", "").strip(),
                "url": result.get("url", "").strip(),
                "snippet": result.get("content", "").strip(),
                "score": result.get("score"),
            }
        )

    return results