from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import os

from core.orchestrator import run_lead_generation
from core.job_manager import (
    create_job,
    get_job,
    run_in_background,
)
from database.database import init_db


app = FastAPI(
    title="LeadGenAI API",
    description="API for autonomous lead discovery and research",
    version="1.0.0",
)


# Allow all origins in development so the frontend works whether opened via
# file://, VS Code Live Server, or directly from FastAPI on port 8000.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LeadGenerationRequest(BaseModel):
    criteria: str
    max_results: int = 5


@app.on_event("startup")
def startup_event():
    """Initialise the SQLite database on server startup."""
    init_db()
    print("[API] Database initialised.")


# ── Frontend serving ──────────────────────────────────────────────────────────
# Serve the frontend at http://127.0.0.1:8000/
# This means no CORS at all — same origin as the API.

_frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
_frontend_dir = os.path.normpath(_frontend_dir)


@app.get("/")
def serve_frontend():
    """Serve index.html at the root URL."""
    index_path = os.path.join(_frontend_dir, "index.html")
    return FileResponse(index_path)


# Serve static assets (CSS, JS, images) at /static/...
if os.path.isdir(_frontend_dir):
    app.mount("/static", StaticFiles(directory=_frontend_dir), name="static")


# ── API endpoints ─────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"name": "LeadGenAI", "status": "online"}


@app.post("/generate-leads")
def generate_leads(request: LeadGenerationRequest):

    job_id = create_job()

    run_in_background(
        job_id,
        run_lead_generation,
        request.criteria,
        request.max_results,
    )

    return {
        "job_id": job_id,
        "status": "queued",
    }


@app.get("/jobs/{job_id}")
def get_job_status(job_id: str):

    job = get_job(job_id)

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Job not found.",
        )

    return job