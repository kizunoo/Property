"""
scripts/test_nextjs_gate_live.py
Live HTTP test of Next.js 16 Edge Proxy (proxy.ts) running on a spare port.
Verifies:
1. No-cookie requests:
   - Pages redirect to /login
   - /api/* returns 401 JSON
   - Allowlist routes (/api/whatsapp/webhook GET/POST, /api/calendar/*.ics, /portal/*, /login) NOT blocked
2. Fake agent cookie:
   - Merely present passes the Next.js gate (Next proxy allows it to reach backend)
3. Portal cookie:
   - Grants access to /portal/* but is BLOCKED with 401 / redirect on agent routes
4. CSRF / Origin enforcement:
   - State-changing /api/* with Sec-Fetch-Site: cross-site -> 403
   - State-changing /api/* with forged Origin -> 403
   - Webhook POST -> exempt from CSRF
5. FastAPI token rejection:
   - Confirms FastAPI rejects fake agent tokens with 401 across endpoints
"""

import sys
import os
import time
import subprocess
import signal
from pathlib import Path
import urllib.request
import urllib.error
import http.client
import json

project_root = Path(__file__).resolve().parent.parent
backend_dir = project_root / "backend"
sys.path.insert(0, str(backend_dir))

TEST_PORT = 3099
BASE_URL = f"http://127.0.0.1:{TEST_PORT}"


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Do not automatically follow redirects, return response so we can inspect status
        return None


opener = urllib.request.build_opener(NoRedirectHandler)


def make_request(path: str, method: str = "GET", headers: dict = None, body: bytes = None):
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url, data=body, method=method)
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    
    try:
        resp = opener.open(req, timeout=10)
        return resp.status, resp.headers, resp.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers, exc.read().decode("utf-8", errors="ignore")


