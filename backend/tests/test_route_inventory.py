"""
backend/tests/test_route_inventory.py
────────────────────────────────────
Enforcement and Route Inventory Test Suite (Part D Items 4, 6, 7, 8):
1. Route Inventory:
   - Iterates over all registered FastAPI app.routes starting with /api/
   - Calls each route with no credentials and asserts 401 or 403 unless allowlisted.
   - Fails the build if an unallowlisted route permits unauthenticated access.
2. Cross-Auth Isolation:
   - Portal cookie used on an agent route is rejected with 401.
   - Agent cookie used on a portal route is rejected with 401.
3. Session State & Revocation:
   - Expired session is rejected with 401.
   - Revoked session is rejected with 401.
   - Suspended agent account is rejected with 403.
4. Header Tampering:
   - X-Agent-Id header is completely ignored; unauthenticated requests cannot spoof identity.
5. Scoping:
   - Agent A cannot view or mutate Agent B's client data (returns 404).
   - Admin can access any client data.
"""

import os
import sys
import re
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Ensure test mode does not bypass authentication in route inventory
os.environ["WHATSAPP_TEST_MODE"] = "false"
os.environ["PORTAL_CODE_PEPPER"] = "test-pepper-route-inventory-12345"

from main import app, AGENT_AUTH_ALLOWLIST
from agent_auth import (
    AgentIdentity,
    hash_agent_token,
    check_client_access,
    require_client_access,
    filter_clients_for_agent,
    require_conversation_access,
)


@pytest.fixture
def client():
    # Ensure WHATSAPP_TEST_MODE is disabled during these tests
    with patch.dict(os.environ, {"WHATSAPP_TEST_MODE": "false", "ENVIRONMENT": "test"}):
        yield TestClient(app)


def test_route_inventory_default_deny(client):
    """
    Iterates over all registered /api/ routes in the FastAPI application.
    For every unallowlisted route, calling it without auth must yield 401 or 403.
    """
    unauthenticated_leaks = []
    checked_routes = set()

    for route in app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if not path or not path.startswith("/api/"):
            continue

        # Check if path matches explicit allowlist
        is_allowlisted = any(pattern.match(path) for pattern in AGENT_AUTH_ALLOWLIST)
        if is_allowlisted:
            continue

        route_key = f"{path}"
        if route_key in checked_routes:
            continue
        checked_routes.add(route_key)

        # Build a concrete test path if parameterized
        test_path = path
        test_path = re.sub(r"\{clientId\}|\{client_id\}", "test-client-id", test_path)
        test_path = re.sub(r"\{propertyId\}|\{property_id\}", "test-prop-id", test_path)
        test_path = re.sub(r"\{viewingId\}|\{viewing_id\}", "test-viewing-id", test_path)
        test_path = re.sub(r"\{conversationId\}|\{conversation_id\}", "test-conv-id", test_path)
        test_path = re.sub(r"\{id\}", "test-id", test_path)

        # Call with primary method
        method = "GET"
        if methods and "GET" not in methods:
            method = list(methods)[0]

        if method == "GET":
            resp = client.get(test_path)
        elif method == "POST":
            resp = client.post(test_path, json={})
        elif method == "PATCH":
            resp = client.patch(test_path, json={})
        elif method == "DELETE":
            resp = client.delete(test_path)
        else:
            resp = client.get(test_path)

        # Must be rejected with 401 or 403 (or 404 for simulate endpoints in prod)
        if resp.status_code not in (401, 403):
            unauthenticated_leaks.append((path, method, resp.status_code, resp.text[:120]))

    assert not unauthenticated_leaks, (
        f"Security Violation: Found {len(unauthenticated_leaks)} unauthenticated routes not in allowlist:\n"
        + "\n".join([f"  - [{m}] {p} -> {sc}: {txt}" for p, m, sc, txt in unauthenticated_leaks])
    )


def test_cross_auth_portal_cookie_rejected_on_agent_route(client):
    """A portal_session cookie must be rejected on agent endpoints with 401."""
    resp = client.get(
        "/api/daily_worklist",
        cookies={"portal_session": "portal_mock_token_123"},
    )
    assert resp.status_code == 401
    assert "Portal session tokens cannot be used to authenticate agent endpoints" in resp.json()["detail"]


def test_cross_auth_agent_cookie_rejected_on_portal_route(client):
    """An agent_session cookie must be rejected on portal endpoints with 401."""
    resp = client.get(
        "/api/portal/client-123/dashboard",
        cookies={"agent_session": "agent_mock_token_123"},
    )
    assert resp.status_code == 401
    assert "Agent session tokens cannot be used to authenticate client portal endpoints" in resp.json()["detail"]


def test_spoofed_x_agent_id_header_ignored(client):
    """Passing X-Agent-Id without a valid session token must be rejected with 401."""
    resp = client.get(
        "/api/daily_worklist",
        headers={"X-Agent-Id": "admin-system-id"},
    )
    assert resp.status_code == 401
    assert "Authentication required" in resp.json()["detail"]


