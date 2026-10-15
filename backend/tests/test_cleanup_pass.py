import os
import sys
import unittest
import tempfile
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
from contextlib import contextmanager

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient

os.environ["PORTAL_CODE_PEPPER"] = "test_portal_pepper_secret_2026_xyz"
os.environ["PORTAL_LEGACY_LOGIN_ENABLED"] = "false"
os.environ["BFF_INTERNAL_SECRET"] = "test_bff_shared_secret_abc123"
os.environ["CALENDAR_SIGNING_SECRET"] = "test_calendar_secret_xyz_123"
os.environ["ENVIRONMENT"] = "test"

import main
import portal_auth
from portal_auth import PersistentRateLimitStore, PortalSession
import agent_auth
from agent_auth import AgentIdentity


def make_mock_query(data=None):
    mq = MagicMock()
    mq.select.return_value = mq
    mq.eq.return_value = mq
    mq.neq.return_value = mq
    mq.order.return_value = mq
    mq.limit.return_value = mq
    mq.update.return_value = mq
    mq.insert.return_value = mq

    if isinstance(data, list):
        list_data = data
        single_data = data[0] if data else {}
    elif isinstance(data, dict):
        list_data = [data]
        single_data = data
    else:
        list_data = []
        single_data = {}

    mq_single = MagicMock()
    mq_single.execute.return_value = MagicMock(data=single_data)
    mq.single.return_value = mq_single

    mq.execute.return_value = MagicMock(data=list_data)
    return mq


