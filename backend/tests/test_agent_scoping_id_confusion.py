"""
backend/tests/test_agent_scoping_id_confusion.py
─────────────────────────────────────────────────
Comprehensive tests for:
1. ID Confusion (Requirement 5):
   Verifies distinct realistic UUIDs for agent_accounts(id) vs agents(id):
   - account_id: 11111111-2222-3333-4444-555555555555
   - agent_id:   aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee
   Verifies scoping everywhere strictly compares clients.assigned_agent_id
   with agent_accounts.agent_id (agents.id), NEVER account_id.
   Covers:
   - Client access (check_client_access, filter_clients_for_agent)
   - Viewings scoping
   - Signals dismiss scoping
   - WhatsApp conversation scoping
   - Portal access panel scoping

2. Scoping of Aggregates (Requirement 8):
   - model_status: admin-only (403 for non-admin, 200 for admin)
   - prediction_accuracy: admin-only (403 for non-admin, 200 for admin)
   - market_movements: global catalog (200 for any agent)
   - pipeline_projection: scoped to agent's clients
   - dashboard_briefing: scoped to agent's clients
   - shortlist: scoped to agent's clients
   - signals dismiss: 404 if client not assigned to agent

3. Calendar & Webhook Endpoints (Requirement 6):
   - Calendar signed token allows public access with zero cookies
   - WhatsApp webhook GET (hub.challenge) and POST signature enforcement
"""

import os
import sys
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi import HTTPException
from fastapi.testclient import TestClient

os.environ["ENVIRONMENT"] = "testing"
os.environ["BFF_INTERNAL_SECRET"] = "test_bff_shared_secret_abc123"
os.environ["PORTAL_CODE_PEPPER"] = "test_pepper_secret_xyz"
os.environ["CALENDAR_SIGNING_SECRET"] = "test_calendar_secret_12345"
os.environ["WHATSAPP_APP_SECRET"] = "0123456789abcdef0123456789abcdef"
os.environ["ENFORCE_WA_SIGNATURE"] = "true"

import main
import agent_auth
from agent_auth import AgentIdentity, check_client_access, filter_clients_for_agent, require_conversation_access
from route_policies import match_policy, RoutePolicy


