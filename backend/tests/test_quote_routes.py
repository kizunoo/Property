"""backend/tests/test_quote_routes.py

Route tests for rep console supplier quote endpoints.
Tests agent auth, scoping, validation, drafting, approval, idempotent delivery,
activity logging, and DB write isolation.
"""
from __future__ import annotations

import sys
import types
from datetime import datetime, timezone, timedelta
from pathlib import Path
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
import pytest

import quote_routes as routes
from quote_logic import SIM_FOOTER, SIM_LABEL

AGENT_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
AGENT_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
CLIENT_A = "11111111-1111-4111-8111-111111111111"
CLIENT_B = "22222222-2222-4222-8222-222222222222"
ROBOT_PRICED = "33333333-3333-4333-8333-333333333333"
ROBOT_UNPRICED = "44444444-4444-4444-8444-444444444444"


class FakeQuery:
    def __init__(self, table_name: str, store: list, writes: list):
        self.table_name = table_name
        self.store = store
        self.writes = writes
        self.filters = []
        self.order_by = None
        self.limit_val = None
        self.update_payload = None
        self.inserted_rows = None

    def select(self, *a, **k):
        return self

    def insert(self, payload):
        self.writes.append((self.table_name, "insert", payload))
        row = dict(payload)
        if "id" not in row:
            row["id"] = str(uuid.uuid4())
        self.store.append(row)
        self.inserted_rows = [dict(row)]
        return self

    def update(self, payload):
        self.writes.append((self.table_name, "update", payload))
        self.update_payload = payload
        return self

    def eq(self, col, val):
        self.filters.append(lambda r: r.get(col) == val)
        return self

    def neq(self, col, val):
        self.filters.append(lambda r: r.get(col) != val)
        return self

    def in_(self, col, vals):
        self.filters.append(lambda r: r.get(col) in vals)
        return self

    def is_(self, col, val):
        if val == "null":
            self.filters.append(lambda r: r.get(col) is None)
        else:
            self.filters.append(lambda r: r.get(col) == val)
        return self

    def lte(self, col, val):
        self.filters.append(lambda r: r.get(col) is not None and str(r.get(col)) <= str(val))
        return self

    def gt(self, col, val):
        self.filters.append(lambda r: r.get(col) is not None and str(r.get(col)) > str(val))
        return self

    def order(self, col, desc=False):
        self.order_by = (col, desc)
        return self

    def limit(self, n):
        self.limit_val = n
        return self

    def execute(self):
        if self.inserted_rows is not None:
            return types.SimpleNamespace(data=self.inserted_rows)

        rows = [r for r in self.store if all(f(r) for f in self.filters)]
        if self.update_payload is not None:
            updated = []
            for r in rows:
                r.update(self.update_payload)
                updated.append(dict(r))
            return types.SimpleNamespace(data=updated)

        if self.order_by:
            col, desc = self.order_by
            rows.sort(key=lambda r: str(r.get(col) or ""), reverse=desc)

        if self.limit_val is not None:
            rows = rows[: self.limit_val]

        return types.SimpleNamespace(data=[dict(r) for r in rows])


class FakeDB:
    def __init__(self, initial_data: dict):
        self.tables = initial_data
        self.writes = []

    def table(self, name: str):
        store = self.tables.setdefault(name, [])
        return FakeQuery(name, store, self.writes)


def create_initial_db():
    return FakeDB({
        "clients": [
            {
                "id": CLIENT_A,
                "name": "Alpha Corp",
                "assigned_agent_id": AGENT_A,
                "facility_profile": {"facility_type": "warehouse", "floor_area_sqm": 25000},
            },
            {
                "id": CLIENT_B,
                "name": "Beta Corp",
                "assigned_agent_id": AGENT_B,
                "facility_profile": {"facility_type": "manufacturing"},
            },
        ],
        "properties": [
            {
                "id": ROBOT_PRICED,
                "address": "PUDU T300",
                "manufacturer": "Pudu Robotics",
                "property_value": None,
                "indicative_price_myr": 100000.0,
            },
            {
                "id": ROBOT_UNPRICED,
                "address": "Experimental Bot",
                "manufacturer": "RoboCorp",
                "property_value": None,
                "indicative_price_myr": None,
            },
        ],
        "supplier_quote_requests": [],
        "supplier_quotes": [],
        "agent_activity": [],
    })


