from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from core.orchestrator import run_lead_generation


app = FastAPI(
    title="LeadGenAI API",
    description="API for autonomous lead discovery and research",
    version="1.0.0",
)


# Allow the frontend to communicate with the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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

    leads = run_lead_generation(
        request.criteria,
        max_results=request.max_results,
    )

    return {
        "criteria": request.criteria,
        "count": len(leads),
        "leads": leads,
    }