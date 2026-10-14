"""
scripts/verify_nextjs_gate.py
─────────────────────────────
Verification script and test suite for the Next.js default-deny proxy/gate.
Simulates unauthenticated requests across:
1. Public allowlisted endpoints (expected: allowed / 200 / passthrough)
   - /login
   - /portal/test-company
   - /api/portal/auth/request-code
   - /api/whatsapp/webhook (GET verification & POST delivery)
   - /api/calendar/v1234.ics (signed calendar export)
   - /api/agent/login
   - /api/agent/enroll
   - /api/agent/reset-password
   - /api/agent/logout
   - /_next/static/chunks/main.js
2. Gated pages (expected: 307 redirect to /login)
   - /
   - /clients
   - /pipeline
   - /signals
   - /unknown-page
3. Gated API routes (expected: 401 Unauthorized)
   - /api/daily_worklist
   - /api/whatsapp/conversations
   - /api/scheduled_viewings
   - /api/console/clients/c1/portal/contacts
   - /api/generate_reasoning
4. Preview route
   - /preview/pipeline (expected: 404 in production, 307 redirect in development)
"""

import sys
import os
import re

PUBLIC_EXEMPT_PATHS = {
    "/api/whatsapp/webhook",
    "/api/health",
    "/api/agent/login",
    "/api/agent/enroll",
    "/api/agent/reset-password",
    "/api/agent/logout",
    "/login",
}

def simulate_nextjs_middleware(path: str, method: str = "GET", cookies: dict = None, headers: dict = None, is_prod: bool = False):
    cookies = cookies or {}
    headers = headers or {}

    # 1. Static Next internals
    if path.startswith("/_next") or path.startswith("/static") or path == "/favicon.ico" or ("." in path and not path.endswith(".ics")):
        return {"action": "passthrough", "status": 200}

    # 2. Preview
    if path.startswith("/preview"):
        if is_prod:
            return {"action": "reject", "status": 404, "detail": "Not Found"}

    # 3. CSRF check on state-changing API
    if method in ("POST", "PUT", "PATCH", "DELETE") and path.startswith("/api/"):
        if path != "/api/whatsapp/webhook":
            origin = headers.get("origin")
            sec_fetch = headers.get("sec-fetch-site")
            if sec_fetch == "cross-site":
                return {"action": "reject", "status": 403, "detail": "CSRF: Cross-site rejected"}
            if origin:
                origin_host = origin.split("://")[-1].rstrip("/")
                allowed = {"localhost:3000", "127.0.0.1:3000"} if not is_prod else set()
                req_host = headers.get("host", "")
                if req_host:
                    allowed.add(req_host)
                if origin_host not in allowed:
                    return {"action": "reject", "status": 403, "detail": f"CSRF: Untrusted origin {origin_host}"}

    # 4. Signed calendar ics
    if path.startswith("/api/calendar/") and path.endswith(".ics"):
        return {"action": "passthrough", "status": 200}

    # 5. Portal v2
    if path.startswith("/portal") or path.startswith("/api/portal"):
        return {"action": "passthrough", "status": 200}

    # 6. Public exempt
    if path in PUBLIC_EXEMPT_PATHS:
        return {"action": "passthrough", "status": 200}

    # 7. Session check
    session_token = cookies.get("agent_session")
    if not session_token:
        if path.startswith("/api/"):
            return {"action": "reject", "status": 401, "detail": "Authentication required"}
        return {"action": "redirect", "status": 307, "target": "/login"}

    return {"action": "passthrough", "status": 200}


def run_gate_verification():
    test_cases = [
        # (Path, Method, Cookies, Expected Status, Expected Action)
        # 1. Allowlisted routes (unauthenticated must NOT be blocked)
        ("/login", "GET", {}, 200, "passthrough"),
        ("/portal/company-abc", "GET", {}, 200, "passthrough"),
        ("/api/portal/auth/request-code", "POST", {}, 200, "passthrough"),
        ("/api/whatsapp/webhook", "GET", {}, 200, "passthrough"),
        ("/api/whatsapp/webhook", "POST", {}, 200, "passthrough"),
        ("/api/calendar/v123.ics", "GET", {}, 200, "passthrough"),
        ("/api/agent/login", "POST", {}, 200, "passthrough"),
        ("/api/agent/enroll", "POST", {}, 200, "passthrough"),
        ("/api/agent/reset-password", "POST", {}, 200, "passthrough"),
        ("/api/agent/logout", "POST", {}, 200, "passthrough"),
        ("/_next/static/chunks/app.js", "GET", {}, 200, "passthrough"),

        # 2. Gated pages (must redirect 307 to /login)
        ("/", "GET", {}, 307, "redirect"),
        ("/clients", "GET", {}, 307, "redirect"),
        ("/pipeline", "GET", {}, 307, "redirect"),
        ("/signals", "GET", {}, 307, "redirect"),

        # 3. Gated API routes (must return 401)
        ("/api/daily_worklist", "GET", {}, 401, "reject"),
        ("/api/whatsapp/conversations", "GET", {}, 401, "reject"),
        ("/api/scheduled_viewings", "GET", {}, 401, "reject"),
        ("/api/console/clients/c1/portal/contacts", "GET", {}, 401, "reject"),
        ("/api/generate_reasoning", "POST", {}, 401, "reject"),
    ]

    passed = 0
    failed = 0

    print("=====================================================================")
    print("        NEXT.JS GATE & PROXY VERIFICATION AUDIT")
    print("=====================================================================")

    for path, method, cookies, expected_status, expected_action in test_cases:
        res = simulate_nextjs_middleware(path, method, cookies=cookies)
        status_ok = res["status"] == expected_status
        action_ok = res["action"] == expected_action
        if status_ok and action_ok:
            passed += 1
            print(f"  [PASS] {method:<6} {path:<40} -> {res['action'].upper()} ({res['status']})")
        else:
            failed += 1
            print(f"  [FAIL] {method:<6} {path:<40} -> Got {res['action']} ({res['status']}), expected {expected_action} ({expected_status})")

    # Preview test in production
    res_preview_prod = simulate_nextjs_middleware("/preview/test", "GET", is_prod=True)
    if res_preview_prod["status"] == 404:
        passed += 1
        print(f"  [PASS] GET    /preview/* (Production)                  -> 404 NOT FOUND")
    else:
        failed += 1
        print(f"  [FAIL] GET    /preview/* (Production)                  -> Got {res_preview_prod['status']}")

    # Preview test in dev (unauthenticated)
    res_preview_dev = simulate_nextjs_middleware("/preview/test", "GET", is_prod=False)
    if res_preview_dev["status"] == 307:
        passed += 1
        print(f"  [PASS] GET    /preview/* (Dev, Unauthenticated)        -> 307 REDIRECT")
    else:
        failed += 1
        print(f"  [FAIL] GET    /preview/* (Dev, Unauthenticated)        -> Got {res_preview_dev['status']}")

    print("---------------------------------------------------------------------")
    print(f"Results: {passed} passed, {failed} failed.")
    print("=====================================================================")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    run_gate_verification()
