import pytest
from fastapi.testclient import TestClient

from app import api


@pytest.fixture()
def client(agent, monkeypatch):
    monkeypatch.setattr(api, "get_agent", lambda: agent)
    return TestClient(api.app)


def _submit(client, text="CP-02 PF-103 alarm, dripping from the shaft seal about 30 drops per minute"):
    r = client.post("/reports", json={"text": text, "reporter": "tech-1"})
    assert r.status_code == 201
    return r.json()


def test_report_waits_for_approval(client):
    rep = _submit(client)
    assert rep["status"] == "awaiting_approval" and rep["draft"]["causes"]
    got = client.get(f"/reports/{rep['report_id']}").json()
    assert got["status"] == "awaiting_approval" and got["decisions"] == []


def test_approve(client):
    rep = _submit(client)
    r = client.post(f"/reports/{rep['report_id']}/decision", json={"decision": "approve", "reviewer": "sup-1"})
    assert r.status_code == 200 and r.json()["report"]["status"] == "approved"
    got = client.get(f"/reports/{rep['report_id']}").json()
    assert got["status"] == "approved" and got["decisions"][0]["reviewer"] == "sup-1"
    assert got["final_draft"] == got["draft"]


def test_reject_needs_reason(client):
    rep = _submit(client)
    url = f"/reports/{rep['report_id']}/decision"
    assert client.post(url, json={"decision": "reject", "reviewer": "sup-1"}).status_code == 422
    r = client.post(url, json={"decision": "reject", "reviewer": "sup-1", "reason": "seal was replaced last week"})
    assert r.json()["report"]["status"] == "rejected"
    assert client.get(f"/reports/{rep['report_id']}").json()["decisions"][0]["reason"] == "seal was replaced last week"


def test_edit(client):
    rep = _submit(client)
    url = f"/reports/{rep['report_id']}/decision"
    assert client.post(url, json={"decision": "edit", "reviewer": "sup-1"}).status_code == 422
    edited = dict(rep["draft"], causes=rep["draft"]["causes"][:1], summary="Edited by supervisor")
    r = client.post(url, json={"decision": "edit", "reviewer": "sup-1", "edited_draft": edited})
    assert r.status_code == 200 and r.json()["report"]["status"] == "approved_with_edits"
    assert client.get(f"/reports/{rep['report_id']}").json()["final_draft"]["summary"] == "Edited by supervisor"


def test_second_decision_is_conflict(client):
    rep = _submit(client)
    url = f"/reports/{rep['report_id']}/decision"
    client.post(url, json={"decision": "approve", "reviewer": "sup-1"})
    assert client.post(url, json={"decision": "approve", "reviewer": "sup-2"}).status_code == 409


def test_safety_stop_report_cannot_be_approved(client):
    rep = _submit(client, "Smoke from the CP-04 motor terminal box")
    assert rep["status"] == "safety_stop" and rep["draft"] is None
    r = client.post(f"/reports/{rep['report_id']}/decision", json={"decision": "approve", "reviewer": "sup-1"})
    assert r.status_code == 409


def test_unknown_report(client):
    assert client.get("/reports/nope").status_code == 404
    assert client.post("/reports/nope/decision", json={"decision": "approve", "reviewer": "x"}).status_code == 404


def test_bad_decision_value(client):
    rep = _submit(client)
    assert client.post(f"/reports/{rep['report_id']}/decision",
                       json={"decision": "maybe", "reviewer": "x"}).status_code == 422
