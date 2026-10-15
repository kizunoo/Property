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
from portal_auth import (
    hash_token,
    PersistentRateLimitStore,
)


class TestPortalV2Demos(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        self.temp_db.close()
        portal_auth.rate_limit_store = PersistentRateLimitStore(db_path=self.temp_db.name)
        self.client = TestClient(main.app)

        self.company_a = "company-aaa-111"
        self.company_b = "company-bbb-222"
        self.token_a = "token_for_company_a_32_bytes_long"
        self.token_b = "token_for_company_b_32_bytes_long"

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
            mock_query.single.return_value = mock_query
            mock_query.update.return_value = mock_query
            mock_query.insert.return_value = mock_query
            mock_query.in_.return_value = mock_query

            if table_name == "portal_sessions":
                mock_query.execute.return_value = MagicMock(data=[session_row])
                return mock_query

            if table_handlers and table_name in table_handlers:
                return table_handlers[table_name](mock_query)

            mock_query.execute.return_value = MagicMock(data=[])
            return mock_query

        return patch.object(main.supabase, "table", side_effect=table_router)

    def test_company_a_cannot_read_company_b_demos(self):
        """Company A calling Company B's demos endpoint receives 403."""
        with self._mock_db_with_session(self.session_a):
            headers = {"Authorization": f"Bearer {self.token_a}"}
            res = self.client.get(f"/api/portal/{self.company_b}/demos", headers=headers)
            self.assertEqual(res.status_code, 403)
            self.assertIn("You do not have access", res.json()["detail"])

    def test_company_a_can_read_own_demos_with_ics_url(self):
        """Company A successfully reads its own demonstrations including calendar ICS URL."""
        mock_demos = [
            {
                "id": "demo-1",
                "status": "upcoming",
                "scheduled_at": "2026-10-20T10:00:00Z",
                "property_id": "prop-robot-1",
                "confirmation_status": "confirmed",
                "client_confirmed_at": "2026-10-14T08:00:00Z",
                "properties": {"id": "prop-robot-1", "address": "KUKA KR-1000 Titan", "neighborhood": "Automotive Assembly"},
            }
        ]

        def viewings_handler(q):
            q.execute.return_value = MagicMock(data=mock_demos)
            return q

        with self._mock_db_with_session(self.session_a, {"scheduled_viewings": viewings_handler}):
            headers = {"Authorization": f"Bearer {self.token_a}"}
            res = self.client.get(f"/api/portal/{self.company_a}/demos", headers=headers)
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertIn("demos", data)
            self.assertEqual(len(data["demos"]), 1)
            demo = data["demos"][0]
            self.assertEqual(demo["id"], "demo-1")
            self.assertEqual(demo["property_name"], "KUKA KR-1000 Titan")
            self.assertTrue(demo["can_cancel"])
            self.assertIsNotNone(demo["ics_url"])
            self.assertIn("/api/calendar/demo-1.ics?token=", demo["ics_url"])

    def test_company_a_cannot_confirm_company_b_demo(self):
        """Company A cannot confirm a demo belonging to Company B."""
        # Demo belongs to Company B
        demo_b = {
            "id": "demo-b-1",
            "client_id": self.company_b,
            "status": "requested",
            "scheduled_at": "2026-10-22T14:00:00Z",
            "property_id": "prop-2",
        }

        def viewings_handler(q):
            q.execute.return_value = MagicMock(data=demo_b)
            return q

        # Attempted with company A session targeted at company A endpoint
        with self._mock_db_with_session(self.session_a, {"scheduled_viewings": viewings_handler}):
            headers = {"Authorization": f"Bearer {self.token_a}"}
            res = self.client.post(f"/api/portal/{self.company_a}/demos/demo-b-1/confirm", headers=headers)
            self.assertEqual(res.status_code, 403)
            self.assertIn("demo belongs to another company", res.json()["detail"])

    def test_confirm_on_requested_returns_409(self):
        """Confirming a demo with status 'requested' returns 409 Conflict (only 'offered' is confirmable)."""
        demo_a = {
            "id": "demo-a-1",
            "client_id": self.company_a,
            "status": "requested",
            "scheduled_at": "2026-10-22T14:00:00Z",
            "property_id": "prop-1",
        }

        def viewings_handler(q):
            q.execute.return_value = MagicMock(data=demo_a)
            return q

        with self._mock_db_with_session(self.session_a, {"scheduled_viewings": viewings_handler}):
            headers = {"Authorization": f"Bearer {self.token_a}"}
            res = self.client.post(f"/api/portal/{self.company_a}/demos/demo-a-1/confirm", headers=headers)
            self.assertEqual(res.status_code, 409)
            self.assertIn("Cannot confirm", res.json()["detail"])

    def test_confirm_on_cancelled_returns_409(self):
        """Confirming a cancelled demo returns 409 Conflict."""
        demo_a = {
            "id": "demo-a-1",
            "client_id": self.company_a,
            "status": "cancelled",
            "property_id": "prop-1",
        }

        def viewings_handler(q):
            q.execute.return_value = MagicMock(data=demo_a)
            return q

        with self._mock_db_with_session(self.session_a, {"scheduled_viewings": viewings_handler}):
            headers = {"Authorization": f"Bearer {self.token_a}"}
            res = self.client.post(f"/api/portal/{self.company_a}/demos/demo-a-1/confirm", headers=headers)
            self.assertEqual(res.status_code, 409)

    def test_company_a_can_confirm_offered_demo(self):
        """Company A confirms a rep-offered slot successfully."""
        demo_a = {
            "id": "demo-a-1",
            "client_id": self.company_a,
            "status": "offered",
            "scheduled_at": "2026-10-22T14:00:00Z",
            "property_id": "prop-1",
        }

        def viewings_handler(q):
            q.execute.return_value = MagicMock(data=demo_a)
            return q

        with self._mock_db_with_session(self.session_a, {"scheduled_viewings": viewings_handler}):
            headers = {"Authorization": f"Bearer {self.token_a}"}
            res = self.client.post(f"/api/portal/{self.company_a}/demos/demo-a-1/confirm", headers=headers)
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertTrue(data["success"])
            self.assertEqual(data["status"], "upcoming")
            self.assertTrue(data["confirmed"])

    def test_confirm_whatsapp_slot_offer_real_shaped_row_succeeds(self):
        """A real-shaped row inserted by claim_and_book_slot_offer (status='upcoming', confirmation_status='unconfirmed', client_confirmed_at=None) maps to 'offered' and satisfies DEMO_RULES['confirm']."""
        real_shaped_whatsapp_demo = {
            "id": "demo-wa-1",
            "client_id": self.company_a,
            "property_id": "prop-1",
            "scheduled_at": "2026-10-22T14:00:00Z",
            "status": "upcoming",
            "confirmation_status": "unconfirmed",
            "client_confirmed_at": None,
            "source": "whatsapp",
        }

        def viewings_handler(q):
            q.execute.return_value = MagicMock(data=real_shaped_whatsapp_demo)
            return q

        with self._mock_db_with_session(self.session_a, {"scheduled_viewings": viewings_handler}):
            headers = {"Authorization": f"Bearer {self.token_a}"}
            res = self.client.post(f"/api/portal/{self.company_a}/demos/demo-wa-1/confirm", headers=headers)
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertTrue(data["success"])
            self.assertEqual(data["status"], "upcoming")
            self.assertTrue(data["confirmed"])

    def test_company_a_cannot_cancel_company_b_demo(self):
        """Company A cannot cancel a demo belonging to Company B."""
        demo_b = {
            "id": "demo-b-2",
            "client_id": self.company_b,
            "status": "upcoming",
        }

        def viewings_handler(q):
            q.execute.return_value = MagicMock(data=demo_b)
            return q

        with self._mock_db_with_session(self.session_a, {"scheduled_viewings": viewings_handler}):
            headers = {"Authorization": f"Bearer {self.token_a}"}
            res = self.client.post(f"/api/portal/{self.company_a}/demos/demo-b-2/cancel", headers=headers)
            self.assertEqual(res.status_code, 403)
            self.assertIn("demo belongs to another company", res.json()["detail"])

    def test_cancel_on_cancelled_or_completed_returns_409(self):
        """Cancelling an already cancelled or completed demo returns 409."""
        for terminal_status in ["cancelled", "completed"]:
            demo_a = {
                "id": "demo-a-term",
                "client_id": self.company_a,
                "status": terminal_status,
            }

            def viewings_handler(q):
                q.execute.return_value = MagicMock(data=demo_a)
                return q

            with self._mock_db_with_session(self.session_a, {"scheduled_viewings": viewings_handler}):
                headers = {"Authorization": f"Bearer {self.token_a}"}
                res = self.client.post(f"/api/portal/{self.company_a}/demos/demo-a-term/cancel", headers=headers)
                self.assertEqual(res.status_code, 409)

    def test_company_a_can_cancel_own_demo(self):
        """Company A cancels its own demo successfully."""
        demo_a = {
            "id": "demo-a-2",
            "client_id": self.company_a,
            "status": "upcoming",
        }

        def viewings_handler(q):
            q.execute.return_value = MagicMock(data=demo_a)
            return q

        with self._mock_db_with_session(self.session_a, {"scheduled_viewings": viewings_handler}):
            headers = {"Authorization": f"Bearer {self.token_a}"}
            res = self.client.post(
                f"/api/portal/{self.company_a}/demos/demo-a-2/cancel",
                json={"reason": "Scheduling conflict"},
                headers=headers,
            )
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertTrue(data["success"])
            self.assertEqual(data["status"], "cancelled")

    def test_company_a_cannot_reschedule_company_b_demo(self):
        """Company A cannot reschedule a demo belonging to Company B."""
        demo_b = {
            "id": "demo-b-3",
            "client_id": self.company_b,
            "property_id": "prop-b",
            "status": "upcoming",
        }

        def viewings_handler(q):
            q.execute.return_value = MagicMock(data=demo_b)
            return q

        with self._mock_db_with_session(self.session_a, {"scheduled_viewings": viewings_handler}):
            headers = {"Authorization": f"Bearer {self.token_a}"}
            res = self.client.post(
                f"/api/portal/{self.company_a}/demos/demo-b-3/reschedule",
                json={"preferred_date": "2026-10-25T10:00:00Z"},
                headers=headers,
            )
            self.assertEqual(res.status_code, 403)
            self.assertIn("demo belongs to another company", res.json()["detail"])

    def test_company_a_can_reschedule_own_demo(self):
        """Company A reschedules demo: marks previous cancelled and inserts new requested demo."""
        demo_a = {
            "id": "demo-a-3",
            "client_id": self.company_a,
            "property_id": "prop-1",
            "status": "upcoming",
            "scheduled_at": "2026-10-20T10:00:00Z",
        }

        def viewings_handler(q):
            q.execute.return_value = MagicMock(data=demo_a)
            return q

        with self._mock_db_with_session(self.session_a, {"scheduled_viewings": viewings_handler}):
            headers = {"Authorization": f"Bearer {self.token_a}"}
            res = self.client.post(
                f"/api/portal/{self.company_a}/demos/demo-a-3/reschedule",
                json={"preferred_date": "2026-10-25T11:00:00Z", "notes": "Shift by 5 days"},
                headers=headers,
            )
            self.assertEqual(res.status_code, 200, res.json())
            data = res.json()
            self.assertTrue(data["success"])
            self.assertEqual(data["old_demo_id"], "demo-a-3")
            self.assertEqual(data["status"], "requested")

    def test_reschedule_failure_path_leaves_old_demo_intact(self):
        """When reschedule creation fails, error 500 is returned and old demo is left untouched."""
        demo_a = {
            "id": "demo-a-intact",
            "client_id": self.company_a,
            "property_id": "prop-1",
            "status": "upcoming",
            "scheduled_at": "2026-10-20T10:00:00Z",
        }

        def viewings_handler(q):
            # Simulate DB failure during new demo insert
            mock_insert = MagicMock()
            mock_insert.execute.side_effect = Exception("DB Connection Timeout")
            q.insert.return_value = mock_insert
            q.execute.return_value = MagicMock(data=demo_a)
            return q

        with self._mock_db_with_session(self.session_a, {"scheduled_viewings": viewings_handler}):
            headers = {"Authorization": f"Bearer {self.token_a}"}
            res = self.client.post(
                f"/api/portal/{self.company_a}/demos/demo-a-intact/reschedule",
                json={"preferred_date": "2026-10-25T11:00:00Z"},
                headers=headers,
            )
            self.assertEqual(res.status_code, 500)

    def test_rate_limit_21st_write_returns_429(self):
        """21st write within 5-minute sliding window triggers HTTP 429."""
        demo_a = {
            "id": "demo-a-rl",
            "client_id": self.company_a,
            "status": "upcoming",
        }

        def viewings_handler(q):
            q.execute.return_value = MagicMock(data=demo_a)
            return q

        with self._mock_db_with_session(self.session_a, {"scheduled_viewings": viewings_handler}):
            headers = {"Authorization": f"Bearer {self.token_a}"}
            # Execute 20 cancellations
            for i in range(20):
                res = self.client.post(f"/api/portal/{self.company_a}/demos/demo-a-rl/cancel", headers=headers)
                self.assertEqual(res.status_code, 200, f"Call {i+1} failed: {res.text}")

            # 21st write must return 429
            res_21 = self.client.post(f"/api/portal/{self.company_a}/demos/demo-a-rl/cancel", headers=headers)
            self.assertEqual(res_21.status_code, 429)
            self.assertIn("Too many write requests", res_21.json()["detail"])

    def test_legacy_session_cannot_mutate_demos(self):
        """Legacy read-only sessions are prohibited from confirming, cancelling, or rescheduling demos."""
        with self._mock_db_with_session(self.session_legacy):
            headers = {"Authorization": "Bearer legacy_token"}
            res_conf = self.client.post(f"/api/portal/{self.company_a}/demos/demo-1/confirm", headers=headers)
            self.assertEqual(res_conf.status_code, 403)
            self.assertIn("read-only", res_conf.json()["detail"])

            res_cancel = self.client.post(f"/api/portal/{self.company_a}/demos/demo-1/cancel", headers=headers)
            self.assertEqual(res_cancel.status_code, 403)
            self.assertIn("read-only", res_cancel.json()["detail"])

            res_resched = self.client.post(f"/api/portal/{self.company_a}/demos/demo-1/reschedule", json={}, headers=headers)
            self.assertEqual(res_resched.status_code, 403)
            self.assertIn("read-only", res_resched.json()["detail"])


if __name__ == "__main__":
    unittest.main()