def test_expired_agent_session_rejected(client):
    """An agent session that has passed idle or absolute expiration must return 401."""
    raw_token = "sess_expired_test_abc"
    token_h = hash_agent_token(raw_token)
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()

    mock_session_row = {
        "id": "sess-expired-id",
        "agent_id": "agent-123",
        "idle_expires_at": past,
        "absolute_expires_at": past,
        "revoked_at": None,
        "agent_accounts": {
            "id": "agent-123",
            "email": "agent@pipeline-ev.com",
            "name": "Expired Agent",
            "role": "agent",
            "status": "active",
            "locked_until": None,
        },
    }

    mock_sb = MagicMock()
    mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[mock_session_row]
    )

    with patch("main.supabase", mock_sb):
        resp = client.get(
            "/api/daily_worklist",
            cookies={"agent_session": raw_token},
        )
        assert resp.status_code == 401
        assert "Session expired" in resp.json()["detail"]


def test_revoked_agent_session_rejected(client):
    """A revoked agent session must return 401."""
    raw_token = "sess_revoked_test_xyz"
    token_h = hash_agent_token(raw_token)
    now = datetime.now(timezone.utc)
    future = (now + timedelta(hours=8)).isoformat()

    mock_session_row = {
        "id": "sess-revoked-id",
        "agent_id": "agent-123",
        "idle_expires_at": future,
        "absolute_expires_at": future,
        "revoked_at": now.isoformat(),
        "agent_accounts": {
            "id": "agent-123",
            "email": "agent@pipeline-ev.com",
            "name": "Revoked Agent",
            "role": "agent",
            "status": "active",
            "locked_until": None,
        },
    }

    mock_sb = MagicMock()
    mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[mock_session_row]
    )

    with patch("main.supabase", mock_sb):
        resp = client.get(
            "/api/daily_worklist",
            cookies={"agent_session": raw_token},
        )
        assert resp.status_code == 401
        assert "revoked" in resp.json()["detail"].lower()


def test_suspended_agent_account_rejected(client):
    """An agent whose account is suspended must return 403."""
    raw_token = "sess_suspended_test"
    now = datetime.now(timezone.utc)
    future = (now + timedelta(hours=8)).isoformat()

    mock_session_row = {
        "id": "sess-suspended-id",
        "agent_id": "agent-123",
        "idle_expires_at": future,
        "absolute_expires_at": future,
        "revoked_at": None,
        "agent_accounts": {
            "id": "agent-123",
            "email": "agent@pipeline-ev.com",
            "name": "Suspended Agent",
            "role": "agent",
            "status": "suspended",
            "locked_until": None,
        },
    }

    mock_sb = MagicMock()
    mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[mock_session_row]
    )

    with patch("main.supabase", mock_sb):
        resp = client.get(
            "/api/daily_worklist",
            cookies={"agent_session": raw_token},
        )
        assert resp.status_code == 403
        assert "suspended" in resp.json()["detail"].lower()


def test_agent_scoping_isolation():
    """
    Test AGENT_PIPELINE_SCOPING logic:
    - Agent A cannot access Agent B's client.
    - Admin can access any client.
    - When scoping is 'shared', any agent can access any client.
    """
    agent_a = AgentIdentity("acc-a", "a@test.com", "Agent A", "agent", "sess-a", agent_id="agent-A")
    agent_b = AgentIdentity("acc-b", "b@test.com", "Agent B", "agent", "sess-b", agent_id="agent-B")
    admin = AgentIdentity("admin-1", "admin@test.com", "Admin", "admin", "sess-admin", agent_id=None)

    mock_sb = MagicMock()
    # Client 100 assigned to agent-A
    mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[{"id": "client-100", "assigned_agent_id": "agent-A"}]
    )

    # 1. Under default 'assigned' scoping:
    with patch.dict(os.environ, {"AGENT_PIPELINE_SCOPING": "assigned"}):
        assert check_client_access(agent_a, "client-100", mock_sb) is True
        assert check_client_access(agent_b, "client-100", mock_sb) is False
        assert check_client_access(admin, "client-100", mock_sb) is True

    # 2. Under 'shared' scoping:
    with patch.dict(os.environ, {"AGENT_PIPELINE_SCOPING": "shared"}):
        assert check_client_access(agent_a, "client-100", mock_sb) is True
        assert check_client_access(agent_b, "client-100", mock_sb) is True
        assert check_client_access(admin, "client-100", mock_sb) is True


def test_unmatched_whatsapp_conversation_admin_only():
    """
    WhatsApp conversations for numbers matching no client must be admin-only.
    """
    agent = AgentIdentity("acc-a", "a@test.com", "Agent A", "agent", "sess-a", agent_id="agent-A")
    admin = AgentIdentity("admin-1", "admin@test.com", "Admin", "admin", "sess-admin", agent_id=None)

    mock_sb = MagicMock()
    # Conversation has no client_id (unmatched number)
    mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[{"id": "conv-unmatched", "client_id": None}]
    )

    # Agent cannot access unmatched conversation
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        require_conversation_access(agent, "conv-unmatched", mock_sb)
    assert exc_info.value.status_code == 403

    # Admin can access unmatched conversation
    # Should not raise
    require_conversation_access(admin, "conv-unmatched", mock_sb)
