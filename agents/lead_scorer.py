"""
LeadGenAI — Lead Scorer.

Scores each researched lead on a 0–100 scale with a transparent breakdown.

Scoring framework
-----------------
  company_fit          0–25   How well does the company match the original criteria?
  automation_potential 0–25   Evidence of automatable, repetitive workflows?
  business_size        0–15   Scale signals (locations, employees, reviews, revenue)?
  online_presence      0–15   Website, booking system, social media, contact channels?
  buying_signals       0–20   Active growth, WhatsApp contact, tech adoption signals?
  ────────────────────────
  TOTAL                0–100
"""

import json
import traceback
from typing import Optional

from config.ollama_client import ask_ai_json


SCORING_PROMPT = """
You are the Lead Scorer for LeadGenAI.

You will be given a research report for a company.
Score this company as a potential lead using the scoring framework below.

SCORING FRAMEWORK (total 100 points):

1. company_fit        (0–25)
   How well does this company match the stated search criteria?
   Does it operate in the target industry and location?

2. automation_potential (0–25)
   Is there evidence of repetitive, manual, or high-volume workflows that
   could be automated? (appointments, inquiries, follow-ups, lead capture etc.)

3. business_size       (0–15)
   Signals that the business has scale: multiple locations, large team,
   high review count, significant online presence.

4. online_presence     (0–15)
   Quality of online presence: proper website, active social media,
   online booking system, WhatsApp business number etc.

5. buying_signals      (0–20)
   Signs the company might be receptive to automation tools:
   actively growing, mentions of efficiency challenges, already using
   some digital tools, WhatsApp / CRM / booking usage.

RULES:
- Base scores ONLY on the provided research data. Do not guess.
- Be honest — do not give a high score just because the company exists.
- Each component score must be between 0 and its maximum.
- Provide a one-sentence reasoning for each component score.
- Provide an overall "why_good_lead" summary (2–4 sentences) if score >= 60,
  or a brief "why_not_ideal" statement if score < 60.
- Return ONLY valid JSON. No markdown. No code fences. No explanation outside the JSON.

Required output structure:

{
  "scores": {
    "company_fit":          {"score": 0, "max": 25, "reasoning": ""},
    "automation_potential": {"score": 0, "max": 25, "reasoning": ""},
    "business_size":        {"score": 0, "max": 15, "reasoning": ""},
    "online_presence":      {"score": 0, "max": 15, "reasoning": ""},
    "buying_signals":       {"score": 0, "max": 20, "reasoning": ""}
  },
  "total_score": 0,
  "score_reasoning": "",
  "why_good_lead": ""
}
"""


def score_lead(
    research: dict,
    original_criteria: str = "",
) -> dict:
    """
    Score a researched lead and return a scoring dict.

    Args:
        research:          The research dict from lead_researcher.
        original_criteria: The user's original search criteria string.

    Returns:
        Dict with keys: scores, total_score, score_reasoning, why_good_lead.
        Returns a safe zero-score fallback on any failure.
    """

    company_name = research.get("company_name", "Unknown")

    try:
        prompt = f"""
{SCORING_PROMPT}

Original search criteria: {original_criteria!r}

Company research report:
{json.dumps(research, indent=2)}

Score this lead. Return ONLY the JSON object.
"""
        result = ask_ai_json(prompt)

        # Validate and fix component scores.
        scores = result.get("scores", {})
        _validate_scores(scores)

        # Recalculate total from components (don't trust AI arithmetic).
        total = sum(v.get("score", 0) for v in scores.values())
        total = max(0, min(100, total))
        result["total_score"] = total

        print(
            f"[LeadScorer] {company_name}: {total}/100"
        )
        return result

    except Exception as exc:
        print(
            f"[LeadScorer] WARNING: Scoring failed for '{company_name}': {exc}\n"
            f"{traceback.format_exc()}"
        )
        return _zero_score(company_name)


def _validate_scores(scores: dict):
    """Clamp each component score to its valid range."""
    maxes = {
        "company_fit": 25,
        "automation_potential": 25,
        "business_size": 15,
        "online_presence": 15,
        "buying_signals": 20,
    }
    for key, max_val in maxes.items():
        if key not in scores:
            scores[key] = {"score": 0, "max": max_val, "reasoning": "Not scored."}
        else:
            s = scores[key].get("score", 0)
            scores[key]["score"] = max(0, min(max_val, int(s)))
            scores[key]["max"] = max_val


def _zero_score(company_name: str) -> dict:
    return {
        "scores": {
            "company_fit":          {"score": 0, "max": 25, "reasoning": "Scoring failed."},
            "automation_potential": {"score": 0, "max": 25, "reasoning": "Scoring failed."},
            "business_size":        {"score": 0, "max": 15, "reasoning": "Scoring failed."},
            "online_presence":      {"score": 0, "max": 15, "reasoning": "Scoring failed."},
            "buying_signals":       {"score": 0, "max": 20, "reasoning": "Scoring failed."},
        },
        "total_score": 0,
        "score_reasoning": f"Scoring failed for {company_name}.",
        "why_good_lead": "",
    }
