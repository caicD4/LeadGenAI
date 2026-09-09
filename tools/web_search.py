"""
LeadGenAI — Web search tool backed by Tavily.
"""
import os
import re
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
            "TAVILY_API_KEY is missing from the environment. "
            "Add it to your .env file."
        )

    return TavilyClient(api_key=api_key)


def search_web(
    query: str,
    *,
    max_results: int = 5,
    search_depth: str = "basic",
    topic: str = "general",
    deduplicate: bool = True,
) -> list[dict[str, Any]]:
    """
    Search the web and return normalized, deduplicated search results.

    Args:
        query:        The search query string.
        max_results:  Maximum number of results to return (1–20).
        search_depth: "basic" (fast, fewer credits) or "advanced" (thorough).
        topic:        "general" or "news".
        deduplicate:  If True, remove results with duplicate URLs.

    Returns:
        List of dicts with keys: title, url, snippet, score.
        Empty list if no results or on error.
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
            f"Web search failed for query {query!r}: {exc}"
        ) from exc

    results = []
    seen_urls: set[str] = set()

    for result in response.get("results", []):
        url = result.get("url", "").strip()

        if deduplicate:
            # Normalise URL for deduplication: strip trailing slash, lowercase domain.
            norm_url = _normalize_url_for_dedup(url)
            if norm_url in seen_urls:
                continue
            seen_urls.add(norm_url)

        results.append({
            "title":   result.get("title", "").strip(),
            "url":     url,
            "snippet": result.get("content", "").strip(),
            "score":   result.get("score"),
        })

    return results


def multi_search(
    queries: list[str],
    *,
    max_results_per_query: int = 5,
    search_depth: str = "basic",
) -> list[dict[str, Any]]:
    """
    Run multiple search queries and return deduplicated combined results.

    Args:
        queries:               List of search query strings.
        max_results_per_query: Results to fetch per query.
        search_depth:          "basic" or "advanced".

    Returns:
        Deduplicated list of result dicts.
    """
    all_results: list[dict] = []
    seen_urls: set[str] = set()

    for query in queries:
        if not query or not query.strip():
            continue

        try:
            results = search_web(
                query,
                max_results=max_results_per_query,
                search_depth=search_depth,
            )
        except WebSearchError as exc:
            print(f"[WebSearch] WARNING: query {query!r} failed: {exc}")
            continue

        for result in results:
            norm_url = _normalize_url_for_dedup(result.get("url", ""))
            if norm_url and norm_url not in seen_urls:
                seen_urls.add(norm_url)
                all_results.append(result)

    return all_results


def _normalize_url_for_dedup(url: str) -> str:
    """Produce a canonical form of a URL for deduplication purposes."""
    if not url:
        return ""
    url = url.lower().strip()
    url = re.sub(r"^https?://", "", url)
    url = re.sub(r"^www\.", "", url)
    url = url.rstrip("/")
    return url