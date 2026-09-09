"""
LeadGenAI — Orchestrator.

Drives the complete lead-generation workflow with granular progress updates.

Progress milestones
-------------------
 10%  Starting
 15%  Building queries
 20%  Searching the web
 30%  Extracting candidates
 35%  Deduplicating
 40–90% Researching companies (spread across candidates)
 90%  Finalizing
 95%  Saving job metadata
100%  Complete
"""

import traceback

from agents.lead_finder import find_and_research_leads
from core.job_manager import update_job


def run_lead_generation(
    criteria: str,
    max_results: int = 5,
    job_id: str = None,
) -> list[dict]:
    """
    Run the complete LeadGenAI workflow.

    Args:
        criteria:    Natural-language lead criteria from the user.
        max_results: Maximum number of leads to find and research.
        job_id:      If provided, pushes live progress to the job manager.

    Returns:
        List of enriched lead dicts.
    """

    def on_progress(message: str, progress: int = None):
        """Push a progress update to the job manager (and always log it)."""
        print(f"[Orchestrator] {message}")
        if job_id is not None and progress is not None:
            update_job(
                job_id,
                status="running",
                progress=progress,
                message=message,
            )

    print("\n[Orchestrator] ============================================")
    print(f"[Orchestrator] Starting lead generation")
    print(f"[Orchestrator] Criteria   : {criteria!r}")
    print(f"[Orchestrator] Max results: {max_results}")
    print(f"[Orchestrator] Job ID     : {job_id or '(none)'}")
    print("[Orchestrator] ============================================\n")

    on_progress("Starting lead generation...", 10)

    try:
        leads = find_and_research_leads(
            criteria=criteria,
            max_results=max_results,
            job_id=job_id,
            on_progress=on_progress,
        )

    except Exception as exc:
        msg = f"Lead generation failed: {type(exc).__name__}: {exc}"
        print(f"[Orchestrator] ERROR: {msg}")
        print(traceback.format_exc())
        # Re-raise so job_manager marks the job as "failed".
        raise RuntimeError(msg) from exc

    count = len(leads) if leads else 0
    print(f"[Orchestrator] Pipeline complete — {count} lead(s) produced.")
    on_progress(f"All {count} lead(s) researched and scored.", 95)

    return leads