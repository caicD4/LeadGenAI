from agents.lead_finder import find_and_research_leads
from database.database import save_lead


def run_lead_generation(
    criteria: str,
    max_results: int = 5,
) -> list[dict]:
    """
    Run the complete LeadGenAI lead-generation workflow.

    Flow:
        criteria
            ↓
        lead discovery
            ↓
        lead research
            ↓
        database storage
    """

    print("\n[Orchestrator] Starting lead generation...")

    # 1. Find and research leads
    leads = find_and_research_leads(
        criteria,
        max_results=max_results,
    )

    if not leads:
        print("[Orchestrator] No leads found.")
        return []

    print(
        f"[Orchestrator] "
        f"Found and researched {len(leads)} lead(s)."
    )

    # 2. Save every lead
    for lead in leads:
        company_name = lead.get(
            "company_name",
            "Unknown",
        )

        industry = lead.get(
            "industry",
            "",
        )

        company_summary = lead.get(
            "company_summary",
            "",
        )

        save_lead(
            company_name,
            industry,
            company_summary,
            str(lead),
        )

        print(
            f"[Orchestrator] Saved: {company_name}"
        )

    print("[Orchestrator] Workflow complete.")

    return leads