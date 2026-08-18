"""Minimal FastAPI chat surface for the copilot.

    uvicorn web.app:app --reload
    open http://127.0.0.1:8000

POST /api/provision  { "message": "...", "team": "checkout", "offline": true }
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel

from copilot import pipeline

STATIC = Path(__file__).parent / "static"
app = FastAPI(title="Golden-Path FinOps Copilot")


class ProvisionRequest(BaseModel):
    message: str
    team: str = "checkout"
    offline: bool = True
    approve: bool = False


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.post("/api/provision")
def provision(req: ProvisionRequest) -> dict:
    if req.offline:
        intent, team = pipeline.classify(req.message, req.team)
        return pipeline.run(intent, team, approval_label=req.approve)
    from copilot import agent
    out = agent.run(req.message, req.team)
    return out.get("submit_result") or {"final_text": out["final_text"]}
