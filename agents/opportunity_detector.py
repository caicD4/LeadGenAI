"""
LeadGenAI — Automation Opportunity Detector.

Given a research report for a company, this module determines which
automation services are actually relevant — based on evidence from the
research, NOT randomly assigned.

Supported opportunity types
---------------------------
- AI Receptionist
- WhatsApp Automation
- Appointment Scheduling Automation
- Lead Qualification Automation
- Customer Support Automation
- Follow-up Automation
- CRM Automation
- Email Automation
- Internal Workflow Automation
- Document Processing Automation
- Reporting & Analytics Automation
"""

import json
import traceback

from config.ollama_client import ask_ai_json


OPPORTUNITY_PROMPT = """
You are the Automation Opportunity Detector for LeadGenAI.

You will be given a company research report.
Your job is to identify which automation services are genuinely relevant
to this company based on the actual evidence in the report.

AVAILABLE AUTOMATION OPPORTUNITIES:
1. AI Receptionist              — handles inbound calls, answers FAQs, routes inquiries
2. WhatsApp Automation          — responds to WhatsApp inquiries, appointment booking via WhatsApp
3. Appointment Scheduling       — automated online booking, reminders, rescheduling
4. Lead Qualification           — automated screening/qualification of inbound leads
5. Customer Support Automation  — chatbots, automated FAQ responses, ticket routing
6. Follow-up Automation         — automated follow-up emails/messages after appointments or inquiries
7. CRM Automation               — automatic contact capture, status updates, pipeline management
8. Email Automation             — newsletter, drip campaigns, transactional emails
9. Internal Workflow Automation — repetitive internal processes, task assignment, approvals
10. Document Processing         — invoices, forms, contracts, reports
11. Reporting & Analytics       — automated dashboards, daily/weekly reports

CRITICAL RULES:
- Only assign opportunities that are genuinely supported by the research evidence.
- Do NOT assign all opportunities blindly.
- For each opportunity, cite specific evidence from the research.
- Distinguish: FACT (from research) vs INFERENCE (reasonable conclusion from facts).
- Assign priority: HIGH (strong evidence), MEDIUM (some evidence), LOW (weak but plausible).
- Return 0 to 6 opportunities maximum. Do not pad the list.
- Return ONLY valid JSON. No markdown. No code fences.

Required output structure:
{
  "opportunities": [
    {
      "opportunity": "Name of the opportunity",
      "reasoning":   "Why this opportunity applies to this company.",
      "evidence":    "Specific facts from the research that support this (FACT: ... / INFERENCE: ...)",
      "priority":    "HIGH | MEDIUM | LOW"
    }
  ]
}
"""


def detect_opportunities(research: dict) -> list[dict]:
    """
    Detect relevant automation opportunities for a company from its research.

    Args:
        research: The research dict from lead_researcher.

    Returns:
        List of opportunity dicts: [{opportunity, reasoning, evidence, priority}]
        Returns empty list on failure.
    """

    company_name = research.get("company_name", "Unknown")

    try:
        prompt = f"""
{OPPORTUNITY_PROMPT}

Company research report:
{json.dumps(research, indent=2)}

Identify automation opportunities for this company.
Return ONLY the JSON object.
"""
        result = ask_ai_json(prompt)
        opportunities = result.get("opportunities", [])

        if not isinstance(opportunities, list):
            opportunities = []

        # Validate each opportunity entry.
        valid_opps = []
        for opp in opportunities:
            if not isinstance(opp, dict):
                continue
            name = opp.get("opportunity", "").strip()
            if not name:
                continue
            valid_opps.append({
                "opportunity": name,
                "reasoning":   opp.get("reasoning", ""),
                "evidence":    opp.get("evidence", ""),
                "priority":    opp.get("priority", "MEDIUM").upper(),
            })

        print(
            f"[OpportunityDetector] {company_name}: "
            f"{len(valid_opps)} opportunity(-ies) detected."
        )
        return valid_opps

    except Exception as exc:
        print(
            f"[OpportunityDetector] WARNING: Failed for '{company_name}': {exc}\n"
            f"{traceback.format_exc()}"
        )
        return []
