import os
import sys
import unittest
import tempfile
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient

os.environ["PORTAL_CODE_PEPPER"] = "test_portal_pepper_secret_2026_xyz"
os.environ["PORTAL_LEGACY_LOGIN_ENABLED"] = "false"
os.environ["BFF_INTERNAL_SECRET"] = "test_bff_shared_secret_abc123"
os.environ["CALENDAR_SIGNING_SECRET"] = "test_calendar_secret_xyz_123"
os.environ["ENVIRONMENT"] = "test"

import main
import portal_auth
from portal_auth import PersistentRateLimitStore
from main import can_quote_transition

FORBIDDEN_PORTAL_KEYS = {"indicative_price_myr", "indicative_price_note"}

FORBIDDEN_KEYS = {
    "expected_value",
    "buy_probability",
    "adoption_probability",
    "ml_probability",
    "tier",
    "score",
    "internal_notes",
    "agent_notes",
    "rep_notes",
    "cost_price",
    "margin",
    "indicative_price_myr",
    "indicative_price_note",
}


def find_forbidden_keys(obj, path="$"):
    hits = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in FORBIDDEN_PORTAL_KEYS:
                hits.append(f"{path}.{k}")
            hits += find_forbidden_keys(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            hits += find_forbidden_keys(v, f"{path}[{i}]")
    return hits


def assert_no_forbidden(obj, path=""):
    """Recursively assert that none of FORBIDDEN_KEYS appear as dictionary keys."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            current_path = f"{path}.{k}" if path else k
            assert (
                k not in FORBIDDEN_KEYS
            ), f"Leaked forbidden key '{k}' found at path '{current_path}'"
            assert_no_forbidden(v, current_path)
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            assert_no_forbidden(item, f"{path}[{idx}]")


class TestPortalNoLeaksAndSecurity(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        self.temp_db.close()
        portal_auth.rate_limit_store = PersistentRateLimitStore(db_path=self.temp_db.name)
        self.client = TestClient(main.app)

        self.company_a = "11111111-1111-1111-1111-111111111111"
        self.company_b = "22222222-2222-2222-2222-222222222222"
        self.property_id = "33333333-3333-3333-3333-333333333333"
        self.quote_id = "44444444-4444-4444-4444-444444444444"

        self.token_a = "token_for_company_a_32_bytes_long"
        self.token_b = "token_for_company_b_32_bytes_long"
        self.token_legacy = "token_legacy_readonly_32_bytes_len"

        now = datetime.now(timezone.utc)
        self.session_a = {
            "id": "sess-a",
            "client_id": self.company_a,
            "contact_id": "contact-a",
            "portal_role": "evaluator",
            "idle_expires_at": (now + timedelta(hours=2)).isoformat(),
            "absolute_expires_at": (now + timedelta(days=7)).isoformat(),
            "revoked_at": None,
            "clients": {"id": self.company_a, "name": "Company A Robotics"},
            "portal_contacts": {"id": "contact-a", "name": "Alice", "status": "active", "locked_until": None},
        }

        self.session_b = {
            "id": "sess-b",
            "client_id": self.company_b,
            "contact_id": "contact-b",
            "portal_role": "evaluator",
            "idle_expires_at": (now + timedelta(hours=2)).isoformat(),
            "absolute_expires_at": (now + timedelta(days=7)).isoformat(),
            "revoked_at": None,
            "clients": {"id": self.company_b, "name": "Company B Automation"},
            "portal_contacts": {"id": "contact-b", "name": "Bob", "status": "active", "locked_until": None},
        }

        self.session_legacy = {
            "id": "sess-legacy",
            "client_id": self.company_a,
            "contact_id": None,
            "portal_role": "legacy_readonly",
            "idle_expires_at": (now + timedelta(hours=2)).isoformat(),
            "absolute_expires_at": (now + timedelta(days=7)).isoformat(),
            "revoked_at": None,
            "clients": {"id": self.company_a, "name": "Company A Robotics"},
            "portal_contacts": None,
        }

    def tearDown(self):
        try:
            if os.path.exists(self.temp_db.name):
                os.remove(self.temp_db.name)
        except Exception:
            pass

    def _mock_db_with_session(self, session_row, table_handlers=None):
        """Helper to mock Supabase calls handling sessions and custom table queries."""
        def table_router(table_name):
            mock_query = MagicMock()
            mock_query.select.return_value = mock_query
            mock_query.eq.return_value = mock_query
            mock_query.order.return_value = mock_query
            mock_query.limit.return_value = mock_query
            mock_query.update.return_value = mock_query
            mock_query.insert.return_value = mock_query
            mock_query.upsert.return_value = mock_query
            mock_query.in_.return_value = mock_query
            mock_query.is_.return_value = mock_query

            # Default single() returns a query that executes to dict
            mock_single_query = MagicMock()
            mock_single_query.execute.return_value = MagicMock(data={})
            mock_query.single.return_value = mock_single_query

            if table_name == "portal_sessions":
                mock_query.execute.return_value = MagicMock(data=[session_row])
                mock_single_query.execute.return_value = MagicMock(data=session_row)
                return mock_query

            if table_handlers and table_name in table_handlers:
                return table_handlers[table_name](mock_query)

            mock_query.execute.return_value = MagicMock(data=[])
            return mock_query

        return patch.object(main.supabase, "table", side_effect=table_router)

    # ─── 1. Zero Leaks Check on All Portal GET Endpoints ─────────────────────────

    def test_portal_get_endpoints_zero_forbidden_leaks(self):
        """All portal GET endpoints must return 200 with zero sales-internal keys leaked."""
        client_dict = {"id": self.company_a, "name": "Company A", "stated_budget": 500000}

        def handle_clients(q):
            q.single.return_value.execute.return_value = MagicMock(data=client_dict)
            q.execute.return_value = MagicMock(data=[client_dict])
            return q

        def handle_evals(q):
            q.execute.return_value = MagicMock(
                data=[{
                    "property_id": self.property_id,
                    "expected_value": 95000,
                    "properties": {
                        "id": self.property_id,
                        "address": "Ottonomy Ottobot Yeti",
                        "property_value": 120000,
                        "indicative_price_myr": 99000,
                        "indicative_price_note": "Reseller listing Oct 2026",
                        "neighborhood": "Manufacturing",
                        "image_url": "https://example.com/img.jpg",
                        "property_type": "Autonomous Mobile Robot",
                        "sqft": 40000,
                        "estimated_annual_savings": 45000,
                    }
                }]
            )
            return q

        def handle_properties(q):
            q.single.return_value.execute.return_value = MagicMock(data={
                "id": self.property_id,
                "address": "Ottonomy Ottobot Yeti",
            })
            q.execute.return_value = MagicMock(
                data=[{
                    "id": self.property_id,
                    "address": "Ottonomy Ottobot Yeti",
                    "property_value": 120000,
                    "indicative_price_myr": 99000,
                    "indicative_price_note": "Reseller listing Oct 2026",
                    "neighborhood": "Manufacturing",
                    "property_type": "Autonomous Mobile Robot",
                    "image_url": None,
                    "estimated_annual_savings": 45000,
                    "specs": {"payload_tier": 4},
                    "payload_tier": 4,
                    "operational_range_sqft": 50000,
                    "nav_sensors": 4,
                    "lead_time_weeks": 6,
                    "stock_status": "in_stock",
                    "spec_sheet_url": "https://example.com/spec.pdf",
                }]
            )
            return q

        def handle_quotes(q):
            q.execute.return_value = MagicMock(
                data=[{
                    "id": self.quote_id,
                    "client_id": self.company_a,
                    "property_id": self.property_id,
                    "quantity": 2,
                    "status": "sent",
                    "notes": "Need fast delivery",
                    "internal_notes": "Rep note: aggressive discount approved",
                    "quoted_amount": 220000,
                    "currency": "MYR",
                    "customer_note": "Includes 2 year warranty",
                    "valid_until": "2026-11-15T00:00:00Z",
                    "requested_at": "2026-10-14T00:00:00Z",
                    "responded_at": None,
                    "sent_at": "2026-10-15T00:00:00Z",
                    "properties": {"address": "Ottonomy Ottobot Yeti"},
                }]
            )
            return q

        def handle_inquiries(q):
            q.execute.return_value = MagicMock(
                data=[{
                    "id": "inq-1",
                    "client_id": self.company_a,
                    "property_id": self.property_id,
                    "message": "Is floor load adequate?",
                    "status": "replied",
                    "agent_reply": "Yes, 500kg/sqm is fine.",
                    "created_at": "2026-10-15T00:00:00Z",
                    "properties": {"address": "Ottonomy Ottobot Yeti"},
                    "inquiry_messages": [{
                        "id": "msg-1",
                        "inquiry_id": "inq-1",
                        "sender": "rep",
                        "body": "Yes, 500kg/sqm is fine.",
                        "read_at": None,
                        "created_at": "2026-10-15T01:00:00Z",
                    }],
                }]
            )
            return q

        handlers = {
            "clients": handle_clients,
            "pipeline_evaluations": handle_evals,
            "properties": handle_properties,
            "portal_quotes": handle_quotes,
            "client_inquiries": handle_inquiries,
        }

        with self._mock_db_with_session(self.session_a, handlers):
            headers = {"Authorization": f"Bearer {self.token_a}"}

            # 1. GET /dashboard
            res = self.client.get(f"/api/portal/{self.company_a}/dashboard", headers=headers)
            self.assertEqual(res.status_code, 200)
            data = res.json()
            assert_no_forbidden(data)
            self.assertEqual(find_forbidden_keys(data), [])
            for match in data.get("matches", []):
                self.assertNotIn("expected_value", match)
                self.assertNotIn("score", match)

            # 2. GET /catalog
            res = self.client.get(f"/api/portal/{self.company_a}/catalog", headers=headers)
            self.assertEqual(res.status_code, 200)
            catalog_data = res.json()
            assert_no_forbidden(catalog_data)
            self.assertEqual(find_forbidden_keys(catalog_data), [])

            # 3. GET /quotes
            res = self.client.get(f"/api/portal/{self.company_a}/quotes", headers=headers)
            self.assertEqual(res.status_code, 200)
            quotes_data = res.json()
            assert_no_forbidden(quotes_data)
            for q in quotes_data.get("quotes", []):
                self.assertNotIn("internal_notes", q)
                self.assertNotIn("rep_notes", q)

            # 4. GET /inquiries
            res = self.client.get(f"/api/portal/{self.company_a}/inquiries", headers=headers)
            self.assertEqual(res.status_code, 200)
            assert_no_forbidden(res.json())

            # 5. GET /preferences
            res = self.client.get(f"/api/portal/{self.company_a}/preferences", headers=headers)
            self.assertEqual(res.status_code, 200)
            assert_no_forbidden(res.json())

            # 6. GET /activity
            res = self.client.get(f"/api/portal/{self.company_a}/activity", headers=headers)
            self.assertEqual(res.status_code, 200)
            assert_no_forbidden(res.json())

    # ─── 2. Cross-Company Isolation ──────────────────────────────────────────────

    def test_cross_company_isolation(self):
        """Company A session attempting to access Company B routes returns 403."""
        with self._mock_db_with_session(self.session_a):
            headers = {"Authorization": f"Bearer {self.token_a}"}

            # Company A cannot view Company B's dashboard
            res = self.client.get(f"/api/portal/{self.company_b}/dashboard", headers=headers)
            self.assertEqual(res.status_code, 403)

            # Company A cannot view Company B's catalog
            res = self.client.get(f"/api/portal/{self.company_b}/catalog", headers=headers)
            self.assertEqual(res.status_code, 403)

            # Company A cannot view Company B's quotes
            res = self.client.get(f"/api/portal/{self.company_b}/quotes", headers=headers)
            self.assertEqual(res.status_code, 403)

            # Company A cannot post quote for Company B
            res = self.client.post(
                f"/api/portal/{self.company_b}/quotes",
                headers=headers,
                json={"property_id": self.property_id, "quantity": 1},
            )
            self.assertEqual(res.status_code, 403)

            # Company A cannot view Company B's inquiries
            res = self.client.get(f"/api/portal/{self.company_b}/inquiries", headers=headers)
            self.assertEqual(res.status_code, 403)

            # Company A cannot post inquiry for Company B
            res = self.client.post(
                f"/api/portal/{self.company_b}/inquiry",
                headers=headers,
                json={"property_id": self.property_id, "message": "Hi"},
            )
            self.assertEqual(res.status_code, 403)

            # Company A cannot view Company B's preferences
            res = self.client.get(f"/api/portal/{self.company_b}/preferences", headers=headers)
            self.assertEqual(res.status_code, 403)

            # Company A cannot update Company B's preferences
            res = self.client.put(
                f"/api/portal/{self.company_b}/preferences",
                headers=headers,
                json={"industry": "Malicious Update"},
            )
            self.assertEqual(res.status_code, 403)

            # Company A cannot view Company B's activity
            res = self.client.get(f"/api/portal/{self.company_b}/activity", headers=headers)
            self.assertEqual(res.status_code, 403)

    # ─── 3. Legacy Read-Only Write Gating ────────────────────────────────────────

    def test_legacy_readonly_session_blocks_all_writes(self):
        """A legacy_readonly session cannot perform mutations (returns 403)."""
        with self._mock_db_with_session(self.session_legacy):
            headers = {"Authorization": f"Bearer {self.token_legacy}"}

            # Quotes POST
            res = self.client.post(
                f"/api/portal/{self.company_a}/quotes",
                headers=headers,
                json={"property_id": self.property_id, "quantity": 1},
            )
            self.assertEqual(res.status_code, 403)

            # Feedback PUT
            res = self.client.put(
                f"/api/portal/{self.company_a}/catalog/{self.property_id}/feedback",
                headers=headers,
                json={"interest": "interested"},
            )
            self.assertEqual(res.status_code, 403)

            # Preferences PUT
            res = self.client.put(
                f"/api/portal/{self.company_a}/preferences",
                headers=headers,
                json={"stated_budget": 100000},
            )
            self.assertEqual(res.status_code, 403)

            # Inquiry POST
            res = self.client.post(
                f"/api/portal/{self.company_a}/inquiry",
                headers=headers,
                json={"property_id": self.property_id, "message": "Test"},
            )
            self.assertEqual(res.status_code, 403)

    # ─── 4. Quote Transition Rules & Integrity ───────────────────────────────────

    def test_quote_transition_matrix(self):
        """Verify strict state transitions and actor permissions for quotes."""
        self.assertTrue(can_quote_transition("portal", "sent", "accepted"))
        self.assertTrue(can_quote_transition("portal", "sent", "declined"))
        self.assertFalse(can_quote_transition("portal", "requested", "accepted"))
        self.assertFalse(can_quote_transition("portal", "requested", "declined"))
        self.assertFalse(can_quote_transition("portal", "accepted", "declined"))

        self.assertTrue(can_quote_transition("rep", "requested", "sent"))
        self.assertFalse(can_quote_transition("rep", "requested", "accepted"))
        self.assertFalse(can_quote_transition("rep", "sent", "accepted"))

        def handle_quote_requested(q):
            q.single.return_value.execute.return_value = MagicMock(
                data={
                    "id": self.quote_id,
                    "client_id": self.company_a,
                    "status": "requested",
                }
            )
            return q

        # Portal client attempting to accept a 'requested' quote returns 409
        with self._mock_db_with_session(self.session_a, {"portal_quotes": handle_quote_requested}):
            res = self.client.post(
                f"/api/portal/{self.company_a}/quotes/{self.quote_id}/respond",
                headers={"Authorization": f"Bearer {self.token_a}"},
                json={"response": "accepted"},
            )
            self.assertEqual(res.status_code, 409)

        def handle_quote_accepted(q):
            q.single.return_value.execute.return_value = MagicMock(
                data={
                    "id": self.quote_id,
                    "client_id": self.company_a,
                    "status": "accepted",
                }
            )
            return q

        # Already accepted quote cannot be re-responded (returns 409)
        with self._mock_db_with_session(self.session_a, {"portal_quotes": handle_quote_accepted}):
            res = self.client.post(
                f"/api/portal/{self.company_a}/quotes/{self.quote_id}/respond",
                headers={"Authorization": f"Bearer {self.token_a}"},
                json={"response": "declined"},
            )
            self.assertEqual(res.status_code, 409)

    def test_duplicate_open_quote_returns_409(self):
        """Requesting another quote for the same unit while one is open returns 409."""
        def handle_properties(q):
            q.single.return_value.execute.return_value = MagicMock(
                data={"id": self.property_id, "address": "Ottonomy Ottobot Yeti"}
            )
            return q

        def handle_quotes(q):
            q.execute.return_value = MagicMock(
                data=[{"id": "existing-quote-id", "status": "requested"}]
            )
            return q

        handlers = {
            "properties": handle_properties,
            "portal_quotes": handle_quotes,
        }

        with self._mock_db_with_session(self.session_a, handlers):
            res = self.client.post(
                f"/api/portal/{self.company_a}/quotes",
                headers={"Authorization": f"Bearer {self.token_a}"},
                json={"property_id": self.property_id, "quantity": 1},
            )
            self.assertEqual(res.status_code, 409)

    # ─── 5. Unit Feedback Partial Update Integrity ───────────────────────────────

    def test_feedback_partial_update_preserves_existing_fields(self):
        """Updating 'is_saved' must preserve existing 'interest' and 'reason'."""
        captured_updates = []

        def handle_properties(q):
            q.single.return_value.execute.return_value = MagicMock(
                data={"id": self.property_id, "address": "Ottonomy Ottobot Yeti"}
            )
            return q

        def handle_feedback(q):
            # ex_res.data
            q.execute.return_value = MagicMock(
                data=[{
                    "id": "fb-1",
                    "interest": "interested",
                    "reason": "High payload",
                    "is_saved": False,
                }]
            )
            def capture_update(payload, **kwargs):
                captured_updates.append(payload)
                mock_ex = MagicMock()
                mock_ex.eq.return_value = mock_ex
                mock_ex.execute.return_value = MagicMock(data=[payload])
                return mock_ex
            q.update.side_effect = capture_update
            return q

        handlers = {
            "properties": handle_properties,
            "portal_unit_feedback": handle_feedback,
        }

        with self._mock_db_with_session(self.session_a, handlers):
            res = self.client.put(
                f"/api/portal/{self.company_a}/catalog/{self.property_id}/feedback",
                headers={"Authorization": f"Bearer {self.token_a}"},
                json={"is_saved": True},
            )
            self.assertEqual(res.status_code, 200)
            self.assertTrue(len(captured_updates) > 0)
            # Notice update_payload should contain is_saved, but NOT overwrite interest or reason with None!
            self.assertEqual(captured_updates[0]["is_saved"], True)
            self.assertNotIn("interest", captured_updates[0])
            self.assertNotIn("reason", captured_updates[0])

    # ─── 6. Write Rate Limiter Enforcement ───────────────────────────────────────

    def test_portal_write_rate_limiter_returns_429(self):
        """21 writes within 60s must return 429."""
        def handle_properties(q):
            q.single.return_value.execute.return_value = MagicMock(
                data={"id": self.property_id, "address": "Ottonomy Ottobot Yeti"}
            )
            return q

        with self._mock_db_with_session(self.session_a, {"properties": handle_properties}):
            headers = {"Authorization": f"Bearer {self.token_a}"}

            for i in range(20):
                res = self.client.put(
                    f"/api/portal/{self.company_a}/catalog/{self.property_id}/feedback",
                    headers=headers,
                    json={"is_saved": True},
                )
                self.assertEqual(res.status_code, 200, f"Attempt {i+1} failed with {res.status_code}")

            # 21st write attempt must be blocked with 429
            res = self.client.put(
                f"/api/portal/{self.company_a}/catalog/{self.property_id}/feedback",
                headers=headers,
                json={"is_saved": True},
            )
            self.assertEqual(res.status_code, 429)


if __name__ == "__main__":
    unittest.main()
