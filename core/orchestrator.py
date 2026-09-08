import traceback

from agents.lead_finder import find_and_research_leads
from core.job_manager import update_job
from database.database import save_lead


def run_lead_generation(
    criteria: str,
    max_results: int = 5,
    job_id: str = None,
) -> list[dict]:
    """
    Run the complete LeadGenAI lead-generation workflow.

    Flow:
        criteria
            ↓
        lead discovery  (web search + AI)
            ↓
        lead research   (web search + AI, per lead)
            ↓
        database storage
            ↓
        return leads

    Args:
        criteria:    Natural-language lead criteria from the user.
        max_results: Maximum number of leads to find and research.
        job_id:      If provided, updates job progress during execution.
    """

    def on_progress(message: str, progress: int = None):
        """Push live progress updates to the job manager."""
        print(f"[Orchestrator] {message}")

        if job_id is not None and progress is not None:
            update_job(
                job_id,
                status="running",
                progress=progress,
                message=message,
            )

    print("\n[Orchestrator] Starting lead generation...")
    print(f"[Orchestrator] Criteria: {criteria!r}")
    print(f"[Orchestrator] Max results: {max_results}")

    # ── 1. Find and research leads ─────────────────────────────────────────
    try:
        leads = find_and_research_leads(
            criteria,
            max_results=max_results,
            on_progress=on_progress,
        )
    except Exception as exc:
        # Re-raise with a clear message so job_manager surfaces it.
        print(f"[Orchestrator] Lead generation failed: {exc}")
        print(traceback.format_exc())
        raise RuntimeError(
            f"Lead generation failed: {exc}"
        ) from exc

    if not leads:
        print("[Orchestrator] No leads found.")
        on_progress("No leads found.", 95)
        return []

    print(f"[Orchestrator] Found and researched {len(leads)} lead(s).")
    on_progress(f"Saving {len(leads)} lead(s) to database...", 92)

    # ── 2. Save every lead to the database ─────────────────────────────────
    for lead in leads:
        company_name = lead.get("company_name", "Unknown")
        industry = lead.get("industry", "")
        company_summary = lead.get("company_summary", "")

        try:
            save_lead(
                company_name,
                industry,
                company_summary,
                str(lead),
            )
            print(f"[Orchestrator] Saved: {company_name}")

        except Exception as exc:
            # Non-fatal: log the error but continue saving other leads.
            print(
                f"[Orchestrator] WARNING: Failed to save '{company_name}': {exc}"
            )

    print("[Orchestrator] Workflow complete.")
    on_progress("All leads saved.", 98)

    return leads