# Set up test app
app = FastAPI()
app.include_router(routes.router)

current_test_db: FakeDB = create_initial_db()


@app.middleware("http")
async def fake_auth_middleware(request: Request, call_next):
    agent_id = request.headers.get("x-test-agent")
    if agent_id:
        request.state.agent = types.SimpleNamespace(
            agent_id=agent_id,
            role=request.headers.get("x-test-role", "agent"),
        )
    return await call_next(request)


_orig_get_db = routes.triage_service.get_db
client = TestClient(app, raise_server_exceptions=False)

@pytest.fixture(autouse=True)
def reset_db():
    global current_test_db
    current_test_db = create_initial_db()
    routes.triage_service.get_db = lambda: current_test_db
    yield
    routes.triage_service.get_db = _orig_get_db


def test_request_without_auth_is_refused():
    res = client.get("/api/quotes")
    assert res.status_code == 401


def test_market_price_outside_bounds_gives_422():
    headers = {"x-test-agent": AGENT_A}
    res = client.post(
        "/api/quotes/request",
        headers=headers,
        json={
            "client_id": CLIENT_A,
            "property_id": ROBOT_PRICED,
            "market_price_myr": 20000.0,  # below 0.4 * 100000
            "kind": "quote",
        },
    )
    assert res.status_code == 422


def test_robot_without_indicative_price_gives_422():
    headers = {"x-test-agent": AGENT_A}
    res = client.post(
        "/api/quotes/request",
        headers=headers,
        json={
            "client_id": CLIENT_A,
            "property_id": ROBOT_UNPRICED,
            "market_price_myr": 100000.0,
            "kind": "quote",
        },
    )
    assert res.status_code == 422


def test_second_request_same_pair_returns_same_draft():
    headers = {"x-test-agent": AGENT_A}
    payload = {
        "client_id": CLIENT_A,
        "property_id": ROBOT_PRICED,
        "market_price_myr": 100000.0,
        "kind": "quote",
    }
    res1 = client.post("/api/quotes/request", headers=headers, json=payload)
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["status"] == "draft"
    req_id = data1["id"]

    res2 = client.post("/api/quotes/request", headers=headers, json=payload)
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["id"] == req_id
    # Assert only one request exists in DB
    assert len(current_test_db.tables["supplier_quote_requests"]) == 1


def test_approve_moves_draft_to_sent_and_sets_reply_due():
    headers = {"x-test-agent": AGENT_A}
    req = client.post(
        "/api/quotes/request",
        headers=headers,
        json={
            "client_id": CLIENT_A,
            "property_id": ROBOT_PRICED,
            "market_price_myr": 100000.0,
            "kind": "quote",
        },
    ).json()

    approve_res = client.post(
        f"/api/quotes/{req['id']}/approve",
        headers=headers,
        json={"draft_body": "Custom body here"},
    )
    assert approve_res.status_code == 200
    upd = approve_res.json()
    assert upd["status"] == "sent"
    assert upd["sent_at"] is not None
    assert upd["reply_due_at"] is not None

    sent_t = datetime.fromisoformat(upd["sent_at"])
    due_t = datetime.fromisoformat(upd["reply_due_at"])
    diff_s = (due_t - sent_t).total_seconds()
    assert 0 <= diff_s <= 120

    # Activity row request_sent was added
    acts = [a for a in current_test_db.tables["agent_activity"] if a["kind"] == "request_sent"]
    assert len(acts) == 1


