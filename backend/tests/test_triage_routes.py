"""Rep-side priority list route. Service is stubbed; no DB, no AI."""
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import triage_routes  # noqa: E402
import triage_service  # noqa: E402

SEEN = []


def fake_list(db, identity, limit=20):
    SEEN.append(identity)
    return [{"inquiry_id": "i1", "priority": "urgent"}]


app = FastAPI()
app.include_router(triage_routes.router)


@app.middleware("http")
async def fake_auth(request: Request, call_next):
    who = request.headers.get("x-test-agent")
    if who:
        request.state.agent = types.SimpleNamespace(
            agent_id=who, role=request.headers.get("x-test-role", "agent"))
    return await call_next(request)


client = TestClient(app, raise_server_exceptions=False)


_orig_list = triage_service.list_priority_inquiries


def setup_function(_):
    SEEN.clear()
    triage_service.set_db(object())
    triage_service.list_priority_inquiries = fake_list


def teardown_function(_):
    triage_service.list_priority_inquiries = _orig_list


def get(agent="repA", role="agent"):
    headers = {"x-test-agent": agent, "x-test-role": role} if agent else {}
    return client.get("/api/console/inquiries/priority", headers=headers)


def test_requires_agent_session():
    assert get(agent=None).status_code == 401 and SEEN == []

def test_returns_list_for_agent():
    r = get()
    assert r.status_code == 200 and r.json()["inquiries"][0]["priority"] == "urgent"

def test_identity_comes_from_session_and_query_cannot_override():
    client.get("/api/console/inquiries/priority?agent_id=evil&is_admin=true",
               headers={"x-test-agent": "repA"})
    assert SEEN[0].agent_id == "repA" and SEEN[0].is_admin is False

def test_admin_role_comes_from_server():
    get(agent="adm", role="admin")
    assert SEEN[0].is_admin is True

def test_503_when_db_not_ready():
    triage_service.set_db(None)
    assert get().status_code == 503
