from config.ollama_client import ask_ai


SYSTEM_PROMPT = """
You are the Lead Researcher for LeadGenAI.

Your job is to research and analyze potential business leads.

Return ONLY valid JSON.

Use exactly these fields:

{
  "company_name": "",
  "industry": "",
  "what_they_do": "",
  "target_customers": "",
  "possible_business_problems": [],
  "possible_service_opportunities": [],
  "important_observations": []
}

Rules:
- Be factual.
- Do not invent information.
- If information is unknown, use "Unknown".
- possible_business_problems must be a JSON array.
- possible_service_opportunities must be a JSON array.
- important_observations must be a JSON array.
- Return no Markdown.
- Return no explanation outside the JSON.
"""

def research_lead(company_info: str) -> str:
    prompt = f"""
{SYSTEM_PROMPT}

Analyze the following lead:

{company_info}

Return the research report as JSON.
"""

    return ask_ai(prompt)