def test_approve_on_non_draft_is_refused():
    headers = {"x-test-agent": AGENT_A}
    req = client.post(
        "/api/quotes/request",
        headers=headers,
        json={
            "client_id": CLIENT_A,
            "property_id": ROBOT_PRICED,
            "market_price_myr": 100000.0,
            "kind": "quote",
        },
    ).json()

    # First approve succeeds
    client.post(f"/api/quotes/{req['id']}/approve", headers=headers, json={})
    # Second approve fails with 409
    res = client.post(f"/api/quotes/{req['id']}/approve", headers=headers, json={})
    assert res.status_code == 409


def test_approve_reappends_simulated_footer_if_removed():
    headers = {"x-test-agent": AGENT_A}
    req = client.post(
        "/api/quotes/request",
        headers=headers,
        json={
            "client_id": CLIENT_A,
            "property_id": ROBOT_PRICED,
            "market_price_myr": 100000.0,
            "kind": "quote",
        },
    ).json()

    approve_res = client.post(
        f"/api/quotes/{req['id']}/approve",
        headers=headers,
        json={"draft_body": "Rep stripped all notices"},
    )
    assert approve_res.status_code == 200
    body = approve_res.json()["draft_body"]
    assert SIM_FOOTER in body


def test_delivery_creates_quote_and_supersedes_older():
    headers = {"x-test-agent": AGENT_A}
    past = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()

    # Insert an existing older quote
    older_quote_id = str(uuid.uuid4())
    current_test_db.tables["supplier_quotes"].append({
        "id": older_quote_id,
        "agent_id": AGENT_A,
        "client_id": CLIENT_A,
        "property_id": ROBOT_PRICED,
        "price_myr": 110000,
        "issued_at": past,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=10)).isoformat(),
        "superseded_by": None,
        "is_simulated": True,
    })

    # Insert a sent request that is due
    req_id = str(uuid.uuid4())
    current_test_db.tables["supplier_quote_requests"].append({
        "id": req_id,
        "agent_id": AGENT_A,
        "client_id": CLIENT_A,
        "property_id": ROBOT_PRICED,
        "kind": "quote",
        "status": "sent",
        "market_price_myr": 100000.0,
        "sent_at": past,
        "reply_due_at": past,
        "created_at": past,
    })

    res = client.get("/api/quotes", headers=headers)
    assert res.status_code == 200
    data = res.json()

    # Request is now quoted
    req_in_db = [r for r in current_test_db.tables["supplier_quote_requests"] if r["id"] == req_id][0]
    assert req_in_db["status"] == "quoted"

    # Exactly one new quote created
    new_quotes = [q for q in current_test_db.tables["supplier_quotes"] if q["id"] != older_quote_id]
    assert len(new_quotes) == 1
    new_quote = new_quotes[0]
    assert new_quote["is_simulated"] is True
    assert new_quote["price_myr"] > 0

    # Older quote was superseded
    old_q = [q for q in current_test_db.tables["supplier_quotes"] if q["id"] == older_quote_id][0]
    assert old_q["superseded_by"] == new_quote["id"]

    # Activity quote_received was added
    acts = [a for a in current_test_db.tables["agent_activity"] if a["kind"] == "quote_received"]
    assert len(acts) == 1


