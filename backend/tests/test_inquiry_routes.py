"""Route tests for the rep inquiry view. Service stubbed; no DB, no AI."""
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import inquiry_detail  # noqa: E402
import inquiry_routes  # noqa: E402
import triage_routes  # noqa: E402
import triage_service  # noqa: E402

SEEN = []
app = FastAPI()
app.include_router(inquiry_routes.router)   # registered BEFORE triage on purpose: no path collision
app.include_router(triage_routes.router)


@app.middleware("http")
async def fake_auth(request: Request, call_next):
    who = request.headers.get("x-test-agent")
    if who:
        request.state.agent = types.SimpleNamespace(
            agent_id=who, role=request.headers.get("x-test-role", "agent"))
    return await call_next(request)


client = TestClient(app, raise_server_exceptions=False)
OK_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


def fake_detail(db, identity, inquiry_id):
    SEEN.append(identity)
    return {"inquiry": {"inquiry_id": inquiry_id}, "messages": []} if inquiry_id == OK_ID else None


def setup_function(_):
    SEEN.clear()
    triage_service.set_db(object())
    inquiry_detail.get_inquiry_detail = fake_detail
    triage_routes.triage_service.list_priority_inquiries = lambda db, identity, limit=20: []


def get(path, agent="repA", role="agent"):
    headers = {"x-test-agent": agent, "x-test-role": role} if agent else {}
    return client.get(path, headers=headers)


def test_requires_agent_session():
    assert get(f"/api/console/inquiry/{OK_ID}", agent=None).status_code == 401

def test_found_and_not_found_are_distinct_but_leak_nothing():
    assert get(f"/api/console/inquiry/{OK_ID}").status_code == 200
    r = get("/api/console/inquiry/cccccccc-cccc-4ccc-8ccc-cccccccccccc")
    assert r.status_code == 404 and "not found" in r.text.lower()

def test_identity_from_session_only():
    client.get(f"/api/console/inquiry/{OK_ID}?agent_id=evil&is_admin=true", headers={"x-test-agent": "repA"})
    assert SEEN[0].agent_id == "repA" and SEEN[0].is_admin is False

def test_admin_role_from_server():
    get(f"/api/console/inquiry/{OK_ID}", agent="adm", role="admin")
    assert SEEN[0].is_admin is True

def test_priority_route_still_works_and_is_not_swallowed():
    assert get("/api/console/inquiries/priority").status_code == 200

def test_503_when_db_missing():
    triage_service.set_db(None)
    assert get(f"/api/console/inquiry/{OK_ID}").status_code == 503
