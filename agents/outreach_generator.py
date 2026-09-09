"""
LeadGenAI — Outreach Generator.

Generates personalised outreach messages (email, WhatsApp, LinkedIn)
for a specific lead, based on actual research data.

Called on-demand (not during the main job) to save API quota.
"""

import json
import traceback

from config.ollama_client import ask_ai_json


OUTREACH_PROMPT = """
You are the Outreach Generator for LeadGenAI.

You will be given a company research report, their top automation opportunity,
and the outreach channel requested.

Your job is to write a SHORT, PERSONALISED outreach message that:
1. References specific facts from the research (not generic claims).
2. Mentions the company by name.
3. Clearly states the problem you can solve.
4. Is professional but not salesy.
5. Is appropriate for the channel (email, WhatsApp, or LinkedIn).

STRICT RULES:
- Do NOT fabricate facts not present in the research.
- Do NOT use generic phrases like "I help businesses like yours."
- Reference at least ONE specific fact about the company.
- Keep it concise: email max 150 words, WhatsApp max 80 words, LinkedIn max 120 words.
- Return ONLY valid JSON. No markdown. No code fences.

Required output structure:
{
  "channel":            "email | whatsapp | linkedin",
  "subject":            "(email only, empty string for other channels)",
  "message":            "The outreach message text",
  "personalization_facts": ["fact 1 used", "fact 2 used"],
  "recommended_action": "What the sender should do next"
}
"""


def generate_outreach(
    research: dict,
    top_opportunity: dict,
    channel: str = "email",
) -> dict:
    """
    Generate a personalised outreach message for a lead.

    Args:
        research:         The full research dict from lead_researcher.
        top_opportunity:  The primary opportunity dict {opportunity, reasoning, evidence}.
        channel:          "email", "whatsapp", or "linkedin".

    Returns:
        Dict with keys: channel, subject, message, personalization_facts, recommended_action.
        Returns a safe error dict on failure.
    """

    company_name = research.get("company_name", "Unknown")
    channel = channel.lower().strip()

    if channel not in ("email", "whatsapp", "linkedin"):
        channel = "email"

    try:
        prompt = f"""
{OUTREACH_PROMPT}

Company research:
{json.dumps(research, indent=2)}

Top automation opportunity:
{json.dumps(top_opportunity, indent=2)}

Requested channel: {channel}

Write the outreach message. Return ONLY the JSON object.
"""
        result = ask_ai_json(prompt)

        # Normalise.
        result["channel"] = channel
        if "subject" not in result:
            result["subject"] = ""
        if "message" not in result:
            result["message"] = ""
        if "personalization_facts" not in result:
            result["personalization_facts"] = []
        if "recommended_action" not in result:
            result["recommended_action"] = ""

        print(
            f"[OutreachGenerator] Generated {channel} outreach for '{company_name}'."
        )
        return result

    except Exception as exc:
        print(
            f"[OutreachGenerator] WARNING: Failed for '{company_name}': {exc}\n"
            f"{traceback.format_exc()}"
        )
        return {
            "channel": channel,
            "subject": "",
            "message": f"Could not generate outreach for {company_name}: {exc}",
            "personalization_facts": [],
            "recommended_action": "",
            "error": str(exc),
        }


def generate_all_channels(research: dict, top_opportunity: dict) -> dict:
    """
    Generate outreach for all three channels at once.

    Returns:
        Dict with keys: email, whatsapp, linkedin.
    """
    return {
        "email":    generate_outreach(research, top_opportunity, "email"),
        "whatsapp": generate_outreach(research, top_opportunity, "whatsapp"),
        "linkedin": generate_outreach(research, top_opportunity, "linkedin"),
    }
