import asyncio
import importlib.util
import json
import logging
import sys
from pathlib import Path

import pytest

backend_dir = Path(__file__).resolve().parents[1]
tests_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
if str(tests_dir) not in sys.path:
    sys.path.insert(0, str(tests_dir))

# Load the real reply_agent module in an isolated namespace to avoid conflicting
# with other test suites that stub sys.modules["reply_agent"].
spec = importlib.util.spec_from_file_location("real_reply_agent", backend_dir / "reply_agent.py")
reply_agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reply_agent)

import copilot_tools as ct
import reply_context as rc
import triage_service
from copilot_tools import Identity
from test_inquiry_resolution import C1, DB, I1, REP_A

VALID_DRAFT = "Dear Alpha Sdn Bhd, thank you for contacting us. Best regards,"
VALID_JSON_REPLY = json.dumps({
    "draft": VALID_DRAFT,
    "product": None,
    "facts_used": [],
    "missing": []
})


def _setup_db():
    db = DB({
        "clients": [{"id": C1, "name": "Alpha Sdn Bhd", ct.CLIENT_AGENT_COL: REP_A}],
        "client_inquiries": [
            {"id": I1, "client_id": C1, ct.INQUIRY_TEXT_COL: "Need help", "status": "open", "created_at": "2026-10-20T01:00:00+00:00"}
        ],
        "inquiry_messages": [],
        ct.ROBOT_TABLE: [],
        ct.EVAL_TABLE: [],
    })
    triage_service.set_db(db)
    return db


# =============================================================================
# PART B1: Cascade Tests (a-g)
# =============================================================================

def test_cascade_first_raises_second_succeeds(monkeypatch):
    """(a) The first model raises an exception and the second returns valid JSON."""
    _setup_db()
    called = []

    async def mock_run(identity, inquiry_id, run_id, model_name=""):
        called.append(model_name)
        if len(called) == 1:
            raise RuntimeError("Primary model connection failed")
        return VALID_JSON_REPLY

    monkeypatch.setattr(reply_agent, "_run", mock_run)
    res = asyncio.run(reply_agent.suggest_reply(Identity(agent_id=REP_A, is_admin=False), I1))

    assert res is not None
    assert res["draft"] == VALID_DRAFT
    assert len(called) == 2


def test_cascade_first_invalid_json_second_succeeds(monkeypatch):
    """(b) The first model returns invalid JSON and the second returns valid JSON."""
    _setup_db()
    called = []

    async def mock_run(identity, inquiry_id, run_id, model_name=""):
        called.append(model_name)
        if len(called) == 1:
            return "This is not valid JSON string at all"
        return VALID_JSON_REPLY

    monkeypatch.setattr(reply_agent, "_run", mock_run)
    res = asyncio.run(reply_agent.suggest_reply(Identity(agent_id=REP_A, is_admin=False), I1))

    assert res is not None
    assert res["draft"] == VALID_DRAFT
    assert len(called) == 2


def test_cascade_all_models_fail_returns_none(monkeypatch):
    """(c) Every model fails or returns invalid JSON, so suggest_reply returns None."""
    _setup_db()

    async def mock_run(identity, inquiry_id, run_id, model_name=""):
        raise RuntimeError(f"Model {model_name} failed")

    monkeypatch.setattr(reply_agent, "_run", mock_run)
    res = asyncio.run(reply_agent.suggest_reply(Identity(agent_id=REP_A, is_admin=False), I1))

    assert res is None


def test_cascade_model_order_and_deduplication(monkeypatch):
    """(d) Models are tried in order MODEL then FALLBACK_MODELS without duplicates."""
    _setup_db()
    called = []

    monkeypatch.setattr(reply_agent, "MODEL", "gemini-2.5-flash")
    monkeypatch.setattr(reply_agent, "FALLBACK_MODELS", ["gemini-3.5-flash", "gemini-2.5-flash", "gemini-2.5-flash-lite"])

    async def mock_run(identity, inquiry_id, run_id, model_name=""):
        called.append(model_name)
        raise RuntimeError("Fail to force complete cascade")

    monkeypatch.setattr(reply_agent, "_run", mock_run)
    res = asyncio.run(reply_agent.suggest_reply(Identity(agent_id=REP_A, is_admin=False), I1))

    assert res is None
    assert called == ["gemini-2.5-flash", "gemini-3.5-flash", "gemini-2.5-flash-lite"]