def test_delivery_not_yet_due_does_nothing():
    headers = {"x-test-agent": AGENT_A}
    future = (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat()

    req_id = str(uuid.uuid4())
    current_test_db.tables["supplier_quote_requests"].append({
        "id": req_id,
        "agent_id": AGENT_A,
        "client_id": CLIENT_A,
        "property_id": ROBOT_PRICED,
        "kind": "quote",
        "status": "sent",
        "market_price_myr": 100000.0,
        "sent_at": future,
        "reply_due_at": future,
        "created_at": future,
    })

    res = client.get("/api/quotes", headers=headers)
    assert res.status_code == 200
    assert len(current_test_db.tables["supplier_quotes"]) == 0
    req_in_db = [r for r in current_test_db.tables["supplier_quote_requests"] if r["id"] == req_id][0]
    assert req_in_db["status"] == "sent"


def test_two_get_calls_in_a_row_create_one_quote():
    headers = {"x-test-agent": AGENT_A}
    past = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()

    req_id = str(uuid.uuid4())
    current_test_db.tables["supplier_quote_requests"].append({
        "id": req_id,
        "agent_id": AGENT_A,
        "client_id": CLIENT_A,
        "property_id": ROBOT_PRICED,
        "kind": "quote",
        "status": "sent",
        "market_price_myr": 100000.0,
        "sent_at": past,
        "reply_due_at": past,
        "created_at": past,
    })

    client.get("/api/quotes", headers=headers)
    client.get("/api/quotes", headers=headers)

    quotes = current_test_db.tables["supplier_quotes"]
    assert len(quotes) == 1


def test_another_agent_requests_never_returned_or_delivered():
    past = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    # Agent A's request
    req_a = str(uuid.uuid4())
    current_test_db.tables["supplier_quote_requests"].append({
        "id": req_a,
        "agent_id": AGENT_A,
        "client_id": CLIENT_A,
        "property_id": ROBOT_PRICED,
        "kind": "quote",
        "status": "sent",
        "market_price_myr": 100000.0,
        "sent_at": past,
        "reply_due_at": past,
        "created_at": past,
    })

    # Agent B queries quotes
    res = client.get("/api/quotes", headers={"x-test-agent": AGENT_B})
    assert res.status_code == 200
    data = res.json()
    assert len(data["requests"]) == 0
    assert len(data["quotes"]) == 0

    # Agent A's request was NOT delivered by Agent B's GET
    req_in_db = [r for r in current_test_db.tables["supplier_quote_requests"] if r["id"] == req_a][0]
    assert req_in_db["status"] == "sent"


def test_log_refuses_unknown_kind_and_unowned_ref_id():
    headers = {"x-test-agent": AGENT_A}
    quote_a = str(uuid.uuid4())
    current_test_db.tables["supplier_quotes"].append({
        "id": quote_a,
        "agent_id": AGENT_B,  # belongs to B
        "client_id": CLIENT_B,
        "property_id": ROBOT_PRICED,
        "price_myr": 100000,
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=14)).isoformat(),
        "is_simulated": True,
    })

    # Unknown kind rejected with 422
    res_bad_kind = client.post(
        "/api/quotes/log",
        headers=headers,
        json={"kind": "invalid_kind", "ref_id": quote_a, "summary": "test"},
    )
    assert res_bad_kind.status_code == 422

    # Unowned ref_id rejected with 403
    res_unowned = client.post(
        "/api/quotes/log",
        headers=headers,
        json={"kind": "expiry_dismissed", "ref_id": quote_a, "summary": "test"},
    )
    assert res_unowned.status_code == 403


def test_no_route_writes_to_properties_or_pipeline_evaluations():
    headers = {"x-test-agent": AGENT_A}
    # Run a full lifecycle
    req_res = client.post(
        "/api/quotes/request",
        headers=headers,
        json={
            "client_id": CLIENT_A,
            "property_id": ROBOT_PRICED,
            "market_price_myr": 100000.0,
            "kind": "quote",
        },
    ).json()

    client.post(f"/api/quotes/{req_res['id']}/approve", headers=headers, json={})

    # Make due
    for r in current_test_db.tables["supplier_quote_requests"]:
        r["reply_due_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()

    client.get("/api/quotes", headers=headers)

    quote = current_test_db.tables["supplier_quotes"][0]
    client.post(
        "/api/quotes/log",
        headers=headers,
        json={"kind": "expiry_followup_sent", "ref_id": quote["id"], "summary": "done"},
    )

    # Check all writes
    for table_name, action, payload in current_test_db.writes:
        assert table_name not in (
            "properties",
            "pipeline_evaluations",
        ), f"Route wrote to forbidden table: {table_name}"
