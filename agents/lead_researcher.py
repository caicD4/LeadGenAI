import json

from config.ollama_client import ask_ai, clean_json_response
from tools.web_search import search_web


SYSTEM_PROMPT = """
You are the Lead Researcher for LeadGenAI.

Your job is to deeply research a specific business using real web search
results provided to you.

The provided web search results are the ONLY source of factual information
you may use.

IMPORTANT:
- Do not invent facts.
- Do not use your own knowledge.
- Every factual claim must be supported by the search results.
- If information is not available, use an empty string or empty array.
- Clearly separate factual observations from potential opportunities.
- Return ONLY valid JSON — no markdown, no explanation, no code fences.

Use exactly this structure:

{
    "company_name": "",
    "industry": "",
    "company_summary": "",
    "products_or_services": [],
    "target_customers": [],
    "business_problems_or_needs": [],
    "potential_service_opportunities": [],
    "important_observations": [],
    "sources": [
        {
            "title": "",
            "url": ""
        }
    ]
}

Rules:

- company_name must match the researched company.
- industry must be supported by the search results.
- company_summary must contain only supported facts.
- products_or_services must contain only things explicitly supported by
  the search results.
- target_customers must be supported by the search results.
- business_problems_or_needs must only contain problems or needs supported
  by the evidence.
- potential_service_opportunities are opportunities that could reasonably
  follow from the evidence. Do not present them as facts about the company.
- important_observations should contain useful factual findings from the
  research.
- sources must contain the URLs used as evidence.
- Do not fabricate URLs.
- Return no explanation outside the JSON.
- Do NOT wrap your response in markdown code fences.
"""


def research_lead(lead: dict) -> str:
    """
    Research a specific lead using a focused web search + AI analysis.
    """

    company_name = lead.get("company_name", "")
    industry = lead.get("industry", "")
    company_info = lead.get("company_info", "")

    if not company_name:
        return json.dumps({
            "error": "company_name is required"
        })

    # ── Web Search ─────────────────────────────────────────────────────────
    # Use a single, focused query to reduce API calls and latency.
    # Previously this made 3 separate queries (9 results) per lead —
    # now it makes 1 broader query (5 results).
    search_query = f"{company_name} {industry} company overview products services"

    print(f"[LeadResearcher] Searching for: {search_query!r}")

    results = search_web(search_query, max_results=5)

    if not results:
        print(f"[LeadResearcher] No results for '{company_name}', returning stub.")
        return json.dumps({
            "company_name": company_name,
            "industry": industry,
            "company_summary": company_info,
            "products_or_services": [],
            "target_customers": [],
            "business_problems_or_needs": [],
            "potential_service_opportunities": [],
            "important_observations": [],
            "sources": []
        })

    # Remove duplicate URLs just in case.
    unique_results = []
    seen_urls: set[str] = set()

    for result in results:
        url = result.get("url")

        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_results.append(result)

    results_text = json.dumps(unique_results, indent=2)

    # ── AI Analysis ────────────────────────────────────────────────────────
    prompt = f"""
{SYSTEM_PROMPT}

Lead to research:

{json.dumps({
    "company_name": company_name,
    "industry": industry,
    "company_info": company_info
}, indent=2)}

Web research results:

{results_text}

Research this company using ONLY the provided evidence.

Return ONLY the JSON object. Do NOT use markdown code fences.
"""

    print(f"[LeadResearcher] Sending research prompt for '{company_name}' to AI...")
    raw = ask_ai(prompt)
    print(f"[LeadResearcher] AI responded for '{company_name}' ({len(raw)} chars).")

    # Strip markdown code fences before returning.
    return clean_json_response(raw)