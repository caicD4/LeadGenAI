"""
LeadGenAI — FastAPI application.

Endpoints
---------
GET  /                            Serve the frontend (index.html)
GET  /health                      Health check
POST /generate-leads              Create a background lead-generation job
GET  /jobs/{job_id}               Poll job status and results
GET  /leads                       Return all persistently stored leads
GET  /leads/{lead_id}             Return a single lead with full details
POST /leads/{lead_id}/outreach    Generate outreach messages for a lead
"""

import os
import traceback

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agents.outreach_generator import generate_all_channels, generate_outreach
from core.job_manager import create_job, get_job, run_in_background
from core.orchestrator import run_lead_generation
from database.database import (
    get_all_leads_with_details,
    get_lead_by_id,
    init_db,
)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="LeadGenAI API",
    description="Autonomous AI-powered lead discovery, research, and outreach.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

@app.on_event("startup")
def startup_event():
    init_db()
    print("[API] Database initialised.")


# ---------------------------------------------------------------------------
# Frontend serving
# ---------------------------------------------------------------------------

_frontend_dir = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "frontend")
)


@app.get("/")
def serve_frontend():
    return FileResponse(os.path.join(_frontend_dir, "index.html"))


if os.path.isdir(_frontend_dir):
    app.mount("/static", StaticFiles(directory=_frontend_dir), name="static")


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class LeadGenerationRequest(BaseModel):
    criteria:    str
    max_results: int = 5


class OutreachRequest(BaseModel):
    channel: str = "email"   # "email" | "whatsapp" | "linkedin" | "all"


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"name": "LeadGenAI", "version": "2.0.0", "status": "online"}


# ---------------------------------------------------------------------------
# Lead generation job
# ---------------------------------------------------------------------------

@app.post("/generate-leads")
def generate_leads(request: LeadGenerationRequest):
    """Create a background lead-generation job and return its ID immediately."""

    if not request.criteria or not request.criteria.strip():
        raise HTTPException(status_code=400, detail="criteria cannot be empty.")

    job_id = create_job()

    run_in_background(
        job_id,
        run_lead_generation,
        request.criteria.strip(),
        request.max_results,
    )

    return {"job_id": job_id, "status": "queued"}


@app.get("/jobs/{job_id}")
def get_job_status(job_id: str):
    """Poll a job by ID — returns status, progress, message, and leads."""

    job = get_job(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")

    return job


# ---------------------------------------------------------------------------
# Persisted leads
# ---------------------------------------------------------------------------

@app.get("/leads")
def list_leads():
    """Return all persistently stored leads with full details."""
    try:
        leads = get_all_leads_with_details()
        return {"leads": leads, "count": len(leads)}
    except Exception as exc:
        print(f"[API] /leads error: {exc}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Database error: {exc}")


@app.get("/leads/{lead_id}")
def get_lead(lead_id: int):
    """Return a single lead with full details."""
    lead = get_lead_by_id(lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found.")
    return lead


# ---------------------------------------------------------------------------
# Outreach generation (on-demand)
# ---------------------------------------------------------------------------

@app.post("/leads/{lead_id}/outreach")
def generate_lead_outreach(lead_id: int, request: OutreachRequest):
    """
    Generate personalised outreach for a lead.

    Pass channel="all" to get email, whatsapp, and linkedin at once.
    """

    lead = get_lead_by_id(lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found.")

    research = lead.get("research", {})
    opportunities = lead.get("opportunities", [])

    if not opportunities:
        raise HTTPException(
            status_code=400,
            detail="No automation opportunities detected for this lead. Run research first."
        )

    # Use the highest-priority opportunity.
    priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    top_opp = sorted(
        opportunities,
        key=lambda o: priority_order.get(o.get("priority", "MEDIUM"), 1)
    )[0]

    channel = request.channel.lower().strip()

    try:
        if channel == "all":
            result = generate_all_channels(research, top_opp)
        else:
            result = generate_outreach(research, top_opp, channel)

        return {"lead_id": lead_id, "outreach": result}

    except Exception as exc:
        print(f"[API] /outreach error: {exc}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Outreach generation failed: {exc}")