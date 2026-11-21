"""Small JSON API. Demo with SYNTHETIC data, not for real plant use.

POST /reports                 submit a fault report, runs the agent up to the approval gate
GET  /reports/{id}            report, draft, status and decisions
POST /reports/{id}/decision   approve | reject (reason required) | edit (edited_draft required)
"""
from __future__ import annotations

from functools import lru_cache

from fastapi import FastAPI, HTTPException

from app.agent.runner import Agent, DecisionError
from app.config import get_settings
from app.models import DecisionIn, ReportIn
from app.store import get_store

app = FastAPI(title="FaultFinder (demo, SYNTHETIC data, not for real plant use)", version="0.1.0")


@lru_cache(maxsize=1)
def get_agent() -> Agent:
    settings = get_settings()
    return Agent(settings, get_store(settings))


@app.get("/health")
def health():
    agent = get_agent()
    return {"ok": True, "store": agent.store.backend, "llm": agent.settings.llm_provider,
            "chunks": agent.store.count("chunks"), "fault_records": agent.store.count("faults"),
            "notice": "Demo with SYNTHETIC data, not for real plant use."}


@app.post("/reports", status_code=201)
def create_report(body: ReportIn):
    return get_agent().submit_report(body.text, body.reporter)


@app.get("/reports/{report_id}")
def get_report(report_id: str):
    agent = get_agent()
    rep = agent.store.get_report(report_id)
    if rep is None:
        raise HTTPException(404, "report not found")
    rep["decisions"] = agent.store.list_decisions(report_id)
    return rep


@app.post("/reports/{report_id}/decision")
def decide(report_id: str, body: DecisionIn):
    try:
        return get_agent().record_decision(report_id, body)
    except KeyError:
        raise HTTPException(404, "report not found")
    except DecisionError as e:
        raise HTTPException(409, str(e))
