import json

from config.ollama_client import ask_ai
from tools.web_search import search_web


SYSTEM_PROMPT = """
You are the Lead Finder for LeadGenAI.

Your job is to identify potential business leads from real web search results.

IMPORTANT:
- Only identify companies that are supported by the provided search results.
- Do not invent companies.
- Do not invent facts about companies.
- Do not use your own knowledge to add companies or facts.
- If the search results do not contain enough evidence, omit the company.
- Return ONLY valid JSON.

Use exactly these fields:

{
    "leads": [
        {
            "company_name": "",
            "industry": "",
            "company_info": ""
        }
    ]
}

Rules:
- Return a JSON object.
- "leads" must be a JSON array.
- Each lead must contain all three fields.
- "company_name" must be the actual company name found in the search results.
- "industry" should be based on evidence from the search results.
- "company_info" should briefly describe what the company does using only information supported by the search results.
- Return no explanation outside the JSON.
"""


def find_leads(criteria: str, max_results: int = 10) -> str:
    """
    Find real business leads using web search and AI analysis.
    """

    search_results = search_web(criteria, max_results=max_results)

    if not search_results:
        return json.dumps({"leads": []})

    results_text = json.dumps(search_results, indent=2)

    prompt = f"""
{SYSTEM_PROMPT}

User's lead criteria:

{criteria}

Here are the real web search results:

{results_text}

Analyze these search results and identify the best matching business leads.
Return ONLY the JSON object.
"""

    return ask_ai(prompt)