def test_cascade_429_and_503_trigger_next_model(monkeypatch):
    """(e) A 429-style exception and a 503-style exception both trigger the next model."""
    _setup_db()
    called = []

    class RateLimit429(Exception):
        pass

    class ServiceUnavailable503(Exception):
        pass

    async def mock_run(identity, inquiry_id, run_id, model_name=""):
        called.append(model_name)
        if len(called) == 1:
            raise RateLimit429("429 RESOURCE_EXHAUSTED")
        if len(called) == 2:
            raise ServiceUnavailable503("503 UNAVAILABLE: High demand")
        return VALID_JSON_REPLY

    monkeypatch.setattr(reply_agent, "_run", mock_run)
    res = asyncio.run(reply_agent.suggest_reply(Identity(agent_id=REP_A, is_admin=False), I1))

    assert res is not None
    assert res["draft"] == VALID_DRAFT
    assert len(called) == 3


def test_cascade_remaining_models_called_exactly_once(monkeypatch):
    """(f) After a first-model failure the remaining models are called exactly once each."""
    _setup_db()
    call_counts = {}

    monkeypatch.setattr(reply_agent, "MODEL", "model-primary")
    monkeypatch.setattr(reply_agent, "FALLBACK_MODELS", ["model-backup-1", "model-backup-2", "model-backup-3"])

    async def mock_run(identity, inquiry_id, run_id, model_name=""):
        call_counts[model_name] = call_counts.get(model_name, 0) + 1
        raise RuntimeError("Fail all")

    monkeypatch.setattr(reply_agent, "_run", mock_run)
    res = asyncio.run(reply_agent.suggest_reply(Identity(agent_id=REP_A, is_admin=False), I1))

    assert res is None
    assert call_counts == {
        "model-primary": 1,
        "model-backup-1": 1,
        "model-backup-2": 1,
        "model-backup-3": 1,
    }


def test_cascade_exception_detail_not_logged_only_type_name(caplog, monkeypatch):
    """(g) Exception detail is not written to the log, only its type name."""
    _setup_db()
    secret_token = "SUPER_SECRET_INTERNAL_KEY_987654321"

    async def mock_run(identity, inquiry_id, run_id, model_name=""):
        if model_name == reply_agent.MODEL:
            raise RuntimeError(f"Fatal error with {secret_token}")
        return VALID_JSON_REPLY

    monkeypatch.setattr(reply_agent, "_run", mock_run)
    with caplog.at_level(logging.WARNING, logger="reply"):
        res = asyncio.run(reply_agent.suggest_reply(Identity(agent_id=REP_A, is_admin=False), I1))

    assert res is not None
    assert "RuntimeError" in caplog.text
    assert secret_token not in caplog.text


# =============================================================================
# PART B2: Price Safety Tests (h, i)
# =============================================================================

def test_price_safety_null_property_value_indicative_never_leaked():
    """(h) With property_value null and indicative_price_myr set, neither the indicative number nor 'indicative' nor 'demo estimate' reach fact sheet or prompt."""
    row = {
        "id": "robot-no-price",
        ct.ROBOT_NAME_COL: "Warehouse Bot V2",
        "property_value": None,
        "indicative_price_myr": 88888,
        "data_source": "real",
    }
    sheet = rc.product_sheet(row)
    sheet_json = json.dumps(sheet)

    # 1. Indicative price value must not appear in fact sheet
    assert "88888" not in sheet_json
    # 2. 'indicative' must not appear in fact sheet
    assert "indicative" not in sheet_json.lower()
    # 3. 'demo estimate' must not appear in fact sheet
    assert "demo estimate" not in sheet_json.lower()

    # Fact sheet shows 'Not in the catalog' for unpriced unit
    facts = {f["label"]: f["value"] for f in sheet["facts"]}
    assert facts.get("Unit cost (RM)") == "Not in the catalog"

    # Also verify prompt text and system instruction never reference indicative or demo prices
    assert "indicative_price_myr" not in reply_agent.INSTRUCTION
    assert "demo estimate" not in reply_agent.INSTRUCTION


def test_price_safety_real_property_value_preserved():
    """(i) With a real property_value set, the fact sheet shows it as before."""
    row = {
        "id": "robot-real-price",
        ct.ROBOT_NAME_COL: "CleanBot Pro",
        "property_value": 75000,
        "data_source": "real",
    }
    sheet = rc.product_sheet(row)
    facts = {f["label"]: f["value"] for f in sheet["facts"]}
    assert facts.get("Unit cost (RM)") == "75000"
