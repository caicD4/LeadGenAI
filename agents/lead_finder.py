"""
LeadGenAI — Lead Finder.

Discovery pipeline:
  1. Build 2–3 targeted search queries from user criteria.
  2. Run multi_search (deduplicates by URL).
  3. Gemini extracts candidate companies with name + website + evidence.
  4. Normalize domains, deduplicate companies.
  5. Check DB for already-researched companies -> flag as cached.
  6. Research each new candidate (lead_researcher).
  7. Detect opportunities (opportunity_detector).
  8. Score each lead (lead_scorer).
  9. Return final list of enriched lead dicts.
"""

import json
import re
import traceback
from typing import Callable, List, Optional

from pydantic import BaseModel, Field, ValidationError

from agents.lead_researcher import research_lead
from agents.lead_scorer import score_lead
from agents.opportunity_detector import detect_opportunities
from config.ollama_client import ask_ai_json, clean_json_response
from database.database import (
    get_company_by_domain,
    normalize_domain,
    save_full_lead,
    upsert_company,
)
from tools.web_search import WebSearchError, multi_search


# ---------------------------------------------------------------------------
# Pydantic models for candidate validation
# ---------------------------------------------------------------------------

class Candidate(BaseModel):
    company_name: str = Field(min_length=1)
    industry:     str = Field(default="")
    website:      str = Field(default="")
    company_info: str = Field(default="")
    source_url:   str = Field(default="")
    source_title: str = Field(default="")
    evidence:     str = Field(default="")


class CandidateList(BaseModel):
    leads: List[Candidate]


# ---------------------------------------------------------------------------
# Discovery prompt
# ---------------------------------------------------------------------------

DISCOVERY_PROMPT = """
You are the Lead Finder for LeadGenAI.

Your job is to extract named, real companies from web search results that
match the user's lead criteria.

RULES:
- Use search results as the primary evidence source.
- You may use general knowledge for well-known companies referenced or
  implied by the results.
- Do NOT invent companies with no basis in the results.
- Each entry must have a company_name.
- website should be the company's actual homepage URL if you can determine it;
  otherwise leave it empty.
- source_url must be a URL from the provided search results.
- evidence: one sentence explaining why this company matches the criteria.
- Return ONLY valid JSON. No markdown. No code fences.

Required structure:
{
  "leads": [
    {
      "company_name": "",
      "industry":     "",
      "website":      "",
      "company_info": "",
      "source_url":   "",
      "source_title": "",
      "evidence":     ""
    }
  ]
}
"""


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def find_and_research_leads(
    criteria: str,
    max_results: int = 5,
    job_id: str = None,
    on_progress: Optional[Callable[[str, int], None]] = None,
) -> list[dict]:
    """
    Full pipeline: discover -> deduplicate -> research -> score -> detect opportunities.

    Returns a list of enriched lead dicts ready to be stored and served to the frontend.
    """

    def _notify(msg: str, pct: int = None):
        print(f"[LeadFinder] {msg}")
        if on_progress:
            on_progress(msg, pct)

    # ── Step 1: Multi-query discovery ─────────────────────────────────────
    _notify("Building search queries...", 15)
    queries = _build_discovery_queries(criteria)
    print(f"[LeadFinder] Queries: {queries}")

    _notify("Searching the web for companies...", 20)
    try:
        search_results = multi_search(queries, max_results_per_query=5)
    except WebSearchError as exc:
        print(f"[LeadFinder] Web search failed: {exc}")
        _notify(f"Web search failed: {exc}", 20)
        return []

    if not search_results:
        _notify("No search results found.", 25)
        return []

    print(f"[LeadFinder] Got {len(search_results)} unique result(s) across all queries.")

    # ── Step 2: AI extracts candidates ─────────────────────────────────────
    _notify(f"Analysing {len(search_results)} results with AI...", 30)
    candidates = _extract_candidates(criteria, search_results, max_results * 2)

    if not candidates:
        _notify("No candidate companies identified.", 35)
        return []

    print(f"[LeadFinder] AI returned {len(candidates)} candidate(s).")

    # ── Step 3: Deduplicate ─────────────────────────────────────────────────
    _notify("Deduplicating candidates...", 35)
    candidates = _deduplicate_candidates(candidates)
    candidates = candidates[:max_results]
    print(f"[LeadFinder] After deduplication: {len(candidates)} candidate(s).")

    # ── Step 4: Research, score, detect opportunities ───────────────────────
    final_leads: list[dict] = []
    total = len(candidates)

    for index, candidate in enumerate(candidates):
        company = candidate.get("company_name", "unknown")
        # Progress: 40% -> 90% spread across candidates
        pct_start = 40 + int((index / total) * 50)
        pct_end   = 40 + int(((index + 1) / total) * 50)

        _notify(
            f"Researching {index + 1}/{total}: {company}...",
            pct_start,
        )

        # Check DB cache — skip re-research if recently done.
        norm = normalize_domain(
            candidate.get("website") or candidate.get("source_url") or company
        )
        cached = get_company_by_domain(norm) if norm else None

        if cached:
            print(f"[LeadFinder] '{company}' already in DB (id={cached['id']}). Using cached.")
            _notify(f"Using cached data for {company}.", pct_start)
        else:
            cached = None  # explicit None = do fresh research

        try:
            lead_dict = _process_one_candidate(
                candidate=candidate,
                criteria=criteria,
                job_id=job_id,
                cached_company=cached,
            )
            if lead_dict:
                final_leads.append(lead_dict)
                _notify(
                    f"Completed {company} — score {lead_dict.get('score', 0)}/100.",
                    pct_end,
                )

        except Exception as exc:
            print(
                f"[LeadFinder] ERROR processing '{company}': {exc}\n"
                f"{traceback.format_exc()}"
            )
            _notify(f"WARNING️ Failed to process {company} (continuing...).", pct_start)
            # Continue — one bad lead should not abort the whole job.

    _notify(
        f"Research complete. {len(final_leads)}/{total} lead(s) ready.",
        90,
    )
    return final_leads


