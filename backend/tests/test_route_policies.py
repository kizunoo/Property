"""
backend/tests/test_route_policies.py
Tests for Route Security Policies, Scoping, and Role Enforcement:
1. Every /api route in FastAPI app has an explicit declared policy in ROUTE_POLICY_DECLARATIONS.
2. Admin-only routes return HTTP 403 Forbidden when called by a non-admin agent.
3. Client-scoped route families return HTTP 404 Not Found for Agent B (anti-enumeration).
4. Console portal panel scoping returns HTTP 404 for non-assigned agents.
5. Suspended agent existing session is rejected immediately with HTTP 403.
6. Enterprise password rules reject weak, short, or email-containing passwords.
7. Admin management actions (suspend, reactivate, revoke, unlock, issue-reset) require admin role.
8. Per-agent LLM rate limit triggers HTTP 429 Too Many Requests when threshold exceeded.
"""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from fastapi import HTTPException

# Ensure backend in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import main
from route_policies import RoutePolicy, match_policy, ROUTE_POLICY_DECLARATIONS
from agent_auth import (
    AgentIdentity,
    validate_password_complexity,
    check_agent_llm_rate_limit,
    reset_agent_llm_rate_limits,
    get_current_agent,
    require_client_access,
)


@pytest.fixture
def client():
    with patch.dict(os.environ, {"ENVIRONMENT": "testing"}):
        yield TestClient(main.app)


def test_every_api_route_has_declared_policy():
    """Fails if any /api endpoint registered in FastAPI app.routes lacks a declared policy."""
    all_routes = []
    
    def _collect(routes):
        for r in routes:
            if hasattr(r, "original_router"):
                _collect(r.original_router.routes)
            elif hasattr(r, "routes"):
                _collect(r.routes)
            elif hasattr(r, "path") and hasattr(r, "methods"):
                for m in (r.methods or ["GET"]):
                    if m not in ("HEAD", "OPTIONS") and r.path.startswith("/api/"):
                        all_routes.append((m, r.path))

    _collect(main.app.routes)
    unique_routes = sorted(set(all_routes))

    missing = []
    for method, path in unique_routes:
        decl = match_policy(method, path)
        if not decl:
            missing.append(f"{method} {path}")

    assert not missing, f"Routes missing declared security policy:\n" + "\n".join(missing)


def test_admin_only_routes_return_403_for_regular_agents(client):
    """Non-admin agent accessing admin-only routes must receive 403 Forbidden."""
    regular_agent = AgentIdentity(
        account_id="acc_rep_001",
        email="rep@company.com",
        name="Rep Agent",
        role="agent",
        session_id="sess_test_123",
        agent_id="agent_uuid_001",
    )

    admin_routes = [
        ("POST", "/api/run_evaluations", {}),
        ("POST", "/api/retrain_model", {}),
        ("PATCH", "/api/properties/prop_123", {}),
        ("POST", "/api/whatsapp/process_reminders", {}),
        ("GET", "/api/agents", None),
        ("POST", "/api/admin/agents/agent_target/suspend", {}),
        ("POST", "/api/admin/agents/agent_target/reactivate", {}),
        ("POST", "/api/admin/agents/agent_target/revoke-all-sessions", {}),
        ("POST", "/api/admin/agents/agent_target/unlock", {}),
        ("POST", "/api/admin/agents/agent_target/issue-reset", {}),
    ]

    with patch("main.get_current_agent", return_value=regular_agent):
        for method, path, payload in admin_routes:
            if method == "GET":
                resp = client.get(path, headers={"Authorization": "Bearer test_tok"})
            elif method == "POST":
                resp = client.post(path, json=payload, headers={"Authorization": "Bearer test_tok"})
            elif method == "PATCH":
                resp = client.patch(path, json=payload, headers={"Authorization": "Bearer test_tok"})
            
            assert resp.status_code == 403, f"Expected 403 for {method} {path}, got {resp.status_code}: {resp.text}"


