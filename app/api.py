from fastapi import FastAPI
from pydantic import BaseModel

from core.orchestrator import run_lead_generation


app = FastAPI(
    title="LeadGenAI API",
    description="API for autonomous lead generation and research.",
    version="1.0.0",
)


class LeadGenerationRequest(BaseModel):
    criteria: str
    max_results: int = 5


@app.get("/")
def root():
    return {
        "name": "LeadGenAI",
        "status": "online",
    }


@app.post("/generate-leads")
def generate_leads(request: LeadGenerationRequest):
    results = run_lead_generation(
        request.criteria,
        max_results=request.max_results,
    )

    return {
        "criteria": request.criteria,
        "count": len(results),
        "leads": results,
    }