# ---------------------------------------------------------------------------
# Internal steps
# ---------------------------------------------------------------------------

def _build_discovery_queries(criteria: str) -> list[str]:
    """Build 2–3 targeted search queries from user criteria."""
    base = criteria.strip()
    queries = [
        base,
        f"top {base} companies list",
    ]
    # Add a "near me" style query only if a location is implied.
    if any(loc in base.lower() for loc in ["india", "delhi", "mumbai", "bangalore",
                                             "chennai", "hyderabad", "pune", "kolkata",
                                             "uk", "usa", "london", "dubai", "uae"]):
        queries.append(f"best {base} businesses reviews")
    return queries


def _extract_candidates(
    criteria: str,
    search_results: list[dict],
    limit: int,
) -> list[dict]:
    """Use Gemini to extract candidate companies from raw search results."""

    results_text = json.dumps(search_results[:20], indent=2)  # cap to keep prompt size

    prompt = f"""
{DISCOVERY_PROMPT}

User's lead criteria: {criteria!r}

Web search results:
{results_text}

Extract up to {limit} matching companies.
Return ONLY the JSON object.
"""

    try:
        raw = ask_ai_json(prompt)
        validated = CandidateList.model_validate(raw)
        return [c.model_dump() for c in validated.leads]

    except (ValidationError, ValueError) as exc:
        print(f"[LeadFinder] Candidate extraction failed: {exc}")
        return []

    except Exception as exc:
        print(f"[LeadFinder] Unexpected error in extraction: {exc}")
        return []


def _deduplicate_candidates(candidates: list[dict]) -> list[dict]:
    """
    Remove duplicate companies.

    Deduplication keys (in priority order):
      1. Normalized domain of website URL
      2. Normalized company name
    """
    seen: set[str] = set()
    unique: list[dict] = []

    for c in candidates:
        # Try website domain first.
        website = c.get("website", "").strip()
        key = normalize_domain(website) if website else ""

        # Fall back to normalized company name.
        if not key:
            key = normalize_domain(c.get("company_name", ""))

        if not key:
            unique.append(c)
            continue

        if key not in seen:
            seen.add(key)
            unique.append(c)
        else:
            print(f"[LeadFinder] Duplicate removed: {c.get('company_name')} ({key})")

    return unique


def _process_one_candidate(
    candidate: dict,
    criteria: str,
    job_id: Optional[str],
    cached_company: Optional[dict],
) -> Optional[dict]:
    """
    Research, score, and detect opportunities for a single candidate.
    Returns an enriched lead dict, or None on unrecoverable failure.
    """

    company_name = candidate.get("company_name", "")
    industry     = candidate.get("industry", "")
    website      = candidate.get("website", "")
    company_info = candidate.get("company_info", "")

    # 1. Research
    research = research_lead(candidate)

    # Populate missing fields from research output.
    resolved_website  = research.get("website", "") or website
    resolved_industry = research.get("industry", "") or industry
    resolved_location = research.get("location", "")
    resolved_summary  = research.get("company_summary", "") or company_info

    # 2. Score
    scoring = score_lead(research, original_criteria=criteria)
    score        = scoring.get("total_score", 0)
    score_breakdown  = scoring.get("scores", {})
    score_reasoning  = scoring.get("score_reasoning", "")
    why_good_lead    = scoring.get("why_good_lead", "")

    # 3. Detect opportunities
    opportunities = detect_opportunities(research)

    # 4. Persist to DB
    norm_domain = normalize_domain(resolved_website or company_name)

    company_id = upsert_company(
        name=company_name,
        normalized_domain=norm_domain,
        website=resolved_website,
        industry=resolved_industry,
        location=resolved_location,
        description=resolved_summary,
    )

    sources = research.get("sources", [])

    lead_id = save_full_lead(
        company_id=company_id,
        job_id=job_id,
        score=score,
        score_breakdown=score_breakdown,
        score_reasoning=score_reasoning,
        why_good_lead=why_good_lead,
        research_json=research,
        opportunities=opportunities,
        sources=sources,
    )

    # 5. Build the dict that goes into the job's "leads" field
    #    (what the frontend receives from GET /jobs/{job_id}).
    return {
        "lead_id":        lead_id,
        "company_id":     company_id,
        "company_name":   company_name,
        "website":        resolved_website,
        "industry":       resolved_industry,
        "location":       resolved_location,
        "company_summary": resolved_summary,
        "score":          score,
        "score_breakdown": score_breakdown,
        "score_reasoning": score_reasoning,
        "why_good_lead":  why_good_lead,
        "opportunities":  opportunities,
        "sources":        sources,
        # Flatten some research facts for the frontend card.
        "products_or_services": research.get("facts", {}).get("products_or_services", []),
        "online_booking":       research.get("facts", {}).get("online_booking_present", False),
        "whatsapp":             research.get("facts", {}).get("whatsapp_contact_present", False),
        "research":             research,
    }