"""
backend/tests/test_agent_auth.py
────────────────────────────────
Unit tests for Part D Stage D1:
- Argon2id password hashing and verification.
- Session token generation and HMAC-SHA256 validation.
- FastAPI dependency get_current_agent self-validation against database.
- Strictly refuses X-Agent-Id header without valid session token.
- Lockout policy: 5 failed attempts locks account for 15 minutes.
- Admin privilege verification.
- Enrollment code flow.
"""

import os
import sys
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi import Request, HTTPException
from fastapi.testclient import TestClient

# Set test environment
os.environ["ENVIRONMENT"] = "testing"
os.environ["AGENT_SESSION_SECRET"] = "testing_agent_auth_secret_pepper_2026_xyz"
os.environ["PORTAL_CODE_PEPPER"] = "testing_portal_pepper_secret_2026_xyz"
os.environ["BFF_INTERNAL_SECRET"] = "testing_bff_secret_12345"

import main
import agent_auth
from agent_auth import (
    hash_password,
    verify_password,
    generate_agent_session_token,
    hash_agent_token,
    generate_enrollment_code,
    hash_enrollment_code,
    get_current_agent,
    require_admin,
    AgentIdentity,
)


class TestAgentAuthD1(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)

    def test_argon2id_hashing_and_verification(self):
        """Argon2id produces verifiable, salt-backed hashes."""
        password = "SecurePassword2026!#"
        pwd_hash = hash_password(password)

        self.assertTrue(pwd_hash.startswith("$argon2id$"))
        self.assertTrue(verify_password(pwd_hash, password))
        self.assertFalse(verify_password(pwd_hash, "WrongPassword123!"))
        self.assertFalse(verify_password(pwd_hash, ""))

    def test_enrollment_code_generation_and_hashing(self):
        """Enrollment codes are generated with proper length and HMAC hashed."""
        code = generate_enrollment_code()
        self.assertEqual(len(code), 12)
        code_h1 = hash_enrollment_code(code)
        code_h2 = hash_enrollment_code(code.lower())
        self.assertEqual(code_h1, code_h2)  # Case-insensitive

    def test_refuses_x_agent_id_header_without_session(self):
        """
        SECURITY REQUIREMENT: FastAPI must NOT trust X-Agent-Id header alone.
        Requests without a valid signed session token must be rejected with 401.
        """
        req = MagicMock(spec=Request)
        req.cookies = {}
        req.headers = {"x-agent-id": "agent-fake-uuid-12345"}
        req.url.path = "/api/agent/me"

        with self.assertRaises(HTTPException) as ctx:
            get_current_agent(req)
        self.assertEqual(ctx.exception.status_code, 401)
        self.assertIn("Authentication required", ctx.exception.detail)

    def test_get_current_agent_valid_session(self):
        """Valid session token looks up database and returns AgentIdentity."""
        raw_token = "valid_agent_raw_token_xyz123"
        token_h = hash_agent_token(raw_token)

        now = datetime.now(timezone.utc)
        mock_session_row = {
            "id": "sess-uuid-001",
            "agent_id": "agent-uuid-100",
            "idle_expires_at": (now + timedelta(hours=8)).isoformat(),
            "absolute_expires_at": (now + timedelta(days=5)).isoformat(),
            "revoked_at": None,
            "agent_accounts": {
                "id": "agent-uuid-100",
                "email": "agent@pipeline-ev.internal",
                "name": "Alex Tan",
                "role": "agent",
                "status": "active",
                "locked_until": None,
            }
        }

        with patch.object(main.supabase, "table") as mock_table:
            mock_query = MagicMock()
            mock_table.return_value = mock_query
            mock_query.select.return_value = mock_query
            mock_query.eq.return_value = mock_query
            mock_query.limit.return_value = mock_query
            mock_query.execute.return_value = MagicMock(data=[mock_session_row])
            mock_query.update.return_value = mock_query

            req = MagicMock(spec=Request)
            req.cookies = {"agent_session": raw_token}
            req.headers = {}

            agent = get_current_agent(req)
            self.assertEqual(agent.agent_id, "agent-uuid-100")
            self.assertEqual(agent.email, "agent@pipeline-ev.internal")
            self.assertEqual(agent.role, "agent")

    def test_get_current_agent_revoked_session(self):
        """Revoked session token returns 401."""
        raw_token = "revoked_raw_token"
        now = datetime.now(timezone.utc)
        mock_session_row = {
            "id": "sess-uuid-002",
            "agent_id": "agent-uuid-100",
            "idle_expires_at": (now + timedelta(hours=8)).isoformat(),
            "absolute_expires_at": (now + timedelta(days=5)).isoformat(),
            "revoked_at": (now - timedelta(minutes=5)).isoformat(),
            "agent_accounts": {
                "id": "agent-uuid-100",
                "email": "agent@pipeline-ev.internal",
                "name": "Alex Tan",
                "role": "agent",
                "status": "active",
            }
        }

        with patch.object(main.supabase, "table") as mock_table:
            mock_query = MagicMock()
            mock_table.return_value = mock_query
            mock_query.select.return_value = mock_query
            mock_query.eq.return_value = mock_query
            mock_query.limit.return_value = mock_query
            mock_query.execute.return_value = MagicMock(data=[mock_session_row])

            req = MagicMock(spec=Request)
            req.cookies = {"agent_session": raw_token}
            req.headers = {}

            with self.assertRaises(HTTPException) as ctx:
                get_current_agent(req)
            self.assertEqual(ctx.exception.status_code, 401)
            self.assertIn("revoked", ctx.exception.detail.lower())

    def test_require_admin_enforcement(self):
        """require_admin permits admins and blocks regular agents."""
        admin = AgentIdentity(
            account_id="adm-1",
            email="admin@pipeline-ev.internal",
            name="Admin",
            role="admin",
            session_id="s1",
        )
        self.assertEqual(require_admin(admin), admin)

        agent = AgentIdentity(
            account_id="rep-1",
            email="rep@pipeline-ev.internal",
            name="Rep",
            role="agent",
            session_id="s2",
            agent_id="rep-uuid-1",
        )
        with self.assertRaises(HTTPException) as ctx:
            require_admin(agent)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_agent_login_lockout_after_five_failed_attempts(self):
        """5 failed login attempts triggers account lockout."""
        mock_account = {
            "id": "agent-lockout-uuid",
            "email": "rep.test@pipeline-ev.internal",
            "name": "Test Rep",
            "role": "agent",
            "password_hash": hash_password("CorrectPassword123!"),
            "status": "active",
            "failed_login_attempts": 4,  # 4 previous failures
            "locked_until": None,
        }

        with patch.object(main.supabase, "table") as mock_table:
            mock_query = MagicMock()
            mock_table.return_value = mock_query
            mock_query.select.return_value = mock_query
            mock_query.ilike.return_value = mock_query
            mock_query.limit.return_value = mock_query
            mock_query.execute.return_value = MagicMock(data=[mock_account])
            mock_query.update.return_value = mock_query

            # 5th failed attempt
            res = self.client.post("/api/agent/login", json={
                "email": "rep.test@pipeline-ev.internal",
                "password": "WrongPassword!",
            })
            self.assertEqual(res.status_code, 403)
            self.assertIn("locked", res.json()["detail"].lower())

    def test_agent_me_endpoint(self):
        """GET /api/agent/me returns session info when authenticated."""
        raw_token = "agent_me_token_xyz"
        now = datetime.now(timezone.utc)
        mock_session_row = {
            "id": "sess-uuid-me",
            "agent_id": "agent-uuid-me",
            "idle_expires_at": (now + timedelta(hours=8)).isoformat(),
            "absolute_expires_at": (now + timedelta(days=5)).isoformat(),
            "revoked_at": None,
            "agent_accounts": {
                "id": "agent-uuid-me",
                "email": "me@pipeline-ev.internal",
                "name": "Me Myself",
                "role": "admin",
                "status": "active",
                "locked_until": None,
            }
        }

        with patch.object(main.supabase, "table") as mock_table:
            mock_query = MagicMock()
            mock_table.return_value = mock_query
            mock_query.select.return_value = mock_query
            mock_query.eq.return_value = mock_query
            mock_query.limit.return_value = mock_query
            mock_query.execute.return_value = MagicMock(data=[mock_session_row])
            mock_query.update.return_value = mock_query

            res = self.client.get("/api/agent/me", cookies={"agent_session": raw_token})
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertTrue(data["authenticated"])
            self.assertEqual(data["email"], "me@pipeline-ev.internal")
            self.assertEqual(data["role"], "admin")

    def test_password_complexity_rules(self):
        """Enforces minimum length 12, email/username exclusion, and dictionary checks."""
        from agent_auth import validate_password_complexity

        # Too short (< 12)
        with self.assertRaises(HTTPException) as ctx:
            validate_password_complexity("Short1!", email="rep@pipeline-ev.internal")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("12 characters", ctx.exception.detail)

        # Contains email address
        with self.assertRaises(HTTPException) as ctx:
            validate_password_complexity("rep@pipeline-ev.internal2026!", email="rep@pipeline-ev.internal")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("email address", ctx.exception.detail)

        # Contains email username (local part >= 3 chars)
        with self.assertRaises(HTTPException) as ctx:
            validate_password_complexity("Secret_rep_2026!#", email="rep@pipeline-ev.internal")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("username", ctx.exception.detail)

        # Disallowed common password
        with self.assertRaises(HTTPException) as ctx:
            validate_password_complexity("password123456", email="rep@pipeline-ev.internal")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("common", ctx.exception.detail)

        # Strong enterprise password (>= 12 chars, not common, not email)
        try:
            validate_password_complexity("KizunooRobot2026!#Valid", email="rep@pipeline-ev.internal")
        except HTTPException:
            self.fail("Valid enterprise password unexpectedly failed complexity check.")

    def test_login_refuses_pending_or_hashless_account(self):
        """Accounts seeded with NULL password_hash and pending_enrollment must be refused on login."""
        mock_acc = {
            "id": "agent-pending-01",
            "email": "pending@pipeline-ev.internal",
            "name": "Pending Agent",
            "role": "agent",
            "password_hash": None,
            "status": "pending_enrollment",
            "failed_login_attempts": 0,
            "locked_until": None,
        }
        with patch.object(main.supabase, "table") as mock_table:
            mock_query = MagicMock()
            mock_table.return_value = mock_query
            mock_query.select.return_value = mock_query
            mock_query.ilike.return_value = mock_query
            mock_query.limit.return_value = mock_query
            mock_query.execute.return_value = MagicMock(data=[mock_acc])

            res = self.client.post("/api/agent/login", json={
                "email": "pending@pipeline-ev.internal",
                "password": "ValidPassword123!#",
            })
            self.assertEqual(res.status_code, 403)
            self.assertIn("pending", res.json()["detail"].lower())

    def test_seed_enroll_login_lifecycle(self):
        """End-to-end seed -> enroll -> login lifecycle test with nullable password_hash."""
        import sys
        from pathlib import Path
        scripts_dir = Path(__file__).resolve().parent.parent.parent / "scripts"
        sys.path.insert(0, str(scripts_dir))
        from seed_agent_accounts import provision_agent

        # 1. Seed provision inserts row with password_hash=None and status='pending_enrollment'
        mock_sb = MagicMock()
        mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
        mock_sb.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[{"id": "new-acc-uuid"}])

        ok = provision_agent(mock_sb, "newrep@pipeline-ev.internal", "New Rep", role="agent")
        self.assertTrue(ok)

        insert_calls = mock_sb.table.return_value.insert.call_args_list
        self.assertTrue(len(insert_calls) > 0)
        inserted_row = insert_calls[0][0][0]
        self.assertIsNone(inserted_row["password_hash"])
        self.assertEqual(inserted_row["status"], "pending_enrollment")

        # 2. Redeem enrollment code via POST /api/agent/enroll
        with patch.object(main.supabase, "table") as mock_app_sb:
            mock_q = MagicMock()
            mock_app_sb.return_value = mock_q
            mock_q.select.return_value = mock_q
            mock_q.eq.return_value = mock_q
            mock_q.limit.return_value = mock_q
            now = datetime.now(timezone.utc)
            mock_q.execute.return_value = MagicMock(data=[{
                "id": "new-acc-uuid",
                "email": "newrep@pipeline-ev.internal",
                "name": "New Rep",
                "role": "agent",
                "status": "pending_enrollment",
                "enrollment_code_expires_at": (now + timedelta(hours=24)).isoformat(),
            }])
            mock_q.update.return_value = mock_q

            res_enroll = self.client.post("/api/agent/enroll", json={
                "enrollment_code": "TESTCODE1234",
                "password": "NewSecretPassword2026!#",
            })
            self.assertEqual(res_enroll.status_code, 200)
            self.assertIn("complete", res_enroll.json()["message"].lower())

            update_call = mock_q.update.call_args[0][0]
            self.assertIsNotNone(update_call.get("password_hash"))
            self.assertEqual(update_call.get("status"), "active")

    def test_duplicate_email_case_insensitive(self):
        """Case-insensitive duplicate emails are rejected at provision time and in SQL index."""
        import sys
        from pathlib import Path
        scripts_dir = Path(__file__).resolve().parent.parent.parent / "scripts"
        sys.path.insert(0, str(scripts_dir))
        from seed_agent_accounts import provision_agent

        mock_sb = MagicMock()
        mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"id": "existing-1", "email": "rep@pipeline-ev.internal", "status": "active"}]
        )
        ok = provision_agent(mock_sb, "REP@PIPELINE-EV.INTERNAL", "Rep Duplicate")
        self.assertFalse(ok)

    def test_trusted_client_ip_forwarding_rate_limiting(self):
        """
        Confirms agent auth rate limiter respects forwarded client IP only when
        accompanied by valid BFF_INTERNAL_SECRET; falls back to socket IP otherwise.
        """
        from portal_auth import get_trusted_client_ip

        # 1. Forwarded IP with VALID secret -> trusted
        req_valid = MagicMock(spec=Request)
        req_valid.headers = {
            "x-forwarded-for": "203.0.113.195, 10.0.0.1",
            "x-bff-internal-secret": os.environ["BFF_INTERNAL_SECRET"],
        }
        req_valid.client = MagicMock(host="127.0.0.1")
        self.assertEqual(get_trusted_client_ip(req_valid), "203.0.113.195")

        # 2. Forwarded IP with INVALID secret -> ignored (falls back to socket IP)
        req_bad_sec = MagicMock(spec=Request)
        req_bad_sec.headers = {
            "x-forwarded-for": "203.0.113.195",
            "x-bff-internal-secret": "forged_invalid_secret_value",
        }
        req_bad_sec.client = MagicMock(host="127.0.0.1")
        self.assertEqual(get_trusted_client_ip(req_bad_sec), "127.0.0.1")

        # 3. Forwarded IP with MISSING secret -> ignored (falls back to socket IP)
        req_no_sec = MagicMock(spec=Request)
        req_no_sec.headers = {"x-forwarded-for": "203.0.113.195"}
        req_no_sec.client = MagicMock(host="127.0.0.1")
        self.assertEqual(get_trusted_client_ip(req_no_sec), "127.0.0.1")

        # 4. Distinct forwarded IPs produce distinct rate limit buckets
        from portal_auth import hash_rate_limit_key
        key1 = hash_rate_limit_key("agent_login_ip", "198.51.100.1")
        key2 = hash_rate_limit_key("agent_login_ip", "198.51.100.2")
        self.assertNotEqual(key1, key2)

    def test_csrf_origin_enforcement_in_fastapi(self):
        """
        Tests FastAPI Origin enforcement for state-changing browser cookie requests:
        - Cookie request with missing Origin -> 403.
        - Cookie request with forged Origin -> 403.
        - Cookie request with allowed localhost Origin in test/dev -> allowed.
        - Bearer auth token without Origin -> allowed.
        """
        # Test route: POST /api/agent/logout (state-changing)
        
        # 1. Missing Origin on cookie-authenticated request -> 403
        res_missing = self.client.post(
            "/api/agent/logout",
            cookies={"agent_session": "test_token"},
            headers={},
        )
        self.assertEqual(res_missing.status_code, 403)
        self.assertIn("missing origin", res_missing.json()["detail"].lower())

        # 2. Forged Origin on cookie-authenticated request -> 403
        res_forged = self.client.post(
            "/api/agent/logout",
            cookies={"agent_session": "test_token"},
            headers={"origin": "https://malicious-attacker-site.com"},
        )
        self.assertEqual(res_forged.status_code, 403)
        self.assertIn("untrusted origin", res_forged.json()["detail"].lower())

        # 3. Allowed localhost Origin in test/dev -> passes CSRF check (200 logout)
        mock_agent = AgentIdentity("a-1", "a@pipeline-ev.internal", "Agent A", "agent", "s-1")
        main.app.dependency_overrides[get_current_agent] = lambda: mock_agent
        try:
            with patch("main.get_current_agent", return_value=mock_agent), patch.object(main.supabase, "table") as mock_table:
                mock_table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
                mock_table.return_value.insert.return_value.execute.return_value = MagicMock(data=[])
                res_allowed = self.client.post(
                    "/api/agent/logout",
                    cookies={"agent_session": "test_token"},
                    headers={"origin": "http://localhost:3000"},
                )
                self.assertEqual(res_allowed.status_code, 200)

                # 4. Bearer token from BFF without Origin -> allowed past CSRF
                res_bearer = self.client.post(
                    "/api/agent/logout",
                    headers={"authorization": "Bearer bff_token_value"},
                )
                self.assertEqual(res_bearer.status_code, 200)
        finally:
            main.app.dependency_overrides.pop(get_current_agent, None)

    def test_admin_account_management_endpoints(self):
        """Admin can suspend, reactivate, and revoke sessions; regular agent is rejected."""
        admin_id = AgentIdentity("admin-acc", "admin@pipeline-ev.internal", "Admin", "admin", "sess-1")
        rep_id = AgentIdentity("rep-acc", "rep@pipeline-ev.internal", "Rep", "agent", "sess-2", agent_id="rep-uuid")

        with patch.object(main.supabase, "table") as mock_table:
            mock_query = MagicMock()
            mock_table.return_value = mock_query
            mock_query.update.return_value = mock_query
            mock_query.eq.return_value = mock_query
            mock_query.is_.return_value = mock_query
            mock_query.execute.return_value = MagicMock(data=[{"id": "target-agent"}])

            # 1. Admin suspends agent
            main.app.dependency_overrides[get_current_agent] = lambda: admin_id
            main.app.dependency_overrides[require_admin] = lambda: admin_id
            try:
                with patch("main.get_current_agent", return_value=admin_id):
                    res = self.client.post(
                        "/api/admin/agents/target-agent/suspend",
                        headers={"origin": "http://localhost:3000"}
                    )
                    self.assertEqual(res.status_code, 200)
                    self.assertIn("suspended", res.json()["message"].lower())

                    # 2. Admin reactivates agent
                    res = self.client.post(
                        "/api/admin/agents/target-agent/reactivate",
                        headers={"origin": "http://localhost:3000"}
                    )
                    self.assertEqual(res.status_code, 200)
                    self.assertIn("reactivated", res.json()["message"].lower())

                    # 3. Admin revokes all sessions
                    res = self.client.post(
                        "/api/admin/agents/target-agent/revoke-all-sessions",
                        headers={"origin": "http://localhost:3000"}
                    )
                    self.assertEqual(res.status_code, 200)
                    self.assertTrue(res.json()["success"])

                # 4. Non-admin rep is forbidden (403)
                main.app.dependency_overrides[get_current_agent] = lambda: rep_id
                main.app.dependency_overrides[require_admin] = lambda: require_admin(rep_id)
                with patch("main.get_current_agent", return_value=rep_id):
                    res = self.client.post(
                        "/api/admin/agents/target-agent/suspend",
                        headers={"origin": "http://localhost:3000"}
                    )
                    self.assertEqual(res.status_code, 403)
            finally:
                main.app.dependency_overrides.pop(get_current_agent, None)
                main.app.dependency_overrides.pop(require_admin, None)

    def test_scoping_enforcement_agent_isolation(self):
        """Agent B must get 403 or 404 on Agent A's client across client mutators and portal panel."""
        from agent_auth import require_client_access

        agent_a = AgentIdentity("acc-a", "a@test.com", "Agent A", "agent", "s-a", agent_id="agent-rep-A")
        agent_b = AgentIdentity("acc-b", "b@test.com", "Agent B", "agent", "s-b", agent_id="agent-rep-B")
        admin = AgentIdentity("admin-1", "admin@test.com", "Admin", "admin", "s-admin", agent_id=None)

        mock_sb = MagicMock()
        mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"id": "client-A", "assigned_agent_id": "agent-rep-A"}]
        )

        with patch.dict(os.environ, {"AGENT_PIPELINE_SCOPING": "assigned"}):
            # Agent A can access
            self.assertIsNone(require_client_access(agent_a, "client-A", mock_sb))
            # Admin can access
            self.assertIsNone(require_client_access(admin, "client-A", mock_sb))
            # Agent B is strictly forbidden (403 or 404)
            with self.assertRaises(HTTPException) as ctx:
                require_client_access(agent_b, "client-A", mock_sb)
            self.assertIn(ctx.exception.status_code, (403, 404))

        # Test endpoint isolation: Agent B calling console portal contacts on Agent A's client
        main.app.dependency_overrides[get_current_agent] = lambda: agent_b
        try:
            with patch("main.get_current_agent", return_value=agent_b), patch.object(main.supabase, "table") as mock_table:
                mock_query = MagicMock()
                mock_table.return_value = mock_query
                mock_query.select.return_value = mock_query
                mock_query.eq.return_value = mock_query
                mock_query.limit.return_value = mock_query
                mock_query.execute.return_value = MagicMock(data=[{"id": "client-A", "assigned_agent_id": "agent-rep-A"}])

                res = self.client.get("/api/console/clients/client-A/portal/contacts")
                self.assertIn(res.status_code, (403, 404))
        finally:
            main.app.dependency_overrides.pop(get_current_agent, None)


if __name__ == "__main__":
    unittest.main()