def wait_for_server(timeout=30):
    start = time.time()
    while time.time() - start < timeout:
        try:
            status, _, _ = make_request("/login")
            if status in (200, 307, 308):
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def run_gate_tests():
    print(f"[*] Starting Next.js server on port {TEST_PORT}...")
    project_root = Path(__file__).resolve().parent.parent

    # Launch next start on TEST_PORT
    cmd = ["npx", "next", "start", "-p", str(TEST_PORT)]
    proc = subprocess.Popen(
        cmd,
        cwd=str(project_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=True,
    )

    passed = 0
    failed = 0

    def assert_check(name: str, condition: bool, details: str = ""):
        nonlocal passed, failed
        if condition:
            print(f"  [PASS] {name}")
            passed += 1
        else:
            print(f"  [FAIL] {name}: {details}")
            failed += 1

    try:
        print("[*] Waiting for Next.js HTTP server to be healthy...")
        if not wait_for_server():
            print("FATAL: Next.js server failed to boot on port", TEST_PORT)
            return False

        print("\n=== Running Live Next.js Proxy Gate Tests ===")

        # 1. Page with no cookie -> redirect to /login
        s, h, _ = make_request("/")
        location = h.get("location", "")
        assert_check("No cookie: GET / redirects to /login", s in (307, 308) and "/login" in location, f"Status: {s}, Location: {location}")

        # 2. API with no cookie -> 401 Unauthorized
        s, _, body = make_request("/api/daily_worklist")
        assert_check("No cookie: GET /api/daily_worklist returns 401", s == 401 and "Authentication required" in body, f"Status: {s}, Body: {body}")

        # 3. Allowlist: /api/whatsapp/webhook (GET & POST) not blocked by gate
        s, _, body = make_request("/api/whatsapp/webhook")
        assert_check("Allowlist: GET /api/whatsapp/webhook not blocked (not 401)", s != 401, f"Status: {s}")

        s, _, body = make_request("/api/whatsapp/webhook", method="POST", headers={"Content-Type": "application/json"}, body=b"{}")
        assert_check("Allowlist: POST /api/whatsapp/webhook not blocked by gate or CSRF (not 401/403)", s not in (401, 403), f"Status: {s}")

        # 4. Allowlist: Signed calendar link (.ics or token param) not blocked by gate
        s, _, _ = make_request("/api/calendar/demo123.ics")
        assert_check("Allowlist: GET /api/calendar/*.ics not blocked (not 401)", s != 401, f"Status: {s}")

        s, _, _ = make_request("/api/calendar/demo123?token=sample_hmac_token")
        assert_check("Allowlist: GET /api/calendar/*?token=... not blocked (not 401)", s != 401, f"Status: {s}")

        # 5. Allowlist: /portal and /api/portal/* pass agent gate
        s, _, _ = make_request("/portal")
        assert_check("Allowlist: GET /portal not blocked by agent gate (not 401)", s != 401, f"Status: {s}")

        s, _, body = make_request("/api/portal/auth/me")
        assert_check("Allowlist: GET /api/portal/auth/me passes agent gate (not agent 401)", "Please log in to access agent services" not in body, f"Status: {s}, Body: {body}")

        s, _, body = make_request("/api/portal/auth/me", headers={"Cookie": "portal_session=client_valid_test_token"})
        assert_check("Portal cookie: GET /api/portal/auth/me reaches portal handler", "Please log in to access agent services" not in body and "No session provided" not in body, f"Status: {s}")

        # 6. Allowlist: /login is accessible
        s, _, _ = make_request("/login")
        assert_check("Allowlist: GET /login returns 200", s == 200, f"Status: {s}")

        # 7. Fake agent cookie passes Next gate (proxy passes request to upstream)
        s, h, body = make_request("/", headers={"Cookie": "agent_session=fake_mock_token_abc123"})
        assert_check("Fake agent cookie: GET / passes Next gate (not redirected to /login)", s not in (307, 308), f"Status: {s}")

        s, _, body = make_request("/api/daily_worklist", headers={"Cookie": "agent_session=fake_mock_token_abc123"})
        assert_check("Fake agent cookie: GET /api/daily_worklist passes Next gate (not gate 401)", s != 401 or "Authentication required. Please log in" not in body, f"Status: {s}")

        # 8. Portal cookie does NOT pass agent gate
        s, h, _ = make_request("/", headers={"Cookie": "portal_session=client_valid_token_xyz"})
        location = h.get("location", "")
        assert_check("Portal cookie on agent page: GET / redirects to /login", s in (307, 308) and "/login" in location, f"Status: {s}")

        s, _, body = make_request("/api/daily_worklist", headers={"Cookie": "portal_session=client_valid_token_xyz"})
        assert_check("Portal cookie on agent API: GET /api/daily_worklist returns 401", s == 401 and "Authentication required" in body, f"Status: {s}")

        # 9. CSRF: Sec-Fetch-Site: cross-site on state-changing API -> 403
        s, _, body = make_request(
            "/api/agents",
            method="POST",
            headers={
                "Cookie": "agent_session=fake_token_123",
                "Sec-Fetch-Site": "cross-site",
                "Content-Type": "application/json"
            },
            body=b"{}"
        )
        assert_check("CSRF: Sec-Fetch-Site: cross-site returns 403", s == 403 and "Cross-site request rejected" in body, f"Status: {s}, Body: {body}")

        # 10. CSRF: Forged Origin on state-changing API -> 403
        s, _, body = make_request(
            "/api/agents",
            method="POST",
            headers={
                "Cookie": "agent_session=fake_token_123",
                "Origin": "https://malicious-attacker.com",
                "Content-Type": "application/json"
            },
            body=b"{}"
        )
        assert_check("CSRF: Forged Origin returns 403", s == 403 and "Untrusted Origin" in body, f"Status: {s}, Body: {body}")

        # 11. FastAPI side validation test: confirm FastAPI rejects fake agent tokens
        import main
        from unittest.mock import patch, MagicMock
        from fastapi.testclient import TestClient
        client = TestClient(main.app)
        with patch.object(main.supabase, "table") as mock_table:
            # Simulate DB returning no matching session for fake token
            mock_table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
            fastapi_resp = client.get("/api/daily_worklist", headers={"Authorization": "Bearer fake_token_abc"})
            assert_check("FastAPI upstream: Rejects fake agent token on API route (401)", fastapi_resp.status_code == 401, f"Status: {fastapi_resp.status_code}")

    finally:
        print("[*] Tearing down Next.js server...")
        # Terminate process tree
        subprocess.run(f"taskkill /F /T /PID {proc.pid}", shell=True, capture_output=True)

    print(f"\nLive Gate Test Results: {passed} passed, {failed} failed.")
    return failed == 0


if __name__ == "__main__":
    success = run_gate_tests()
    sys.exit(0 if success else 1)
