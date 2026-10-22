"""Route tests for resolve / reopen / history / suggest-reply. Services stubbed; no DB, no AI."""
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import inquiry_actions_routes as routes  # noqa: E402
import inquiry_detail  # noqa: E402
import inquiry_resolution  # noqa: E402
import triage_service  # noqa: E402

OK = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
SEEN, SUGGEST_CALLS = [], []
app = FastAPI()
app.include_router(routes.router)


@app.middleware("http")
async def fake_auth(request: Request, call_next):
    who = request.headers.get("x-test-agent")
    if who:
        request.state.agent = types.SimpleNamespace(agent_id=who, role=request.headers.get("x-test-role", "agent"))
    return await call_next(request)


client = TestClient(app, raise_server_exceptions=False)

stub = types.ModuleType("reply_agent")


async def _suggest(identity, inquiry_id):
    SUGGEST_CALLS.append((identity, inquiry_id))
    return {"draft": "Hello", "product": None, "facts_used": [], "missing": [], "warnings": [], "uses_demo_data": False}

stub.suggest_reply = _suggest
sys.modules["reply_agent"] = stub


def setup_function(_):
    SEEN.clear(); SUGGEST_CALLS.clear(); routes._hits.clear()
    triage_service.set_db(object())
    stub.suggest_reply = _suggest
    inquiry_resolution.resolve_inquiry = lambda db, ident, iid, note=None: (SEEN.append((ident, note)) or "ok")
    inquiry_resolution.reopen_inquiry = lambda db, ident, iid: "ok"
    inquiry_resolution.list_company_history = lambda db, ident, cid: {"client_id": cid, "inquiries": []}
    inquiry_detail.get_inquiry_detail = lambda db, ident, iid: {"inquiry": {}} if iid == OK else None
    routes._audit = lambda *a, **k: None


def call(method, path, agent="repA", role="agent", **kw):
    headers = {"x-test-agent": agent, "x-test-role": role} if agent else {}
    return getattr(client, method)(path, headers=headers, **kw)


def test_all_routes_require_agent_session():
    for method, path in (("post", f"/api/console/inquiry/{OK}/resolve"), ("post", f"/api/console/inquiry/{OK}/reopen"),
                         ("get", f"/api/console/clients/{OK}/inquiry-history"),
                         ("post", f"/api/console/inquiry/{OK}/suggest-reply")):
        kw = {"json": {}} if path.endswith("resolve") else {}
        assert call(method, path, agent=None, **kw).status_code == 401, path

def test_resolve_ok_note_and_identity_from_session():
    r = call("post", f"/api/console/inquiry/{OK}/resolve?agent_id=evil", json={"note": "Done", "agent_id": "evil"})
    assert r.status_code == 200 and SEEN[0][0].agent_id == "repA" and SEEN[0][1] == "Done"

def test_resolve_note_too_long_is_422():
    assert call("post", f"/api/console/inquiry/{OK}/resolve", json={"note": "x" * 501}).status_code == 422

def test_resolve_conflict_and_not_found_codes():
    inquiry_resolution.resolve_inquiry = lambda *a, **k: "already_resolved"
    assert call("post", f"/api/console/inquiry/{OK}/resolve", json={}).status_code == 409
    inquiry_resolution.resolve_inquiry = lambda *a, **k: "not_found"
    assert call("post", f"/api/console/inquiry/{OK}/resolve", json={}).status_code == 404

def test_reopen_codes():
    inquiry_resolution.reopen_inquiry = lambda *a, **k: "not_resolved"
    assert call("post", f"/api/console/inquiry/{OK}/reopen").status_code == 409
    inquiry_resolution.reopen_inquiry = lambda *a, **k: "not_found"
    assert call("post", f"/api/console/inquiry/{OK}/reopen").status_code == 404

def test_history_ok_and_404():
    assert call("get", f"/api/console/clients/{OK}/inquiry-history").status_code == 200
    inquiry_resolution.list_company_history = lambda *a, **k: None
    assert call("get", f"/api/console/clients/{OK}/inquiry-history").status_code == 404

def test_suggest_reply_ok_and_identity_from_server():
    r = call("post", f"/api/console/inquiry/{OK}/suggest-reply?is_admin=true")
    assert r.status_code == 200 and r.json()["draft"] == "Hello"
    assert SUGGEST_CALLS[0][0].agent_id == "repA" and SUGGEST_CALLS[0][0].is_admin is False

def test_suggest_reply_unknown_inquiry_404_without_calling_ai():
    r = call("post", "/api/console/inquiry/cccccccc-cccc-4ccc-8ccc-cccccccccccc/suggest-reply")
    assert r.status_code == 404 and SUGGEST_CALLS == []

def test_suggest_reply_rate_limited():
    for _ in range(routes.SUGGEST_LIMIT):
        assert call("post", f"/api/console/inquiry/{OK}/suggest-reply").status_code == 200
    assert call("post", f"/api/console/inquiry/{OK}/suggest-reply").status_code == 429

def test_suggest_reply_failures_are_502_without_leaking():
    async def boom(identity, iid): raise RuntimeError("secret internal detail")
    stub.suggest_reply = boom
    r = call("post", f"/api/console/inquiry/{OK}/suggest-reply")
    assert r.status_code == 502 and "secret" not in r.text
    async def none(identity, iid): return None
    stub.suggest_reply = none
    assert call("post", f"/api/console/inquiry/{OK}/suggest-reply").status_code == 502

def test_503_when_db_not_ready():
    triage_service.set_db(None)
    assert call("get", f"/api/console/clients/{OK}/inquiry-history").status_code == 503
