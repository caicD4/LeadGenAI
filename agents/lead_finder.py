import json
from typing import Callable, List, Optional

from pydantic import BaseModel, Field, ValidationError

from agents.lead_researcher import research_lead
from config.ollama_client import ask_ai, clean_json_response
from tools.web_search import search_web


class Lead(BaseModel):
    company_name: str = Field(min_length=1)
    industry: str = Field(min_length=1)
    company_info: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    source_title: str = Field(min_length=1)
    evidence: str = Field(min_length=1)


class LeadFinderResult(BaseModel):
    leads: List[Lead]


SYSTEM_PROMPT = """
You are the Lead Finder for LeadGenAI.

Your job is to identify potential business leads (companies) from the provided web search results.

The user's criteria may be:
- A type of business or industry (e.g. "medspa", "accounting firm", "SaaS startup")
- A location + industry combination (e.g. "AI companies in India")
- A specific niche or vertical

Your goal is to find real, named companies that match the criteria.

IMPORTANT:
- Use the search results as your primary evidence.
- You MAY use your general knowledge to fill in well-known company names if they
  are clearly referenced or implied by the search results.
- Do NOT invent companies that have no basis in the results.
- Every lead must have all six required fields.
- Return ONLY valid JSON — no markdown, no explanation, no code fences.

Required structure:

{
    "leads": [
        {
            "company_name": "",
            "industry": "",
            "company_info": "",
            "source_url": "",
            "source_title": "",
            "evidence": ""
        }
    ]
}

Rules:
- "leads" must be an array.
- Every lead must contain all six fields with non-empty values.
- company_name: the actual business name.
- industry: what sector/niche they operate in.
- company_info: a brief factual description of the company.
- source_url: a URL from the search results that references this company.
- source_title: the title of that page.
- evidence: one sentence explaining why this company matches the user's criteria.
- Do NOT wrap your response in markdown code fences.
- Return no explanation outside the JSON.
"""


def find_leads(
    criteria: str,
    max_results: int = 10,
    on_progress: Optional[Callable[[str], None]] = None,
) -> str:
    """
    Discover potential leads using web search and AI analysis,
    then validate the AI output against the Lead schema.
    """

    if on_progress:
        on_progress("Searching the web for leads...")

    print(f"[LeadFinder] Searching for: {criteria!r}")

    # Build a richer search query — single-word terms like "medspa" need
    # context to find company listings rather than general info pages.
    search_query = criteria
    if len(criteria.split()) == 1:
        search_query = f"best {criteria} companies list top businesses"

    search_results = search_web(
        search_query,
        max_results=max_results,
    )

    if not search_results:
        print("[LeadFinder] No web search results found.")
        return json.dumps({"leads": []})

    print(f"[LeadFinder] Got {len(search_results)} search result(s).")

    if on_progress:
        on_progress(f"Found {len(search_results)} search results. Analysing with AI...")

    results_text = json.dumps(
        search_results,
        indent=2,
    )

    prompt = f"""
{SYSTEM_PROMPT}

User's lead criteria:

{criteria}

Real web search results:

{results_text}

Analyze the search results and identify the best matching leads.

Return ONLY the JSON object. Do NOT use markdown code fences.
"""

    print("[LeadFinder] Sending prompt to AI...")
    raw_response = ask_ai(prompt)
    print(f"[LeadFinder] AI responded ({len(raw_response)} chars).")

    # Strip any markdown code fences the model may have added.
    cleaned = clean_json_response(raw_response)

    try:
        parsed = json.loads(cleaned)
        validated = LeadFinderResult.model_validate(parsed)

    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Lead Finder returned invalid JSON: {exc}\n"
            f"Raw AI response (first 500 chars): {raw_response[:500]}"
        ) from exc

    except ValidationError as exc:
        raise ValueError(
            f"Lead Finder returned structurally invalid data: {exc}"
        ) from exc

    return validated.model_dump_json(indent=2)


def find_and_research_leads(
    criteria: str,
    max_results: int = 5,
    on_progress: Optional[Callable[[str, int], None]] = None,
) -> list[dict]:
    """
    Find candidate leads and research each one.

    Args:
        criteria:    Natural-language search criteria.
        max_results: How many leads to discover.
        on_progress: Optional callback(message, progress_pct) for status updates.
    """

    def _notify(msg: str, pct: int = None):
        print(f"[LeadFinder] {msg}")
        if on_progress:
            on_progress(msg, pct)

    # ── Step 1: Find leads ────────────────────────────────────────────────
    _notify("Discovering leads via web search...", 20)

    raw_leads = find_leads(
        criteria,
        max_results=max_results,
        on_progress=lambda msg: _notify(msg),
    )

    try:
        lead_data = json.loads(raw_leads)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "Lead Finder returned invalid JSON."
        ) from exc

    leads = lead_data.get("leads", [])

    if not leads:
        _notify("No leads discovered.", 90)
        return []

    # Cap to max_results — the AI sometimes returns more than requested.
    if len(leads) > max_results:
        print(
            f"[LeadFinder] AI returned {len(leads)} leads; "
            f"capping to max_results={max_results}."
        )
        leads = leads[:max_results]

    _notify(f"Discovered {len(leads)} lead(s). Starting research...", 40)

    # ── Step 2: Research each lead ────────────────────────────────────────
    researched_leads = []

    for index, lead in enumerate(leads):
        company = lead.get("company_name", "unknown")
        progress = 40 + int((index / len(leads)) * 50)  # 40% → 90%

        _notify(
            f"Researching lead {index + 1}/{len(leads)}: {company}...",
            progress,
        )

        research_raw = research_lead(lead)

        # Strip fences from researcher output too.
        research_cleaned = clean_json_response(research_raw)

        try:
            research_data = json.loads(research_cleaned)
        except json.JSONDecodeError as exc:
            # Log the actual bad response so we can see what went wrong.
            print(
                f"[LeadFinder] WARNING: Lead Researcher returned invalid JSON "
                f"for '{company}': {exc}\n"
                f"  Raw (first 300 chars): {research_raw[:300]!r}"
            )
            continue

        researched_leads.append(research_data)

    _notify(
        f"Research complete. {len(researched_leads)} lead(s) ready.",
        90,
    )

    return researched_leads