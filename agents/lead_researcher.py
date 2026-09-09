"""
LeadGenAI — Lead Researcher.

Researches a single company using an iterative web-search loop.

Research loop (max 2 iterations):
  1. Primary search: company name + industry + "services"
  2. AI extracts structured facts.
  3. If critical fields (website, services) still missing -> second search.
  4. AI merges and finalises.

Output clearly separates FACTS (from search results) from INFERENCES
(logical conclusions that are not directly stated).
"""

import json
import traceback
from typing import Optional

from config.ollama_client import ask_ai_json
from tools.web_search import multi_search, search_web, WebSearchError


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

RESEARCH_PROMPT = """
You are the Lead Researcher for LeadGenAI.

Research a specific company using ONLY the web search results provided.

CRITICAL RULES:
- Do NOT invent facts.
- Every claim in "facts" must be directly supported by the search results.
- Inferences are allowed in "inferences" only — clearly label them as logical
  conclusions that follow from the facts, not as confirmed facts.
- If information is not available, use empty string / empty array.
- Return ONLY valid JSON. No markdown. No code fences.

FACT vs INFERENCE:
  FACT:      "The company's website has an online booking button."
  INFERENCE: "This suggests they receive appointment requests that could be automated."

Required JSON structure:

{
  "company_name":    "",
  "website":         "",
  "industry":        "",
  "location":        "",
  "company_summary": "",
  "facts": {
    "products_or_services":     [],
    "target_customers":         [],
    "number_of_locations":      "",
    "company_size_signals":     [],
    "online_booking_present":   false,
    "whatsapp_contact_present": false,
    "contact_channels":         [],
    "social_media_presence":    [],
    "notable_observations":     []
  },
  "inferences": {
    "potential_pain_points":    [],
    "automation_readiness":     "",
    "growth_signals":           []
  },
  "sources": [
    {"title": "", "url": "", "snippet": ""}
  ]
}
"""


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------

def research_lead(lead: dict) -> dict:
    """
    Research a company and return a structured research dict.

    Uses an iterative search loop (max 2 iterations).
    Never raises — returns a partial or stub result on any failure.

    Args:
        lead: Dict with at least "company_name"; optionally "industry",
              "website", "company_info".

    Returns:
        Structured research dict (see RESEARCH_PROMPT for schema).
    """

    company_name = lead.get("company_name", "").strip()
    industry     = lead.get("industry", "").strip()
    website      = lead.get("website", "").strip() or lead.get("source_url", "").strip()
    company_info = lead.get("company_info", "").strip()

    if not company_name:
        return _stub("", "company_name is required", [])

    print(f"[LeadResearcher] Starting research: {company_name!r}")

    # ── Iteration 1 ──────────────────────────────────────────────────────────
    queries_1 = _build_queries(company_name, industry, website, iteration=1)
    results_1 = _safe_multi_search(queries_1, max_results=5)

    if not results_1:
        print(f"[LeadResearcher] No search results for '{company_name}'. Returning stub.")
        return _stub(company_name, company_info, [])

    research = _run_research_ai(
        company_name, industry, company_info, results_1
    )

    # ── Iteration 2 (if needed) ───────────────────────────────────────────────
    website_found  = bool(research.get("website", "").strip())
    services_found = bool(research.get("facts", {}).get("products_or_services"))

    if not website_found or not services_found:
        print(
            f"[LeadResearcher] Iteration 2 for '{company_name}' "
            f"(website_found={website_found}, services_found={services_found})"
        )

        queries_2 = _build_queries(company_name, industry, website, iteration=2)
        results_2 = _safe_multi_search(queries_2, max_results=5)

        if results_2:
            # Merge unique results from both iterations.
            merged = _merge_results(results_1, results_2)
            research = _run_research_ai(
                company_name, industry, company_info, merged
            )

    print(
        f"[LeadResearcher] Done: {company_name!r} — "
        f"website={research.get('website', '')!r}, "
        f"services={len(research.get('facts', {}).get('products_or_services', []))} items"
    )
    return research


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_queries(
    company_name: str,
    industry: str,
    website: str,
    iteration: int,
) -> list[str]:
    """Build focused search queries for each research iteration."""

    if iteration == 1:
        q1 = f"{company_name} {industry} company overview services"
        q2 = f"{company_name} about us products location contact"
        return [q1, q2]

    else:  # iteration 2 — look for more specific details
        q1 = f"{company_name} {industry} booking appointment WhatsApp"
        q2 = f"\"{company_name}\" website reviews"
        return [q1, q2]


def _safe_multi_search(queries: list[str], max_results: int = 5) -> list[dict]:
    """Run multi_search and return empty list on any error."""
    try:
        return multi_search(queries, max_results_per_query=max_results)
    except Exception as exc:
        print(f"[LeadResearcher] Search error: {exc}")
        return []


def _run_research_ai(
    company_name: str,
    industry: str,
    company_info: str,
    search_results: list[dict],
) -> dict:
    """Send search results to Gemini and parse the structured research output."""

    results_text = json.dumps(search_results, indent=2)

    prompt = f"""
{RESEARCH_PROMPT}

Company to research:
{{
  "company_name":  {json.dumps(company_name)},
  "industry":      {json.dumps(industry)},
  "company_info":  {json.dumps(company_info)}
}}

Web search results:
{results_text}

Research this company using ONLY the provided evidence.
Return ONLY the JSON object.
"""

    try:
        result = ask_ai_json(prompt)
        # Always enforce the company name from the original lead.
        result["company_name"] = company_name
        return result

    except Exception as exc:
        print(
            f"[LeadResearcher] AI research failed for '{company_name}': {exc}\n"
            f"{traceback.format_exc()}"
        )
        return _stub(company_name, company_info, search_results)


def _merge_results(
    results_1: list[dict],
    results_2: list[dict],
) -> list[dict]:
    """Merge two result lists, deduplicating by URL."""
    seen: set[str] = set()
    merged: list[dict] = []

    for r in results_1 + results_2:
        url = r.get("url", "")
        if url and url not in seen:
            seen.add(url)
            merged.append(r)

    return merged


def _stub(company_name: str, company_info: str, sources: list[dict]) -> dict:
    """Return a safe empty-research stub."""
    return {
        "company_name":    company_name,
        "website":         "",
        "industry":        "",
        "location":        "",
        "company_summary": company_info or "",
        "facts": {
            "products_or_services":     [],
            "target_customers":         [],
            "number_of_locations":      "",
            "company_size_signals":     [],
            "online_booking_present":   False,
            "whatsapp_contact_present": False,
            "contact_channels":         [],
            "social_media_presence":    [],
            "notable_observations":     [],
        },
        "inferences": {
            "potential_pain_points": [],
            "automation_readiness":  "",
            "growth_signals":        [],
        },
        "sources": [
            {"title": s.get("title", ""), "url": s.get("url", ""), "snippet": s.get("snippet", "")}
            for s in sources[:5]
        ],
    }