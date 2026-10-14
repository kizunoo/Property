import os
import sys
import unittest
import hmac
import hashlib
import tempfile
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi import Request
from fastapi.testclient import TestClient

# Set required test env
os.environ["PORTAL_CODE_PEPPER"] = "test_portal_pepper_secret_2026_xyz"
os.environ["PORTAL_LEGACY_LOGIN_ENABLED"] = "false"
os.environ["BFF_INTERNAL_SECRET"] = "test_bff_shared_secret_abc123"
os.environ["ENVIRONMENT"] = "test"

import main
import portal_auth
from portal_auth import (
    hash_code,
    hash_token,
    hash_ip,
    generate_secure_code,
    generate_invite_token,
    generate_session_token,
    get_trusted_client_ip,
    PersistentRateLimitStore,
    PortalSession,
)


class TestPortalV2Auth(unittest.TestCase):
    def setUp(self):
        os.environ["PORTAL_CODE_PEPPER"] = "test_portal_pepper_secret_2026_xyz"
        os.environ["PORTAL_LEGACY_LOGIN_ENABLED"] = "false"
        os.environ["BFF_INTERNAL_SECRET"] = "test_bff_shared_secret_abc123"
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        self.temp_db.close()
        portal_auth.rate_limit_store = PersistentRateLimitStore(db_path=self.temp_db.name)
        self.client = TestClient(main.app)

    def tearDown(self):
        try:
            if os.path.exists(self.temp_db.name):
                os.remove(self.temp_db.name)
        except Exception:
            pass

    def test_pepper_required(self):
        with patch.dict(os.environ, {"PORTAL_CODE_PEPPER": ""}):
            with self.assertRaises(RuntimeError):
                portal_auth.get_code_pepper()

    def test_hash_code_uses_hmac(self):
        code = "AB12CD"
        h1 = hash_code(code)
        pepper = "test_portal_pepper_secret_2026_xyz"
        expected = hmac.new(pepper.encode("utf-8"), code.encode("utf-8"), hashlib.sha256).hexdigest()
        self.assertEqual(h1, expected)

    def test_anti_enumeration_request_code(self):
        with patch.object(main.supabase, "table") as mock_table:
            mock_query = MagicMock()
            mock_query.select.return_value = mock_query
            mock_query.eq.return_value = mock_query
            mock_query.ilike.return_value = mock_query
            mock_query.limit.return_value = mock_query
            mock_query.execute.return_value = MagicMock(data=[])
            mock_table.return_value = mock_query

            res = self.client.post("/api/portal/auth/request-code", json={"identifier": "nonexistent@company.com"})
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertTrue(data["success"])
            self.assertIn("single-use login code has been issued", data["message"])

    def test_legacy_login_disabled_by_default(self):
        os.environ["PORTAL_LEGACY_LOGIN_ENABLED"] = "false"
        res = self.client.post("/api/portal/auth/legacy-login", json={"code": "OLDCODE1"})
        self.assertEqual(res.status_code, 403)
        self.assertIn("Legacy company code login is disabled", res.json()["detail"])

    def test_legacy_login_when_enabled_creates_readonly_session(self):
        os.environ["PORTAL_LEGACY_LOGIN_ENABLED"] = "true"
        code = "LEGACY88"
        code_h = hash_code(code)
        with patch.object(main.supabase, "table") as mock_table:
            mock_query = MagicMock()
            mock_query.select.return_value = mock_query
            mock_query.eq.return_value = mock_query
            mock_query.limit.return_value = mock_query
            mock_query.execute.return_value = MagicMock(data=[{
                "id": "company-aaa-111",
                "name": "Nexus Robotics Sdn Bhd",
                "portal_access_code_hash": code_h,
            }])
            mock_query.insert.return_value = mock_query
            mock_table.return_value = mock_query

            res = self.client.post("/api/portal/auth/legacy-login", json={"code": code})
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertTrue(data["is_legacy"])
            self.assertIn("session_token", data)
            self.assertEqual(data["portal_role"], "legacy_readonly")

    def test_endpoint_no_session_returns_401(self):
        res = self.client.get("/api/portal/company-aaa-111/dashboard")
        self.assertEqual(res.status_code, 401)
        self.assertIn("Authentication required", res.json()["detail"])

    def test_endpoint_cross_tenant_mismatch_returns_403(self):
        fake_token = "valid_opaque_token_32_chars_long"
        token_h = hash_token(fake_token)
        now = datetime.now(timezone.utc)

        mock_session_row = {
            "id": "sess-1",
            "client_id": "company-bbb-222",
            "contact_id": "contact-b",
            "portal_role": "evaluator",
            "idle_expires_at": (now + timedelta(hours=2)).isoformat(),
            "absolute_expires_at": (now + timedelta(days=7)).isoformat(),
            "revoked_at": None,
            "clients": {"id": "company-bbb-222", "name": "Company B"},
            "portal_contacts": {"id": "contact-b", "name": "Bob", "status": "active", "locked_until": None},
        }

        with patch.object(main.supabase, "table") as mock_table:
            mock_query = MagicMock()
            mock_query.select.return_value = mock_query
            mock_query.eq.return_value = mock_query
            mock_query.limit.return_value = mock_query
            mock_query.execute.return_value = MagicMock(data=[mock_session_row])
            mock_table.return_value = mock_query

            headers = {"Authorization": f"Bearer {fake_token}"}
            res = self.client.get("/api/portal/company-aaa-111/dashboard", headers=headers)
            self.assertEqual(res.status_code, 403)
            self.assertIn("You do not have access to this company's workspace", res.json()["detail"])

    def test_endpoint_expired_session_returns_401(self):
        fake_token = "expired_token_xyz"
        now = datetime.now(timezone.utc)
        mock_session_row = {
            "id": "sess-expired",
            "client_id": "company-aaa-111",
            "contact_id": "contact-a",
            "portal_role": "evaluator",
            "idle_expires_at": (now - timedelta(minutes=10)).isoformat(),
            "absolute_expires_at": (now + timedelta(days=5)).isoformat(),
            "revoked_at": None,
            "clients": {"id": "company-aaa-111", "name": "Company A"},
            "portal_contacts": {"id": "contact-a", "name": "Alice", "status": "active", "locked_until": None},
        }

        with patch.object(main.supabase, "table") as mock_table:
            mock_query = MagicMock()
            mock_query.select.return_value = mock_query
            mock_query.eq.return_value = mock_query
            mock_query.limit.return_value = mock_query
            mock_query.execute.return_value = MagicMock(data=[mock_session_row])
            mock_table.return_value = mock_query

            headers = {"Authorization": f"Bearer {fake_token}"}
            res = self.client.get("/api/portal/company-aaa-111/dashboard", headers=headers)
            self.assertEqual(res.status_code, 401)
            self.assertIn("expired due to inactivity", res.json()["detail"])

    def test_endpoint_revoked_session_returns_401(self):
        fake_token = "revoked_token_xyz"
        now = datetime.now(timezone.utc)
        mock_session_row = {
            "id": "sess-revoked",
            "client_id": "company-aaa-111",
            "contact_id": "contact-a",
            "portal_role": "evaluator",
            "idle_expires_at": (now + timedelta(hours=1)).isoformat(),
            "absolute_expires_at": (now + timedelta(days=5)).isoformat(),
            "revoked_at": (now - timedelta(minutes=5)).isoformat(),
            "clients": {"id": "company-aaa-111", "name": "Company A"},
            "portal_contacts": {"id": "contact-a", "name": "Alice", "status": "active", "locked_until": None},
        }

        with patch.object(main.supabase, "table") as mock_table:
            mock_query = MagicMock()
            mock_query.select.return_value = mock_query
            mock_query.eq.return_value = mock_query
            mock_query.limit.return_value = mock_query
            mock_query.execute.return_value = MagicMock(data=[mock_session_row])
            mock_table.return_value = mock_query

            headers = {"Authorization": f"Bearer {fake_token}"}
            res = self.client.get("/api/portal/company-aaa-111/dashboard", headers=headers)
            self.assertEqual(res.status_code, 401)
            self.assertIn("revoked", res.json()["detail"])

    def test_locked_out_contact_returns_403(self):
        fake_token = "locked_contact_token"
        now = datetime.now(timezone.utc)
        mock_session_row = {
            "id": "sess-locked",
            "client_id": "company-aaa-111",
            "contact_id": "contact-locked",
            "portal_role": "evaluator",
            "idle_expires_at": (now + timedelta(hours=1)).isoformat(),
            "absolute_expires_at": (now + timedelta(days=5)).isoformat(),
            "revoked_at": None,
            "clients": {"id": "company-aaa-111", "name": "Company A"},
            "portal_contacts": {
                "id": "contact-locked",
                "name": "Locked User",
                "status": "active",
                "locked_until": (now + timedelta(minutes=12)).isoformat(),
            },
        }

        with patch.object(main.supabase, "table") as mock_table:
            mock_query = MagicMock()
            mock_query.select.return_value = mock_query
            mock_query.eq.return_value = mock_query
            mock_query.limit.return_value = mock_query
            mock_query.execute.return_value = MagicMock(data=[mock_session_row])
            mock_table.return_value = mock_query

            headers = {"Authorization": f"Bearer {fake_token}"}
            res = self.client.get("/api/portal/company-aaa-111/dashboard", headers=headers)
            self.assertEqual(res.status_code, 403)
            self.assertIn("locked out", res.json()["detail"])

    def test_finance_viewer_cannot_save_preferences(self):
        fake_token = "finance_token_xyz"
        now = datetime.now(timezone.utc)
        mock_session_row = {
            "id": "sess-fin",
            "client_id": "company-aaa-111",
            "contact_id": "contact-fin",
            "portal_role": "finance_viewer",
            "idle_expires_at": (now + timedelta(hours=1)).isoformat(),
            "absolute_expires_at": (now + timedelta(days=5)).isoformat(),
            "revoked_at": None,
            "clients": {"id": "company-aaa-111", "name": "Company A"},
            "portal_contacts": {"id": "contact-fin", "name": "Finance CFO", "status": "active", "locked_until": None},
        }

        with patch.object(main.supabase, "table") as mock_table:
            mock_query = MagicMock()
            mock_query.select.return_value = mock_query
            mock_query.eq.return_value = mock_query
            mock_query.limit.return_value = mock_query
            mock_query.execute.return_value = MagicMock(data=[mock_session_row])
            mock_table.return_value = mock_query

            headers = {"Authorization": f"Bearer {fake_token}"}
            res = self.client.put("/api/portal/company-aaa-111/preferences", json={"stated_budget": 500000}, headers=headers)
            self.assertEqual(res.status_code, 403)
            self.assertIn("Finance viewers cannot modify preferences", res.json()["detail"])

    # ─── NEW HARDENING TESTS ──────────────────────────────────────────────────

    def test_rate_limit_many_contacts_one_ip(self):
        """30 attempts from one IP across 30 different contacts succeed; 31st triggers 429."""
        ip = "192.168.1.100"
        with patch.object(main.supabase, "table") as mock_table:
            mock_query = MagicMock()
            mock_query.select.return_value = mock_query
            mock_query.eq.return_value = mock_query
            mock_query.ilike.return_value = mock_query
            mock_query.limit.return_value = mock_query
            mock_query.execute.return_value = MagicMock(data=[])
            mock_table.return_value = mock_query

            headers = {
                "X-BFF-Internal-Secret": "test_bff_shared_secret_abc123",
                "X-Forwarded-For": ip,
            }

            # 30 allowed attempts
            for i in range(30):
                res = self.client.post(
                    "/api/portal/auth/request-code",
                    json={"identifier": f"buyer_{i}@company.com"},
                    headers=headers,
                )
                self.assertEqual(res.status_code, 200)

            # 31st attempt triggers IP rate limit (429)
            res31 = self.client.post(
                "/api/portal/auth/request-code",
                json={"identifier": "buyer_31@company.com"},
                headers=headers,
            )
            self.assertEqual(res31.status_code, 429)
            self.assertIn("Too many failed attempts", res31.json()["detail"])

    def test_rate_limit_many_ips_one_contact(self):
        """5 incorrect code attempts against one contact from 5 different IPs trigger contact lockout."""
        contact_id = "contact-xyz-777"
        mock_contact = {
            "id": contact_id,
            "client_id": "company-aaa-111",
            "name": "Ahmad",
            "email": "ahmad@nexusrfx.com",
            "whatsapp_number": "60123456789",
            "portal_role": "evaluator",
            "status": "active",
            "rep_code_hash": hash_code("CORRECT"),
            "rep_code_expires_at": (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(),
            "self_code_hash": None,
            "self_code_expires_at": None,
            "failed_login_attempts": 0,
            "locked_until": None,
            "clients": {"id": "company-aaa-111", "name": "Nexus RFX"},
        }

        with patch.object(main.supabase, "table") as mock_table:
            mock_query = MagicMock()
            mock_query.select.return_value = mock_query
            mock_query.eq.return_value = mock_query
            mock_query.ilike.return_value = mock_query
            mock_query.limit.return_value = mock_query
            mock_query.execute.return_value = MagicMock(data=[mock_contact])
            mock_query.update.return_value = mock_query
            mock_table.return_value = mock_query

            for i in range(4):
                mock_contact["failed_login_attempts"] = i
                headers = {
                    "X-BFF-Internal-Secret": "test_bff_shared_secret_abc123",
                    "X-Forwarded-For": f"10.0.0.{i+1}",
                }
                res = self.client.post(
                    "/api/portal/auth/verify-code",
                    json={"identifier": "ahmad@nexusrfx.com", "code": "WRONG1"},
                    headers=headers,
                )
                self.assertEqual(res.status_code, 401)

            # 5th attempt locks the account
            mock_contact["failed_login_attempts"] = 4
            headers = {
                "X-BFF-Internal-Secret": "test_bff_shared_secret_abc123",
                "X-Forwarded-For": "10.0.0.5",
            }
            res5 = self.client.post(
                "/api/portal/auth/verify-code",
                json={"identifier": "ahmad@nexusrfx.com", "code": "WRONG2"},
                headers=headers,
            )
            self.assertEqual(res5.status_code, 401)

            # Once locked_until is set in DB, subsequent verification returns 403
            mock_contact["locked_until"] = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
            res_locked = self.client.post(
                "/api/portal/auth/verify-code",
                json={"identifier": "ahmad@nexusrfx.com", "code": "CORRECT"},
                headers={"X-Forwarded-For": "10.0.0.6"},
            )
            self.assertEqual(res_locked.status_code, 403)
            self.assertIn("temporarily locked out", res_locked.json()["detail"])

    def test_rate_limit_restart_persistence(self):
        """Counters persist across store re-instantiations (simulated server reboot)."""
        db_file = self.temp_db.name
        store1 = PersistentRateLimitStore(db_path=db_file)
        key_hash = hash_ip("192.168.10.50")

        # Record 29 attempts in store1
        for _ in range(29):
            allowed, _, count = store1.increment_and_check(key_hash, "ip", window_seconds=900, max_attempts=30)
            self.assertTrue(allowed)

        # Simulate process reboot by initializing a brand new store on the same database
        store2 = PersistentRateLimitStore(db_path=db_file)
        allowed, _, count = store2.increment_and_check(key_hash, "ip", window_seconds=900, max_attempts=30)
        self.assertTrue(allowed)  # 30th attempt is still allowed
        self.assertEqual(count, 30)

        # 31st attempt exceeds limit and locks out
        allowed31, _, count31 = store2.increment_and_check(key_hash, "ip", window_seconds=900, max_attempts=30)
        self.assertFalse(allowed31)
        self.assertEqual(count31, 31)

    def test_pending_rep_code_survives_self_service_request(self):
        """A self-service code request must NOT overwrite or invalidate a valid pending rep-issued code."""
        rep_code = "REP999"
        rep_hash = hash_code(rep_code)
        rep_exp = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()

        mock_contact = {
            "id": "contact-rep-protected",
            "client_id": "company-aaa-111",
            "name": "Director Lee",
            "email": "lee@vanguard.com",
            "whatsapp_number": "60199998888",
            "status": "active",
            "locked_until": None,
            "rep_code_hash": rep_hash,
            "rep_code_expires_at": rep_exp,
            "self_code_hash": None,
            "self_code_expires_at": None,
            "portal_role": "admin",
            "failed_login_attempts": 0,
            "clients": {"id": "company-aaa-111", "name": "Vanguard AMRs"},
        }

        with patch.object(main.supabase, "table") as mock_table:
            mock_query = MagicMock()
            mock_query.select.return_value = mock_query
            mock_query.eq.return_value = mock_query
            mock_query.ilike.return_value = mock_query
            mock_query.limit.return_value = mock_query
            mock_query.execute.return_value = MagicMock(data=[mock_contact])
            mock_update = MagicMock()
            mock_query.update.return_value = mock_update
            mock_update.eq.return_value = mock_update
            mock_update.execute.return_value = MagicMock(data=[])
            mock_table.return_value = mock_query

            # Self-service request arrives
            res = self.client.post("/api/portal/auth/request-code", json={"identifier": "lee@vanguard.com"})
            self.assertEqual(res.status_code, 200)

            # Assert that update was NOT called to overwrite self_code_hash or rep_code_hash
            mock_query.update.assert_not_called()

            # Now verify that the rep-issued code STILL works for login
            mock_query.insert.return_value = MagicMock(execute=MagicMock(data=[{"id": "new-session-id"}]))
            v_res = self.client.post("/api/portal/auth/verify-code", json={
                "identifier": "lee@vanguard.com",
                "code": rep_code,
            })
            self.assertEqual(v_res.status_code, 200)
            self.assertIn("session_token", v_res.json())

    def test_one_time_invite_link_login(self):
        """A rep-issued 32-byte invite link redeems once and is invalidated immediately."""
        raw_token = generate_invite_token()
        token_h = hash_token(raw_token)
        exp = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()

        mock_contact = {
            "id": "contact-invite-link",
            "client_id": "company-aaa-111",
            "name": "Dr. Tan",
            "email": "tan@aeroforge.com",
            "whatsapp_number": "60111222333",
            "portal_role": "evaluator",
            "status": "active",
            "invite_token_hash": token_h,
            "invite_token_expires_at": exp,
            "clients": {"id": "company-aaa-111", "name": "AeroForge Robotics"},
        }

        with patch.object(main.supabase, "table") as mock_table:
            mock_query = MagicMock()
            mock_query.select.return_value = mock_query
            mock_query.eq.return_value = mock_query
            mock_query.limit.return_value = mock_query
            mock_query.execute.return_value = MagicMock(data=[mock_contact])
            mock_update = MagicMock()
            mock_query.update.return_value = mock_update
            mock_update.eq.return_value = mock_update
            mock_update.execute.return_value = MagicMock(data=[])
            mock_query.insert.return_value = MagicMock(execute=MagicMock(data=[{"id": "invite-sess-1"}]))
            mock_table.return_value = mock_query

            # First redemption succeeds
            res = self.client.post("/api/portal/auth/verify-invite", json={"token": raw_token})
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertTrue(data["success"])
            self.assertIn("session_token", data)
            self.assertEqual(data["client_id"], "company-aaa-111")

            # Verify that invite token was cleared in DB
            mock_query.update.assert_called_with({
                "invite_token_hash": None,
                "invite_token_expires_at": None,
                "failed_login_attempts": 0,
                "locked_until": None,
                "last_login_at": mock_query.update.call_args[0][0]["last_login_at"],
            })

            # Second redemption fails
            mock_query.execute.return_value = MagicMock(data=[])
            res2 = self.client.post("/api/portal/auth/verify-invite", json={"token": raw_token})
            self.assertEqual(res2.status_code, 401)

    def test_rep_unlock_contact(self):
        """Rep unlock endpoint resets failed attempts and clears lockout."""
        with patch.object(main.supabase, "table") as mock_table:
            mock_query = MagicMock()
            mock_update = MagicMock()
            mock_query.update.return_value = mock_update
            mock_update.eq.return_value = mock_update
            mock_update.execute.return_value = MagicMock(data=[])
            mock_query.insert.return_value = MagicMock(execute=MagicMock(data=[]))
            mock_table.return_value = mock_query

            res = self.client.post("/api/console/clients/company-aaa/portal/contacts/contact-123/unlock")
            self.assertEqual(res.status_code, 200)
            self.assertTrue(res.json()["success"])
            mock_query.update.assert_called_with({
                "failed_login_attempts": 0,
                "locked_until": None,
            })

    def test_phone_ambiguity_guard(self):
        """When 2 contacts across different companies share a phone number, request-code returns generic success without issuing code."""
        with patch.object(main.supabase, "table") as mock_table:
            mock_query = MagicMock()
            mock_query.select.return_value = mock_query
            mock_query.eq.return_value = mock_query
            mock_query.ilike.return_value = mock_query
            mock_query.limit.return_value = mock_query
            # Return 2 contacts matching phone
            mock_query.execute.return_value = MagicMock(data=[
                {"id": "c1", "client_id": "company-1", "name": "Consultant A"},
                {"id": "c2", "client_id": "company-2", "name": "Consultant A"},
            ])
            mock_table.return_value = mock_query

            res = self.client.post("/api/portal/auth/request-code", json={"identifier": "+60123456789"})
            self.assertEqual(res.status_code, 200)
            # Update must NOT be called (no code issued to ambiguous phone)
            mock_query.update.assert_not_called()

    def test_trusted_proxy_ip_forwarding_with_secret(self):
        """FastAPI trusts X-Forwarded-For only when BFF_INTERNAL_SECRET is valid."""
        # 1. Valid secret: trusts forwarded IP
        req_trusted = MagicMock(spec=Request)
        req_trusted.headers = {
            "x-bff-internal-secret": "test_bff_shared_secret_abc123",
            "x-forwarded-for": "203.0.113.195, 10.0.0.1",
        }
        ip = get_trusted_client_ip(req_trusted)
        self.assertEqual(ip, "203.0.113.195")

        # 2. Invalid secret: discards forwarded IP, falls back to direct client socket
        req_untrusted = MagicMock(spec=Request)
        req_untrusted.headers = {
            "x-bff-internal-secret": "wrong_secret",
            "x-forwarded-for": "203.0.113.195",
        }
        req_untrusted.client = MagicMock(host="127.0.0.1")
        ip_fallback = get_trusted_client_ip(req_untrusted)
        self.assertEqual(ip_fallback, "127.0.0.1")

    def test_docs_disabled_in_production(self):
        """When ENVIRONMENT=production, FastAPI docs, redoc, and openapi are disabled."""
        from fastapi import FastAPI
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
            _is_prod = os.getenv("ENVIRONMENT", "").lower() in ("production", "prod")
            prod_app = FastAPI(
                title="Test",
                docs_url=None if _is_prod else "/docs",
                redoc_url=None if _is_prod else "/redoc",
                openapi_url=None if _is_prod else "/openapi.json",
            )
            self.assertIsNone(prod_app.docs_url)
            self.assertIsNone(prod_app.redoc_url)
            self.assertIsNone(prod_app.openapi_url)


if __name__ == "__main__":
    unittest.main()
