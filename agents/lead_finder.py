import json
from typing import List

from pydantic import BaseModel, Field, ValidationError

from agents.lead_researcher import research_lead
from config.ollama_client import ask_ai
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

Your job is to identify potential business leads from the provided web search results.

The web search results are the ONLY source of factual information you may use.

IMPORTANT:
- Only identify companies supported by the provided search results.
- Do not invent companies.
- Do not use your own knowledge.
- Do not infer unsupported facts.
- Every lead MUST be traceable to one provided search result.
- If evidence is insufficient, omit the lead.
- Return ONLY valid JSON.

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
- Every lead must contain all six fields.
- company_name must be supported by the search results.
- industry must be supported by the search results.
- company_info must use only supported information.
- source_url must be the URL supporting the lead.
- source_title must be the title of that source.
- evidence must explain why the source supports the lead.
- Do not create a lead merely because a company name appears incidentally.
- Return no explanation outside the JSON.
"""


def find_leads(criteria: str, max_results: int = 10) -> str:
    """
    Discover potential leads using web search and AI analysis,
    then validate the AI output against the Lead schema.
    """

    search_results = search_web(
        criteria,
        max_results=max_results,
    )

    if not search_results:
        return json.dumps({"leads": []})

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

Return ONLY the JSON object.
"""

    raw_response = ask_ai(prompt)

    try:
        parsed = json.loads(raw_response)
        validated = LeadFinderResult.model_validate(parsed)

    except (json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(
            f"Lead Finder returned invalid data: {exc}"
        ) from exc

    return validated.model_dump_json(indent=2)


def find_and_research_leads(
    criteria: str,
    max_results: int = 5,
) -> list[dict]:
    """
    Find candidate leads and research each one.
    """

    raw_leads = find_leads(
        criteria,
        max_results=max_results,
    )

    try:
        lead_data = json.loads(raw_leads)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "Lead Finder returned invalid JSON."
        ) from exc

    leads = lead_data.get("leads", [])

    researched_leads = []

    for lead in leads:
        research_raw = research_lead(lead)

        try:
            research_data = json.loads(research_raw)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Lead Researcher returned invalid JSON for "
                f"{lead.get('company_name', 'unknown lead')}."
            ) from exc

        researched_leads.append(research_data)

    return researched_leads