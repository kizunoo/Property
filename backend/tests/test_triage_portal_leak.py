"""
Test that inquiry triage priority, status, and metadata NEVER leak to portal responses.
Triage labels and alerts are rep-side only.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient

os.environ["PORTAL_CODE_PEPPER"] = "test_portal_pepper_secret_2026_xyz"
os.environ["PORTAL_LEGACY_LOGIN_ENABLED"] = "false"
os.environ["BFF_INTERNAL_SECRET"] = "test_bff_shared_secret_abc123"
os.environ["CALENDAR_SIGNING_SECRET"] = "test_calendar_secret_xyz_123"
os.environ["ENVIRONMENT"] = "testing"

import main
import portal_auth
import triage_service
from portal_auth import PersistentRateLimitStore


def assert_no_triage_leaks(obj, path=""):
    """Recursively assert that no dictionary key anywhere in the response starts with 'triage'."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            curr = f"{path}.{k}" if path else k
            assert not k.lower().startswith("triage"), (
                f"Leaked triage key '{k}' found in portal response at path '{curr}'"
            )
            assert_no_triage_leaks(v, curr)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            assert_no_triage_leaks(item, f"{path}[{i}]")


class TestTriagePortalLeak(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        self.temp_db.close()
        portal_auth.rate_limit_store = PersistentRateLimitStore(db_path=self.temp_db.name)
        self.client = TestClient(main.app)

        self.client_id = "11111111-1111-1111-1111-111111111111"
        self.property_id = "22222222-2222-2222-2222-222222222222"
        self.token = "portal_test_token_32_bytes_long_123"
        now = datetime.now(timezone.utc)

        self.session = {
            "id": "sess-test",
            "client_id": self.client_id,
            "contact_id": "contact-test",
            "portal_role": "evaluator",
            "idle_expires_at": (now + timedelta(hours=2)).isoformat(),
            "absolute_expires_at": (now + timedelta(days=7)).isoformat(),
            "revoked_at": None,
            "clients": {"id": self.client_id, "name": "Alpha Corp Robotics"},
            "portal_contacts": {"id": "contact-test", "name": "Alice", "status": "active", "locked_until": None},
        }

    def tearDown(self):
        try:
            if os.path.exists(self.temp_db.name):
                os.remove(self.temp_db.name)
        except Exception:
            pass

    def test_inquiry_submission_and_listing_zero_triage_leaks(self):
        """Portal inquiries endpoints must never leak triage_* columns to the company."""
        inquiries_store = []
        messages_store = []

        def table_router(table_name):
            q = MagicMock()
            q.select.return_value = q
            q.eq.return_value = q
            q.order.return_value = q
            q.limit.return_value = q
            q.update.return_value = q
            q.insert.return_value = q
            q.in_.return_value = q
            q.is_.return_value = q

            single_mock = MagicMock()
            q.single.return_value = single_mock

            if table_name == "portal_sessions":
                q.execute.return_value = MagicMock(data=[self.session])
                single_mock.execute.return_value = MagicMock(data=self.session)
                return q

            if table_name == "clients":
                client_data = {"id": self.client_id, "name": "Alpha Corp Robotics", "assigned_agent_id": "rep-1"}
                q.execute.return_value = MagicMock(data=[client_data])
                single_mock.execute.return_value = MagicMock(data=client_data)
                return q

            if table_name == "properties":
                prop_data = {"id": self.property_id, "address": "Bot-500 AMR", "property_value": 150000, "specs": {}}
                q.execute.return_value = MagicMock(data=[prop_data])
                single_mock.execute.return_value = MagicMock(data=prop_data)
                return q

            if table_name == "client_inquiries":
                def do_insert(payload):
                    record = dict(payload)
                    record["id"] = "inq-999"
                    record["created_at"] = datetime.now(timezone.utc).isoformat()
                    inquiries_store.append(record)
                    mock_res = MagicMock(data=[record])
                    return MagicMock(execute=MagicMock(return_value=mock_res))

                def do_update(payload):
                    for r in inquiries_store:
                        if r.get("id") == "inq-999":
                            r.update(payload)
                    mock_res = MagicMock(data=inquiries_store)
                    return MagicMock(execute=MagicMock(return_value=mock_res))

                q.insert.side_effect = do_insert
                q.update.side_effect = do_update
                q.execute.return_value = MagicMock(data=inquiries_store)
                single_mock.execute.return_value = MagicMock(data=inquiries_store[0] if inquiries_store else {})
                return q

            if table_name == "inquiry_messages":
                def do_msg_insert(payload):
                    record = dict(payload)
                    record["id"] = f"msg-{len(messages_store) + 1}"
                    record["created_at"] = datetime.now(timezone.utc).isoformat()
                    messages_store.append(record)
                    mock_res = MagicMock(data=[record])
                    return MagicMock(execute=MagicMock(return_value=mock_res))

                q.insert.side_effect = do_msg_insert
                q.execute.return_value = MagicMock(data=messages_store)
                single_mock.execute.return_value = MagicMock(data=messages_store[0] if messages_store else {})
                return q

            if table_name == "signals":
                q.execute.return_value = MagicMock(data=[])
                return q

            if table_name == "portal_audit_log":
                q.execute.return_value = MagicMock(data=[])
                return q

            q.execute.return_value = MagicMock(data=[])
            single_mock.execute.return_value = MagicMock(data={})
            return q

        with patch.object(main.supabase, "table", side_effect=table_router):
            triage_service.set_db(main.supabase)
            triage_service.set_ai_runner(lambda cid, text: None)
            headers = {"Authorization": f"Bearer {self.token}"}

            # 1. Create inquiry via portal endpoint
            post_res = self.client.post(
                f"/api/portal/{self.client_id}/inquiry",
                headers=headers,
                json={"property_id": self.property_id, "message": "How much is this robot? Need a quote ASAP"},
            )
            self.assertEqual(post_res.status_code, 200)
            inq_json = post_res.json()
            assert_no_triage_leaks(inq_json)

            # 2. Run triage_new_inquiry explicitly synchronously with AI disabled
            triage_res = triage_service.triage_new_inquiry(
                main.supabase,
                client_id=self.client_id,
                inquiry_id="inq-999",
                text="How much is this robot? Need a quote ASAP",
                background=False,
            )
            self.assertIn("priority", triage_res)

            # Confirm inquiry record in DB now contains triage metadata internally
            self.assertTrue(len(inquiries_store) > 0)
            self.assertIn("triage_priority", inquiries_store[0])
            self.assertEqual(inquiries_store[0]["triage_priority"], "urgent")

            # 3. Call GET /api/portal/{client_id}/inquiries - must NOT leak any triage_* keys
            get_res = self.client.get(f"/api/portal/{self.client_id}/inquiries", headers=headers)
            self.assertEqual(get_res.status_code, 200)
            get_json = get_res.json()
            assert_no_triage_leaks(get_json)

            # 4. Post message to thread
            msg_res = self.client.post(
                f"/api/portal/{self.client_id}/inquiries/inq-999/messages",
                headers=headers,
                json={"body": "Can you also send specs sheet?"},
            )
            self.assertEqual(msg_res.status_code, 200)
            assert_no_triage_leaks(msg_res.json())