class TestCleanupPass(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        self.temp_db.close()
        portal_auth.rate_limit_store = PersistentRateLimitStore(db_path=self.temp_db.name)
        self.client = TestClient(main.app)

        self.agent_a_id = "agent-aaa-111"
        self.agent_b_id = "agent-bbb-222"
        self.client_a_id = "client-aaa-111"
        self.client_b_id = "client-bbb-222"
        self.quote_id = "quote-111-222"
        self.property_id = "prop-111-222"
        self.inquiry_id = "inq-111-222"

        self.token_a = "token-company-a"
        self.token_b = "token-company-b"
        self.token_legacy = "token-company-legacy"

        self.session_a = PortalSession(
            session_id="sess-a",
            client_id=self.client_a_id,
            contact_id="contact-a",
            contact_name="Alice",
            portal_role="evaluator",
            client_name="Company A Robotics",
            is_legacy=False,
        )

        self.session_b = PortalSession(
            session_id="sess-b",
            client_id=self.client_b_id,
            contact_id="contact-b",
            contact_name="Bob",
            portal_role="evaluator",
            client_name="Company B Automation",
            is_legacy=False,
        )

        self.session_legacy = PortalSession(
            session_id="sess-legacy",
            client_id=self.client_a_id,
            contact_id=None,
            contact_name="Guest",
            portal_role="legacy_readonly",
            client_name="Company A Robotics",
            is_legacy=True,
        )

        self.agent_identity_a = AgentIdentity(
            account_id="acc-a",
            agent_id=self.agent_a_id,
            email="agenta@pipeline-ev.com",
            name="Agent A",
            role="agent",
            session_id="sess-agent-a",
        )

        self.agent_identity_b = AgentIdentity(
            account_id="acc-b",
            agent_id=self.agent_b_id,
            email="agentb@pipeline-ev.com",
            name="Agent B",
            role="agent",
            session_id="sess-agent-b",
        )

        self.agent_identity_admin = AgentIdentity(
            account_id="acc-admin",
            agent_id="agent-admin-999",
            email="admin@pipeline-ev.com",
            name="Admin User",
            role="admin",
            session_id="sess-agent-admin",
        )

    def tearDown(self):
        main.app.dependency_overrides.clear()
        try:
            os.remove(self.temp_db.name)
        except OSError:
            pass

    @contextmanager
    def _mock_session(self, session):
        main.app.dependency_overrides[main.get_current_portal_session] = lambda: session
        try:
            yield
        finally:
            main.app.dependency_overrides.pop(main.get_current_portal_session, None)

    # ─────────────────────────────────────────────────────────────────────────────
    # 1d. Catalog payload_kg read & filters
    # ─────────────────────────────────────────────────────────────────────────────

    def test_catalog_reads_payload_from_specs_and_fallback(self):
        """GET /catalog reads specs->>'payload_kg' first with fallback to bedrooms."""
        mock_props = [
            {
                "id": "p-1",
                "address": "Robot Specs 1",
                "specs": {"payload_kg": 250},
                "bedrooms": 100,  # should be ignored since specs has payload_kg
                "property_type": "AMR",
                "category": "AMR",
                "lead_time_weeks": 4,
                "property_value": 50000,
                "neighborhood": "Indoor",
                "status": "AVAILABLE",
            },
            {
                "id": "p-2",
                "address": "Robot Legacy Fallback",
                "specs": {},
                "bedrooms": 150,  # should fallback to bedrooms
                "property_type": "Forklift",
                "category": "Forklift",
                "lead_time_weeks": 8,
                "property_value": 75000,
                "neighborhood": "Warehouse",
                "status": "AVAILABLE",
            },
        ]

        def router(tbl):
            if tbl == "clients":
                return make_mock_query({"id": self.client_a_id})
            if tbl == "properties":
                return make_mock_query(mock_props)
            return make_mock_query([])

        with self._mock_session(self.session_a), \
             patch("main.supabase.table", side_effect=router):
            headers = {"Authorization": f"Bearer {self.token_a}"}

            # 1. Base query without filters
            res = self.client.get(f"/api/portal/{self.client_a_id}/catalog", headers=headers)
            self.assertEqual(res.status_code, 200)
            units = res.json()["units"]
            self.assertEqual(len(units), 2)
            self.assertEqual(units[0]["specs"]["payload_kg"], 250)
            self.assertEqual(units[1]["payload_tier"], 150)

            # 2. Filter min_payload_kg = 200 (should return only p-1)
            res_min = self.client.get(f"/api/portal/{self.client_a_id}/catalog?min_payload_kg=200", headers=headers)
            self.assertEqual(res_min.status_code, 200)
            self.assertEqual(len(res_min.json()["units"]), 1)
            self.assertEqual(res_min.json()["units"][0]["property_id"], "p-1")

            # 3. Filter category = AMR (should return only p-1)
            res_cat = self.client.get(f"/api/portal/{self.client_a_id}/catalog?category=AMR", headers=headers)
            self.assertEqual(res_cat.status_code, 200)
            self.assertEqual(len(res_cat.json()["units"]), 1)
            self.assertEqual(res_cat.json()["units"][0]["property_id"], "p-1")

            # 4. Filter max_lead_time_weeks = 5 (should return only p-1)
            res_lead = self.client.get(f"/api/portal/{self.client_a_id}/catalog?max_lead_time_weeks=5", headers=headers)
            self.assertEqual(res_lead.status_code, 200)
            self.assertEqual(len(res_lead.json()["units"]), 1)
            self.assertEqual(res_lead.json()["units"][0]["property_id"], "p-1")

    # ─────────────────────────────────────────────────────────────────────────────
    # 2. Rep Quote Routes & Scoping
    # ─────────────────────────────────────────────────────────────────────────────

    def test_agent_b_cannot_list_or_send_quotes_for_agent_a(self):
        """Agent B gets 404 when attempting to list or send quotes for Agent A's client."""
        def mock_supabase_table(tbl):
            if tbl == "clients":
                return make_mock_query({"id": self.client_a_id, "assigned_agent_id": self.agent_a_id})
            return make_mock_query([])

        with patch("main.get_current_agent", return_value=self.agent_identity_b), \
             patch("agent_auth.get_current_agent", return_value=self.agent_identity_b), \
             patch("main.supabase.table", side_effect=mock_supabase_table):

            # Agent B attempts GET quotes for Agent A's client -> 404
            res_get = self.client.get(f"/api/console/clients/{self.client_a_id}/quotes")
            self.assertEqual(res_get.status_code, 404)

            # Agent B attempts POST send quote for Agent A's client -> 404
            res_post = self.client.post(
                f"/api/console/clients/{self.client_a_id}/quotes/{self.quote_id}/send",
                json={"quoted_amount": 10000, "currency": "MYR"},
            )
            self.assertEqual(res_post.status_code, 404)

    def test_rep_cannot_send_quote_on_accepted_or_declined(self):
        """Rep cannot send quote if it is already accepted or declined (returns 409)."""
        def mock_supabase_table(tbl):
            if tbl == "clients":
                return make_mock_query({"id": self.client_a_id, "assigned_agent_id": self.agent_a_id})
            elif tbl == "portal_quotes":
                return make_mock_query({"id": self.quote_id, "client_id": self.client_a_id, "status": "accepted"})
            return make_mock_query([])

        with patch("main.get_current_agent", return_value=self.agent_identity_a), \
             patch("agent_auth.get_current_agent", return_value=self.agent_identity_a), \
             patch("main.supabase.table", side_effect=mock_supabase_table):

            res = self.client.post(
                f"/api/console/clients/{self.client_a_id}/quotes/{self.quote_id}/send",
                json={"quoted_amount": 15000, "currency": "MYR"},
            )
            self.assertEqual(res.status_code, 409)

    def test_rep_send_stores_internal_notes_portal_get_never_returns_it(self):
        """Rep send stores internal_notes; portal GET never includes internal_notes."""
        stored_updates = []

        def mock_supabase_table(tbl):
            if tbl == "clients":
                return make_mock_query({"id": self.client_a_id, "assigned_agent_id": self.agent_a_id, "name": "Client A"})
            elif tbl == "portal_quotes":
                mq = make_mock_query({"id": self.quote_id, "client_id": self.client_a_id, "status": "requested", "property_id": self.property_id})
                def cap_update(payload):
                    stored_updates.append(payload)
                    return mq
                mq.update.side_effect = cap_update
                return mq
            elif tbl == "signals":
                return make_mock_query({"id": "sig-1"})
            return make_mock_query([])

        with patch("main.get_current_agent", return_value=self.agent_identity_a), \
             patch("agent_auth.get_current_agent", return_value=self.agent_identity_a), \
             patch("main.supabase.table", side_effect=mock_supabase_table):

            res = self.client.post(
                f"/api/console/clients/{self.client_a_id}/quotes/{self.quote_id}/send",
                json={
                    "quoted_amount": 25000,
                    "currency": "MYR",
                    "customer_note": "Customer visible note",
                    "internal_notes": "CONFIDENTIAL REP MARGIN NOTE",
                },
            )
            self.assertEqual(res.status_code, 200)
            self.assertTrue(len(stored_updates) > 0)
            self.assertEqual(stored_updates[0]["internal_notes"], "CONFIDENTIAL REP MARGIN NOTE")

        # Now test Portal GET for the same quote: internal_notes MUST NOT leak
        def mock_portal_get_quotes(tbl):
            if tbl == "portal_quotes":
                return make_mock_query([{
                    "id": self.quote_id,
                    "property_id": self.property_id,
                    "quantity": 1,
                    "notes": "Need quotation",
                    "status": "sent",
                    "requested_at": "2026-10-15T10:00:00Z",
                    "responded_at": None,
                    "quoted_amount": 25000,
                    "currency": "MYR",
                    "customer_note": "Customer visible note",
                    "internal_notes": "CONFIDENTIAL REP MARGIN NOTE",
                    "valid_until": "2026-11-15",
                    "properties": {"address": "Ottobot Unit"},
                }])
            return make_mock_query([])

        with self._mock_session(self.session_a), \
             patch("main.supabase.table", side_effect=mock_portal_get_quotes):
            p_res = self.client.get(
                f"/api/portal/{self.client_a_id}/quotes",
                headers={"Authorization": f"Bearer {self.token_a}"},
            )
            self.assertEqual(p_res.status_code, 200)
            data = p_res.json()["quotes"][0]
            self.assertNotIn("internal_notes", data)
            self.assertNotIn("rep_notes", data)
            self.assertEqual(data["customer_note"], "Customer visible note")

    def test_portal_quote_request_creates_signal_for_assigned_agent(self):
        """A new portal quote request creates a signal for the client's assigned agent."""
        inserted_signals = []

        def mock_supabase_table(tbl):
            if tbl == "properties":
                return make_mock_query({"id": self.property_id, "address": "Unit A"})
            elif tbl == "clients":
                return make_mock_query({"id": self.client_a_id, "name": "Company A", "assigned_agent_id": self.agent_a_id})
            elif tbl == "portal_quotes":
                # For duplicate check: return empty list
                mq = make_mock_query([])
                return mq
            elif tbl == "signals":
                mq = make_mock_query([])
                def cap_signal(payload):
                    inserted_signals.append(payload)
                    return mq
                mq.insert.side_effect = cap_signal
                return mq
            return make_mock_query([])

        with self._mock_session(self.session_a), \
             patch("main.supabase.table", side_effect=mock_supabase_table):
            res = self.client.post(
                f"/api/portal/{self.client_a_id}/quotes",
                headers={"Authorization": f"Bearer {self.token_a}"},
                json={"property_id": self.property_id, "quantity": 2, "notes": "Urgent quotation needed"},
            )
            self.assertEqual(res.status_code, 200)
            self.assertTrue(len(inserted_signals) > 0)
            sig = inserted_signals[0]
            self.assertEqual(sig["client_id"], self.client_a_id)
            self.assertEqual(sig["type"], "portal_quote_requested")

    # ─────────────────────────────────────────────────────────────────────────────
    # 3. Missing Security & Gating Tests
    # ─────────────────────────────────────────────────────────────────────────────

    def test_legacy_readonly_session_returns_403_on_all_mutation_endpoints(self):
        """Legacy readonly session is rejected (403) on: feedback PUT, quote POST, quote respond POST, inquiry POST, message POST, preferences PUT."""
        with self._mock_session(self.session_legacy):
            headers = {"Authorization": f"Bearer {self.token_legacy}"}

            # 1. Feedback PUT
            r1 = self.client.put(
                f"/api/portal/{self.client_a_id}/catalog/{self.property_id}/feedback",
                headers=headers,
                json={"interest": "interested"},
            )
            self.assertEqual(r1.status_code, 403)

            # 2. Quote POST
            r2 = self.client.post(
                f"/api/portal/{self.client_a_id}/quotes",
                headers=headers,
                json={"property_id": self.property_id, "quantity": 1},
            )
            self.assertEqual(r2.status_code, 403)

            # 3. Quote respond POST
            r3 = self.client.post(
                f"/api/portal/{self.client_a_id}/quotes/{self.quote_id}/respond",
                headers=headers,
                json={"response": "accepted"},
            )
            self.assertEqual(r3.status_code, 403)

            # 4. Inquiry POST
            r4 = self.client.post(
                f"/api/portal/{self.client_a_id}/inquiry",
                headers=headers,
                json={"property_id": self.property_id, "message": "Inquiry text"},
            )
            self.assertEqual(r4.status_code, 403)

            # 5. Message POST
            r5 = self.client.post(
                f"/api/portal/{self.client_a_id}/inquiries/{self.inquiry_id}/messages",
                headers=headers,
                json={"body": "Thread reply"},
            )
            self.assertEqual(r5.status_code, 403)

            # 6. Preferences PUT
            r6 = self.client.put(
                f"/api/portal/{self.client_a_id}/preferences",
                headers=headers,
                json={"industry": "Logistics"},
            )
            self.assertEqual(r6.status_code, 403)

    def test_write_rate_limiter_429_on_quotes_and_feedback(self):
        """21st write within 5 minutes returns 429 on quotes POST and feedback PUT."""
        def router(tbl):
            if tbl == "properties":
                return make_mock_query({"id": self.property_id, "address": "Unit A"})
            if tbl == "clients":
                return make_mock_query({"id": self.client_a_id, "name": "Company A"})
            return make_mock_query([])

        with self._mock_session(self.session_a), \
             patch("main.supabase.table", side_effect=router):
            headers = {"Authorization": f"Bearer {self.token_a}"}

            # 20 writes pass on feedback
            for _ in range(20):
                res = self.client.put(
                    f"/api/portal/{self.client_a_id}/catalog/{self.property_id}/feedback",
                    headers=headers,
                    json={"is_saved": True},
                )
                self.assertEqual(res.status_code, 200)

            # 21st write on feedback returns 429
            res_fb = self.client.put(
                f"/api/portal/{self.client_a_id}/catalog/{self.property_id}/feedback",
                headers=headers,
                json={"is_saved": True},
            )
            self.assertEqual(res_fb.status_code, 429)

            # 20 writes on quotes pass
            for _ in range(20):
                res = self.client.post(
                    f"/api/portal/{self.client_a_id}/quotes",
                    headers=headers,
                    json={"property_id": self.property_id, "quantity": 1},
                )
                self.assertEqual(res.status_code, 200)

            # 21st write on quotes returns 429
            res_q = self.client.post(
                f"/api/portal/{self.client_a_id}/quotes",
                headers=headers,
                json={"property_id": self.property_id, "quantity": 1},
            )
            self.assertEqual(res_q.status_code, 429)

    def test_cross_company_isolation_feedback_quotes_inquiries_messages(self):
        """Company A cannot read or write Company B's feedback, quotes, inquiries, or messages."""
        with self._mock_session(self.session_a):
            headers = {"Authorization": f"Bearer {self.token_a}"}

            # Feedback
            r1 = self.client.put(
                f"/api/portal/{self.client_b_id}/catalog/{self.property_id}/feedback",
                headers=headers,
                json={"interest": "interested"},
            )
            self.assertEqual(r1.status_code, 403)

            # Quotes GET & POST
            r2 = self.client.get(f"/api/portal/{self.client_b_id}/quotes", headers=headers)
            self.assertEqual(r2.status_code, 403)
            r3 = self.client.post(f"/api/portal/{self.client_b_id}/quotes", headers=headers, json={"property_id": self.property_id})
            self.assertEqual(r3.status_code, 403)

            # Inquiries GET & POST
            r4 = self.client.get(f"/api/portal/{self.client_b_id}/inquiries", headers=headers)
            self.assertEqual(r4.status_code, 403)
            r5 = self.client.post(f"/api/portal/{self.client_b_id}/inquiry", headers=headers, json={"message": "Inquiry"})
            self.assertEqual(r5.status_code, 403)
            r6 = self.client.post(f"/api/portal/{self.client_b_id}/inquiries/{self.inquiry_id}/messages", headers=headers, json={"body": "Msg"})
            self.assertEqual(r6.status_code, 403)

    def test_profile_update_writes_audit_row_only_for_changed_fields(self):
        """Profile update writes one audit row per CHANGED field and none for unchanged ones."""
        audit_inserts = []

        def mock_supabase_table(tbl):
            if tbl == "clients":
                return make_mock_query({
                    "id": self.client_a_id,
                    "industry": "Automotive",
                    "facility_type": "Plant",
                    "facility_size_sqm": 5000,
                    "use_case": "Pallet transport",
                    "purchase_timeline": "3_months",
                    "existing_automation": "None",
                })
            elif tbl == "portal_profile_audit":
                mq = make_mock_query([])
                def cap_audit(payload):
                    audit_inserts.append(payload)
                    return mq
                mq.insert.side_effect = cap_audit
                return mq
            return make_mock_query([])

        with self._mock_session(self.session_a), \
             patch("main.supabase.table", side_effect=mock_supabase_table):
            headers = {"Authorization": f"Bearer {self.token_a}"}

            # Update: industry is CHANGED (Automotive -> Electronics)
            # facility_type is UNCHANGED (Plant -> Plant)
            # facility_size_sqm is CHANGED (5000 -> 10000)
            res = self.client.put(
                f"/api/portal/{self.client_a_id}/preferences",
                headers=headers,
                json={
                    "industry": "Electronics",
                    "facility_type": "Plant",
                    "facility_size_sqm": 10000,
                },
            )
            self.assertEqual(res.status_code, 200)

            # Exactly two audit rows should be recorded (industry, facility_size_sqm), NOT facility_type!
            audit_fields = [entry["field"] for entry in audit_inserts]
            self.assertEqual(len(audit_inserts), 2)
            self.assertIn("industry", audit_fields)
            self.assertIn("facility_size_sqm", audit_fields)
            self.assertNotIn("facility_type", audit_fields)

    # ─────────────────────────────────────────────────────────────────────────────
    # Rep Reply -> inquiry_messages unread lifecycle test
    # ─────────────────────────────────────────────────────────────────────────────

    def test_rep_reply_inquiry_messages_unread_lifecycle(self):
        """
        Rep reply writes sender='rep' row into inquiry_messages ->
        Portal GET /inquiries returns unread_count=1 ->
        Portal POST /read marks read ->
        Portal GET /inquiries returns unread_count=0.
        """
        stored_messages = [
            {
                "id": "msg-orig-1",
                "inquiry_id": self.inquiry_id,
                "client_id": self.client_a_id,
                "sender": "company",
                "body": "Can you provide AMR specs?",
                "read_at": None,
                "created_at": "2026-10-15T10:00:00Z",
            }
        ]

        def mock_supabase_table(tbl):
            if tbl == "clients":
                return make_mock_query({"id": self.client_a_id, "assigned_agent_id": self.agent_a_id})
            elif tbl == "client_inquiries":
                return make_mock_query([{
                    "id": self.inquiry_id,
                    "client_id": self.client_a_id,
                    "property_id": self.property_id,
                    "message": "Can you provide AMR specs?",
                    "status": "open",
                    "agent_reply": None,
                    "created_at": "2026-10-15T10:00:00Z",
                    "properties": {"address": "AMR-500 Unit"},
                }])
            elif tbl == "inquiry_messages":
                mq = make_mock_query(stored_messages)

                def cap_insert(payload):
                    row = {
                        "id": f"msg-rep-{len(stored_messages) + 1}",
                        "inquiry_id": payload.get("inquiry_id"),
                        "client_id": payload.get("client_id"),
                        "sender": payload.get("sender"),
                        "body": payload.get("body"),
                        "read_at": None,
                        "created_at": "2026-10-15T11:00:00Z",
                    }
                    stored_messages.append(row)
                    mq_res = MagicMock()
                    mq_res.execute.return_value = MagicMock(data=[row])
                    return mq_res

                def cap_update(payload):
                    if "read_at" in payload:
                        for m in stored_messages:
                            if m.get("sender") == "rep":
                                m["read_at"] = payload["read_at"]
                    mq_up = MagicMock()
                    mq_up.eq.return_value = mq_up
                    mq_up.is_.return_value = mq_up
                    mq_up.execute.return_value = MagicMock(data=stored_messages)
                    return mq_up

                mq.insert.side_effect = cap_insert
                mq.update.side_effect = cap_update
                return mq
            return make_mock_query([])

        with patch("main.get_current_agent", return_value=self.agent_identity_a), \
             patch("agent_auth.get_current_agent", return_value=self.agent_identity_a), \
             patch("main.supabase.table", side_effect=mock_supabase_table):

            # 1. Rep replies to the client inquiry
            rep_res = self.client.post(
                f"/api/console/clients/{self.client_a_id}/inquiries/{self.inquiry_id}/reply",
                json={"reply": "Here is the full AMR spec sheet."},
            )
            self.assertEqual(rep_res.status_code, 200)
            self.assertTrue(rep_res.json()["success"])

            # Verify that sender='rep' row was recorded
            rep_msgs = [m for m in stored_messages if m["sender"] == "rep"]
            self.assertEqual(len(rep_msgs), 1)
            self.assertEqual(rep_msgs[0]["body"], "Here is the full AMR spec sheet.")
            self.assertIsNone(rep_msgs[0]["read_at"])

        with self._mock_session(self.session_a), \
             patch("main.supabase.table", side_effect=mock_supabase_table):

            # 2. Portal fetches inquiries -> unread_count should be 1
            headers = {"Authorization": f"Bearer {self.token_a}"}
            get_inq = self.client.get(f"/api/portal/{self.client_a_id}/inquiries", headers=headers)
            self.assertEqual(get_inq.status_code, 200)
            inquiries = get_inq.json()["inquiries"]
            self.assertEqual(len(inquiries), 1)
            self.assertEqual(inquiries[0]["unread_count"], 1)

            # 3. Portal marks inquiry as read
            mark_read = self.client.post(
                f"/api/portal/{self.client_a_id}/inquiries/{self.inquiry_id}/read",
                headers=headers,
            )
            self.assertEqual(mark_read.status_code, 200)
            self.assertTrue(mark_read.json()["success"])

            # 4. Portal fetches inquiries again -> unread_count should be 0
            get_inq_after = self.client.get(f"/api/portal/{self.client_a_id}/inquiries", headers=headers)
            self.assertEqual(get_inq_after.status_code, 200)
            inquiries_after = get_inq_after.json()["inquiries"]
            self.assertEqual(len(inquiries_after), 1)
            self.assertEqual(inquiries_after[0]["unread_count"], 0)

    # ─────────────────────────────────────────────────────────────────────────────
    # Console quotes pending & profile audit policy tests
    # ─────────────────────────────────────────────────────────────────────────────

    def test_rep_pending_quotes_and_profile_audit_endpoints(self):
        """
        GET /api/console/quotes/pending:
          - Rep sees only quotes for their assigned clients.
          - Admin sees all pending quotes.
        GET /api/console/clients/{id}/portal/profile-audit:
          - Assigned rep gets 200 and audit rows.
          - Unassigned rep gets 404 (client scoping).
        """
        all_pending_quotes = [
            {
                "id": "q-1",
                "client_id": self.client_a_id,
                "property_id": self.property_id,
                "quantity": 2,
                "notes": "Fast delivery requested",
                "status": "requested",
                "requested_at": "2026-10-15T09:00:00Z",
                "clients": {"id": self.client_a_id, "name": "Company A", "assigned_agent_id": self.agent_a_id},
                "properties": {"address": "AMR-500"},
            },
            {
                "id": "q-2",
                "client_id": self.client_b_id,
                "property_id": "prop-bbb-999",
                "quantity": 1,
                "notes": "Standard",
                "status": "requested",
                "requested_at": "2026-10-15T09:30:00Z",
                "clients": {"id": self.client_b_id, "name": "Company B", "assigned_agent_id": self.agent_b_id},
                "properties": {"address": "Forklift Unit"},
            },
        ]

        def mock_supabase_table(tbl):
            if tbl == "clients":
                return make_mock_query({"id": self.client_a_id, "assigned_agent_id": self.agent_a_id})
            elif tbl == "portal_quotes":
                return make_mock_query(all_pending_quotes)
            elif tbl == "portal_profile_audit":
                return make_mock_query([
                    {
                        "id": "aud-1",
                        "field": "industry",
                        "old_value": "Automotive",
                        "new_value": "Electronics",
                        "changed_at": "2026-10-15T12:00:00Z",
                        "contact_id": "contact-a",
                        "portal_contacts": {"name": "Alice", "email": "alice@companya.com"},
                    }
                ])
            return make_mock_query([])

        # 1. Rep A calls pending quotes: should only receive Quote 1
        with patch("main.get_current_agent", return_value=self.agent_identity_a), \
             patch("agent_auth.get_current_agent", return_value=self.agent_identity_a), \
             patch("main.supabase.table", side_effect=mock_supabase_table):

            res_a = self.client.get("/api/console/quotes/pending")
            self.assertEqual(res_a.status_code, 200)
            quotes_a = res_a.json()["quotes"]
            self.assertEqual(len(quotes_a), 1)
            self.assertEqual(quotes_a[0]["id"], "q-1")

        # 2. Admin calls pending quotes: should receive both Quote 1 and Quote 2
        with patch("main.get_current_agent", return_value=self.agent_identity_admin), \
             patch("agent_auth.get_current_agent", return_value=self.agent_identity_admin), \
             patch("main.supabase.table", side_effect=mock_supabase_table):

            res_admin = self.client.get("/api/console/quotes/pending")
            self.assertEqual(res_admin.status_code, 200)
            quotes_admin = res_admin.json()["quotes"]
            self.assertEqual(len(quotes_admin), 2)

        # 3. Rep A calls profile-audit for assigned client_a -> 200
        with patch("main.get_current_agent", return_value=self.agent_identity_a), \
             patch("agent_auth.get_current_agent", return_value=self.agent_identity_a), \
             patch("main.supabase.table", side_effect=mock_supabase_table):

            res_audit_a = self.client.get(f"/api/console/clients/{self.client_a_id}/portal/profile-audit")
            self.assertEqual(res_audit_a.status_code, 200)
            self.assertEqual(len(res_audit_a.json()["audit_log"]), 1)
            self.assertEqual(res_audit_a.json()["audit_log"][0]["field"], "industry")

        # 4. Rep B calls profile-audit for client_a -> 404 (client scoping enforced)
        with patch("main.get_current_agent", return_value=self.agent_identity_b), \
             patch("agent_auth.get_current_agent", return_value=self.agent_identity_b), \
             patch("main.supabase.table", side_effect=mock_supabase_table):

            res_audit_b = self.client.get(f"/api/console/clients/{self.client_a_id}/portal/profile-audit")
            self.assertEqual(res_audit_b.status_code, 404)

    # ─────────────────────────────────────────────────────────────────────────────
    # Console BFF route path traversal validation
    # ─────────────────────────────────────────────────────────────────────────────

    def test_console_route_path_traversal_validation(self):
        """
        Verify validation rules enforced in app/api/console/[...path]/route.ts:
        - Segments containing '..', '%2e', '%2f', '\\' are rejected (400)
        - Empty segments are rejected (400)
        - Disallowed methods are rejected (405)
        """
        allowed_methods = {"GET", "POST", "PUT", "PATCH", "DELETE"}

        def validate_path(method: str, raw_segments: list[str], raw_url: str = "") -> int:
            if method not in allowed_methods:
                return 405
            if not raw_segments:
                return 400
            for seg in raw_segments:
                if not seg or seg.strip() == "":
                    return 400
                lower = seg.lower()
                if (
                    ".." in seg
                    or "\\" in seg
                    or "%2e" in lower
                    or "%2f" in lower
                    or "%5c" in lower
                ):
                    return 400
            if ".." in raw_url or "%2e%2e" in raw_url.lower():
                return 400
            return 200

        # Valid paths
        self.assertEqual(validate_path("GET", ["quotes", "pending"]), 200)
        self.assertEqual(validate_path("POST", ["clients", "c-1", "quotes", "q-1", "send"]), 200)

        # Path traversal tests ("../admin" style)
        self.assertEqual(validate_path("GET", ["..", "admin"]), 400)
        self.assertEqual(validate_path("GET", ["quotes", "..", "admin"]), 400)
        self.assertEqual(validate_path("GET", ["%2e%2e", "admin"]), 400)
        self.assertEqual(validate_path("GET", ["quotes%2f..%2fadmin"]), 400)
        self.assertEqual(validate_path("GET", ["foo\\bar"]), 400)
        self.assertEqual(validate_path("GET", [""]), 400)
        self.assertEqual(validate_path("GET", ["   "]), 400)
        self.assertEqual(validate_path("GET", ["quotes"], raw_url="http://localhost:3000/api/console/../admin"), 400)

        # Method validation
        self.assertEqual(validate_path("OPTIONS", ["quotes"]), 405)
        self.assertEqual(validate_path("TRACE", ["quotes"]), 405)


if __name__ == "__main__":
    unittest.main()
