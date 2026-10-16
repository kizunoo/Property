"""Route tests with the LLM stubbed out. Never calls Gemini. Self-contained FastAPI app."""
import asyncio
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

CALLS = []
stub = types.ModuleType("copilot_agent")


async def _ok(agent_id, is_admin, conversation_id, message):
    CALLS.append((agent_id, is_admin, conversation_id, message))
    return "stub reply"

stub.run_copilot = _ok
sys.modules["copilot_agent"] = stub

import copilot_routes  # noqa: E402

app = FastAPI()
app.include_router(copilot_routes.router)


@app.middleware("http")
async def fake_auth(request: Request, call_next):
    who = request.headers.get("x-test-agent")
    if who:
        request.state.agent = types.SimpleNamespace(
            agent_id=who, role=request.headers.get("x-test-role", "agent"))
    return await call_next(request)


client = TestClient(app, raise_server_exceptions=False)
CID = "conv-12345678"


def post(body=None, agent="repA", role="agent"):
    headers = {"x-test-agent": agent, "x-test-role": role} if agent else {}
    return client.post("/api/console/copilot", json=body or {"message": "hi", "conversation_id": CID},
                       headers=headers)


def setup_function(_):
    CALLS.clear()
    copilot_routes._hits.clear()
    stub.run_copilot = _ok
    copilot_routes.TIMEOUT_S = 45


def test_requires_agent_session():
    assert post(agent=None).status_code == 401
    assert CALLS == []

def test_validation_rejects_bad_input():
    assert post({"message": "", "conversation_id": CID}).status_code == 422
    assert post({"message": "x" * 1001, "conversation_id": CID}).status_code == 422
    assert post({"message": "hi", "conversation_id": "short"}).status_code == 422
    assert post({"message": "hi", "conversation_id": "bad id!!!!!!"}).status_code == 422

def test_success_returns_reply():
    r = post()
    assert r.status_code == 200 and r.json() == {"reply": "stub reply"}

def test_identity_comes_from_session_not_body():
    post({"message": "hi", "conversation_id": CID, "agent_id": "evil", "is_admin": True})
    assert CALLS[0][0] == "repA" and CALLS[0][1] is False

def test_admin_flag_comes_from_server_role():
    post(agent="adm", role="admin")
    assert CALLS[0][1] is True

def test_rate_limit_returns_429():
    for _ in range(copilot_routes.RATE_LIMIT):
        assert post().status_code == 200
    assert post().status_code == 429

def test_timeout_returns_504():
    async def slow(*a):
        await asyncio.sleep(1)
    stub.run_copilot = slow
    copilot_routes.TIMEOUT_S = 0.05
    assert post().status_code == 504

def test_internal_error_returns_502_without_leaking():
    async def boom(*a):
        raise RuntimeError("secret internal detail")
    stub.run_copilot = boom
    r = post()
    assert r.status_code == 502 and "secret" not in r.text
