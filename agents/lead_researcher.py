import json

from config.ollama_client import ask_ai
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
- Return ONLY valid JSON.

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
"""


def research_lead(lead: dict) -> str:
    """
    Research a specific lead using additional web searches.
    """

    company_name = lead.get("company_name", "")
    industry = lead.get("industry", "")
    company_info = lead.get("company_info", "")

    if not company_name:
        return json.dumps({
            "error": "company_name is required"
        })

    search_queries = [
        f"{company_name} company",
        f"{company_name} products services",
        f"{company_name} customers industry",
    ]

    all_results = []

    for query in search_queries:
        results = search_web(query, max_results=3)

        if results:
            all_results.extend(results)

    if not all_results:
        return json.dumps({
            "company_name": company_name,
            "industry": industry,
            "company_summary": "",
            "products_or_services": [],
            "target_customers": [],
            "business_problems_or_needs": [],
            "potential_service_opportunities": [],
            "important_observations": [],
            "sources": []
        })

    # Remove duplicate search results.
    unique_results = []
    seen_urls = set()

    for result in all_results:
        url = result.get("url")

        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_results.append(result)

    results_text = json.dumps(unique_results, indent=2)

    prompt = f"""
{SYSTEM_PROMPT}

Lead to research:

{json.dumps({
    "company_name": company_name,
    "industry": industry,
    "company_info": company_info
}, indent=2)}

Additional web research:

{results_text}

Research this company using ONLY the provided evidence.

Return ONLY the JSON object.
"""

    return ask_ai(prompt)