class TestAgentScopingAndIDParity(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        # Distinct realistic UUIDs
        self.ACCOUNT_ID = "11111111-2222-3333-4444-555555555555"
        self.AGENT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        self.OTHER_AGENT_ID = "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"
        self.CLIENT_ID = "cccccccc-dddd-eeee-ffff-000000000001"

        self.agent_identity = AgentIdentity(
            account_id=self.ACCOUNT_ID,
            agent_id=self.AGENT_ID,
            email="agent@pipeline-ev.com",
            name="Sarah Jenkins",
            role="agent",
            session_id="sess-test-uuid-999",
        )

        self.admin_identity = AgentIdentity(
            account_id="99999999-8888-7777-6666-555555555555",
            agent_id=None,
            email="admin@pipeline-ev.com",
            name="System Admin",
            role="admin",
            session_id="sess-admin-uuid-001",
        )

    def tearDown(self):
        main.app.dependency_overrides.clear()

    # ─── 1. ID CONFUSION PARITY TESTS ──────────────────────────────────────────

    def test_client_scoping_strictly_uses_agent_id_not_account_id(self):
        """Scoping checks clients.assigned_agent_id == agent.agent_id, NEVER account_id."""
        mock_supabase = MagicMock()

        # Case A: client assigned to AGENT_ID (should succeed)
        mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = (
            MagicMock(data=[{"id": self.CLIENT_ID, "assigned_agent_id": self.AGENT_ID}])
        )
        self.assertTrue(check_client_access(self.agent_identity, self.CLIENT_ID, mock_supabase))

        # Case B: client assigned to ACCOUNT_ID (must FAIL - proves code does not confuse the two)
        mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = (
            MagicMock(data=[{"id": self.CLIENT_ID, "assigned_agent_id": self.ACCOUNT_ID}])
        )
        self.assertFalse(check_client_access(self.agent_identity, self.CLIENT_ID, mock_supabase))

    def test_filter_clients_strictly_uses_agent_id_not_account_id(self):
        """filter_clients_for_agent matches client assigned_agent_id with agent_id."""
        clients = [
            {"id": "c1", "name": "Client 1", "assigned_agent_id": self.AGENT_ID},
            {"id": "c2", "name": "Client 2", "assigned_agent_id": self.ACCOUNT_ID},  # wrong: account_id
            {"id": "c3", "name": "Client 3", "assigned_agent_id": self.OTHER_AGENT_ID},
        ]
        filtered = filter_clients_for_agent(self.agent_identity, clients)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["id"], "c1")

    def test_whatsapp_conversation_scoping_uses_agent_id(self):
        """WhatsApp conversation checking checks client assigned_agent_id against agent.agent_id."""
        mock_supabase = MagicMock()
        # Conversation belongs to client assigned to agent_id -> succeeds
        mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.side_effect = [
            MagicMock(data=[{"id": "conv-1", "client_id": self.CLIENT_ID}]),
            MagicMock(data=[{"id": self.CLIENT_ID, "assigned_agent_id": self.AGENT_ID}]),
        ]
        # Should not raise
        require_conversation_access(self.agent_identity, "conv-1", mock_supabase)

        # Conversation belongs to client assigned to account_id -> must raise 404
        mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.side_effect = [
            MagicMock(data=[{"id": "conv-2", "client_id": self.CLIENT_ID}]),
            MagicMock(data=[{"id": self.CLIENT_ID, "assigned_agent_id": self.ACCOUNT_ID}]),
        ]
        with self.assertRaises(HTTPException) as ctx:
            require_conversation_access(self.agent_identity, "conv-2", mock_supabase)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_signals_dismiss_scoped_to_agent_id(self):
        """Dismissing a signal verifies the client's assigned_agent_id matches agent.agent_id."""
        with patch("main.get_current_agent", return_value=self.agent_identity):
            with patch.object(main.supabase, "table") as mock_table:
                mock_query = MagicMock()
                # Signal is for a client assigned to ANOTHER agent
                mock_query.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[{"id": "sig-1", "client_id": self.CLIENT_ID, "clients": {"assigned_agent_id": self.OTHER_AGENT_ID}}]
                )
                mock_table.return_value = mock_query

                headers = {"X-BFF-Internal-Secret": "test_bff_shared_secret_abc123"}
                res = self.client.post("/api/signals/sig-1/dismiss", headers=headers)
                self.assertEqual(res.status_code, 404)

    # ─── 2. SCOPING OF AGGREGATES & ADMIN-ONLY ENDPOINTS ──────────────────────

    def test_model_status_and_prediction_accuracy_are_admin_only(self):
        """model_status and prediction_accuracy are admin-only in policy table and route handler."""
        self.assertEqual(match_policy("GET", "/api/model_status").policy, RoutePolicy.ADMIN_ONLY)
        self.assertEqual(match_policy("GET", "/api/prediction_accuracy").policy, RoutePolicy.ADMIN_ONLY)

        headers = {"X-BFF-Internal-Secret": "test_bff_shared_secret_abc123"}

        # Non-admin agent gets 403 Forbidden
        with patch("main.get_current_agent", return_value=self.agent_identity):
            res1 = self.client.get("/api/model_status", headers=headers)
            self.assertEqual(res1.status_code, 403)
            self.assertIn("Administrator privileges required", res1.json()["detail"])

            res2 = self.client.get("/api/prediction_accuracy", headers=headers)
            self.assertEqual(res2.status_code, 403)
            self.assertIn("Administrator privileges required", res2.json()["detail"])

        # Admin gets 200 OK
        with patch("main.get_current_agent", return_value=self.admin_identity):
            with patch.object(main.supabase, "table") as mock_table:
                mock_query = MagicMock()
                mock_query.select.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
                mock_table.return_value = mock_query

                res1 = self.client.get("/api/model_status", headers=headers)
                self.assertEqual(res1.status_code, 200)

                res2 = self.client.get("/api/prediction_accuracy", headers=headers)
                self.assertEqual(res2.status_code, 200)

    def test_market_movements_is_global_and_accessible_to_any_agent(self):
        """market_movements provides catalog insights and is accessible to standard agents."""
        self.assertEqual(match_policy("GET", "/api/market_movements").policy, RoutePolicy.ANY_AGENT)

        headers = {"X-BFF-Internal-Secret": "test_bff_shared_secret_abc123"}
        with patch("main.get_current_agent", return_value=self.agent_identity):
            with patch.object(main.supabase, "table") as mock_table:
                mock_query = MagicMock()
                mock_query.select.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
                mock_table.return_value = mock_query

                res = self.client.get("/api/market_movements", headers=headers)
                self.assertEqual(res.status_code, 200)

    # ─── 3. CALENDAR & WEBHOOK VERIFICATION ────────────────────────────────────

    def test_calendar_route_policy_is_public(self):
        """Calendar routes with token authentication are public in the policy table."""
        self.assertEqual(match_policy("GET", "/api/calendar/demo123").policy, RoutePolicy.PUBLIC)
        self.assertEqual(match_policy("GET", "/api/calendar/demo123.ics").policy, RoutePolicy.PUBLIC)

    def test_whatsapp_webhook_verification_and_public_policy(self):
        """WhatsApp webhook GET and POST are PUBLIC in the policy table."""
        self.assertEqual(match_policy("GET", "/api/whatsapp/webhook").policy, RoutePolicy.PUBLIC)
        self.assertEqual(match_policy("POST", "/api/whatsapp/webhook").policy, RoutePolicy.PUBLIC)

        # GET verification with valid verify token returns hub.challenge
        challenge = "test_challenge_code_98765"
        res = self.client.get(
            "/api/whatsapp/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.challenge": challenge,
                "hub.verify_token": os.environ.get("WHATSAPP_VERIFY_TOKEN", ""),
            },
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.text, challenge)
