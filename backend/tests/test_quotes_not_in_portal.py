"""backend/tests/test_quotes_not_in_portal.py

Verifies portal isolation:
1. No quote terms or agent activity leak into app/portal/ or components/portal/.
2. /api/portal backend endpoints do not reference supplier_quote, agent_activity, or quote_logic.
3. Every quote route enforces agent authentication identically to the inquiry router.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import types
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_no_quote_terms_in_portal_frontend():
    forbidden_terms = ["supplier_quote", "lib/quotes", "quote_routes", "agent_activity"]
    portal_dirs = [
        REPO_ROOT / "app" / "portal",
        REPO_ROOT / "components" / "portal",
    ]

    violations = []
    for pdir in portal_dirs:
        if not pdir.exists():
            continue
        for root, _, files in os.walk(pdir):
            for file in files:
                if file.endswith((".ts", ".tsx", ".js", ".jsx", ".json")):
                    filepath = Path(root) / file
                    content = filepath.read_text(encoding="utf-8", errors="ignore")
                    for term in forbidden_terms:
                        if term in content:
                            violations.append(f"{filepath}: contains '{term}'")

    assert not violations, f"Portal frontend contains forbidden quote references:\n" + "\n".join(violations)


def test_no_quote_logic_in_portal_backend_routes():
    main_py = REPO_ROOT / "backend" / "main.py"
    content = main_py.read_text(encoding="utf-8")

    # Inspect all route definitions serving /api/portal
    forbidden_terms = ["supplier_quote", "agent_activity", "quote_logic"]
    portal_blocks = re.findall(
        r"@app\.(?:get|post|put|patch|delete)\([\"']/api/portal[^\"]*[\"'].*?\)\s*(?:async\s+)?def\s+([a-zA-Z0-9_]+)\s*\(.*?\):(?:\n(?:[ \t]+.*|\s*))*",
        content,
    )

    violations = []
    for m in re.finditer(
        r"@app\.(?:get|post|put|patch|delete)\([\"']/api/portal.*?\)\s*(?:async\s+)?def\s+([a-zA-Z0-9_]+)",
        content,
    ):
        func_name = m.group(1)
        # Find function body in text
        start_idx = m.start()
        end_idx = content.find("\n@app.", start_idx + 1)
        body = content[start_idx:end_idx] if end_idx != -1 else content[start_idx:]
        for term in forbidden_terms:
            if term in body:
                violations.append(f"Function {func_name} contains '{term}'")

    assert not violations, f"Portal routes in main.py reference quote logic:\n" + "\n".join(violations)


def test_quote_routes_enforce_agent_auth():
    import sys
    sys.path.insert(0, str(REPO_ROOT / "backend"))
    import quote_routes
    import inquiry_actions_routes

    app = FastAPI()
    app.include_router(quote_routes.router)
    app.include_router(inquiry_actions_routes.router)

    client = TestClient(app, raise_server_exceptions=False)

    # Every quote route without agent header must return 401
    quote_endpoints = [
        ("GET", "/api/quotes", None),
        ("POST", "/api/quotes/request", {"client_id": "c1", "property_id": "p1", "market_price_myr": 100000.0, "kind": "quote"}),
        ("POST", "/api/quotes/test-id/approve", {}),
        ("POST", "/api/quotes/test-id/cancel", None),
        ("POST", "/api/quotes/test-id/publish-to-portal", {}),
        ("POST", "/api/quotes/log", {"kind": "expiry_dismissed", "ref_id": "q1", "summary": "test"}),
    ]

    for method, path, payload in quote_endpoints:
        if method == "GET":
            res = client.get(path)
        else:
            res = client.post(path, json=payload if payload is not None else {})
        assert res.status_code == 401, f"Route {method} {path} did not reject unauthenticated request with 401 (got {res.status_code})"