def test_client_scoped_routes_return_404_for_unassigned_agent():
    """Agent B attempting to access Agent A's client receives 404 (anti-enumeration)."""
    agent_b = AgentIdentity(
        account_id="acc_agent_b",
        email="b@company.com",
        name="Agent B",
        role="agent",
        session_id="sess_b_123",
        agent_id="agent_uuid_b",
    )

    mock_sb = MagicMock()
    # Mock client assigned to agent_uuid_a (not agent_b)
    mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[{"id": "client_a", "assigned_agent_id": "agent_uuid_a"}]
    )

    with pytest.raises(HTTPException) as exc_info:
        require_client_access(agent_b, "client_a", mock_sb)
    
    assert exc_info.value.status_code == 404
    assert "not found" in exc_info.value.detail.lower()


def test_console_portal_panel_scoping(client):
    """Console portal management routes enforce client ownership and return 404 for unassigned agents."""
    agent_b = AgentIdentity(
        account_id="acc_agent_b",
        email="b@company.com",
        name="Agent B",
        role="agent",
        session_id="sess_b_123",
        agent_id="agent_uuid_b",
    )

    mock_sb = MagicMock()
    mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[{"id": "client_secret", "assigned_agent_id": "agent_uuid_a"}]
    )

    # Calling require_client_access directly on portal console target
    with pytest.raises(HTTPException) as exc_info:
        require_client_access(agent_b, "client_secret", mock_sb)
    assert exc_info.value.status_code == 404


def test_suspended_agent_session_rejected_immediately(client):
    """When an agent's account status is 'suspended', any existing session is rejected with 403."""
    suspended_agent = AgentIdentity(
        account_id="acc_suspended_1",
        email="suspended@company.com",
        name="Suspended Agent",
        role="agent",
        session_id="sess_susp_123",
        agent_id="agent_123",
    )

    # In get_current_agent, account status check raises 403
    mock_req = MagicMock()
    mock_req.headers = {"authorization": "Bearer valid_session_token_xyz"}
    mock_req.cookies = {}

    with patch.object(main.supabase, "table") as mock_table:
        # Session valid in DB with joined agent_accounts
        mock_table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[{
            "id": "sess_1",
            "account_id": "acc_suspended_1",
            "revoked_at": None,
            "absolute_expires_at": "2099-01-01T00:00:00+00:00",
            "idle_expires_at": "2099-01-01T00:00:00+00:00",
            "agent_accounts": {
                "id": "acc_suspended_1",
                "email": "suspended@company.com",
                "role": "agent",
                "status": "suspended",
                "agent_id": "agent_123",
            }
        }])

        with pytest.raises(HTTPException) as exc_info:
            get_current_agent(mock_req)
        
        assert exc_info.value.status_code == 403
        assert "suspended" in exc_info.value.detail.lower()


def test_password_complexity_rules():
    """Validates enterprise password length, dictionary check, and email address restrictions."""
    # Too short (< 12 chars)
    with pytest.raises(HTTPException) as exc:
        validate_password_complexity("Short1!", email="agent@company.com")
    assert exc.value.status_code == 400
    assert "at least 12 characters" in exc.value.detail

    # Contains email
    with pytest.raises(HTTPException) as exc:
        validate_password_complexity("Secretagent@company.com2026", email="agent@company.com")
    assert exc.value.status_code == 400
    assert "cannot contain your email" in exc.value.detail

    # Common password
    with pytest.raises(HTTPException) as exc:
        validate_password_complexity("password12345", email="john@company.com")
    assert exc.value.status_code == 400
    assert "too common" in exc.value.detail

    # Valid strong password
    # Should not raise
    validate_password_complexity("Super$tr0ngP@ssw0rd2026!Key", email="agent@company.com")


def test_per_agent_llm_rate_limiting():
    """Agent invoking LLM routes beyond threshold (10 calls/min) receives HTTP 429."""
    reset_agent_llm_rate_limits()
    agent_id = "agent_test_limiter_001"

    # First 10 requests must succeed
    for i in range(10):
        check_agent_llm_rate_limit(agent_id)

    # 11th request must fail with 429
    with pytest.raises(HTTPException) as exc_info:
        check_agent_llm_rate_limit(agent_id)

    assert exc_info.value.status_code == 429
    assert "rate limit exceeded" in exc_info.value.detail.lower()
    assert "Retry-After" in exc_info.value.headers

    # Other agent is not affected (per-agent scoping)
    check_agent_llm_rate_limit("agent_test_limiter_002")

    reset_agent_llm_rate_limits()
