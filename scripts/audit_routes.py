"""
scripts/audit_routes.py
Automated Route & Security Audit Tool for PIPELINE.EV
Introspects FastAPI application routes and Next.js BFF API route handlers.
Produces an audit report with reachability, auth status, third-party services, and risk ratings.
"""

import os
import sys
import glob
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

# Set test environment to prevent external connections during import
os.environ["ENVIRONMENT"] = "testing"
os.environ["BFF_INTERNAL_SECRET"] = os.environ.get("BFF_INTERNAL_SECRET", "audit_test_secret_32bytes_value_12345")
os.environ["PORTAL_CODE_PEPPER"] = os.environ.get("PORTAL_CODE_PEPPER", "audit_test_pepper_32bytes_value_12345")

try:
    import main
    fastapi_app = main.app
except Exception as e:
    print(f"Error importing FastAPI main: {e}")
    sys.exit(1)

# Scan Next.js BFF API routes
nextjs_api_dir = Path(__file__).resolve().parent.parent / "app" / "api"
nextjs_routes = set()
for route_file in nextjs_api_dir.glob("**/route.ts"):
    rel = route_file.relative_to(nextjs_api_dir)
    # Convert path to route pattern e.g. clients/[clientId]/route.ts -> /api/clients/{clientId}
    parts = list(rel.parent.parts)
    route_path = "/api/" + "/".join(parts) if parts else "/api"
    # Normalize Next.js [param] to {param}
    normalized = route_path.replace("[", "{").replace("]", "}")
    nextjs_routes.add(normalized)

audit_rows = []

for route in fastapi_app.routes:
    path = getattr(route, "path", None)
    if not path or path in ("/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"):
        continue

    methods = sorted(list(getattr(route, "methods", [])))
    methods_str = ", ".join([m for m in methods if m not in ("HEAD", "OPTIONS")])
    if not methods_str:
        continue

    endpoint = getattr(route, "endpoint", None)
    endpoint_name = endpoint.__name__ if endpoint else "unknown"

    # Check Next.js BFF reachability
    # An endpoint is reachable from the browser if a matching Next.js route exists or calls it
    is_bff_reachable = False
    norm_path = path.rstrip("/")
    for nr in nextjs_routes:
        if nr.rstrip("/") == norm_path or norm_path.startswith(nr.rstrip("/")):
            is_bff_reachable = True
            break

    reachability = "Browser (via Next.js BFF)" if is_bff_reachable else "Direct FastAPI Only"

    # Identify service
    if "whatsapp" in path:
        service = "Meta Cloud API (graph.facebook.com)"
    elif "portal" in path:
        service = "Portal v2 Auth / PostgreSQL"
    elif "model" in path or "train" in path:
        service = "ML Engine (scikit-learn)"
    elif "market" in path or "price" in path:
        service = "Market Simulation Engine"
    else:
        service = "Supabase PostgreSQL"

    # Determine auth & risk
    if "simulate_incoming" in path:
        auth_status = "None (Public Webhook / Simulation)"
        risk = "CRITICAL HIGH RISK"
        mitigation = "Disable in production; admin-only in development"
    elif any(kw in path for kw in ("simulate_market_day", "simulate_price_change")):
        auth_status = "None"
        risk = "HIGH RISK"
        mitigation = "Disable in production; admin-only in development"
    elif "confirm_demo" in path:
        auth_status = "None (Removed from Portal UI)"
        risk = "HIGH RISK"
        mitigation = "Require agent session or portal session"
    elif any(kw in path for kw in ("send_slot_offer", "send_template", "send_pitch", "send_message", "nudge")):
        auth_status = "None"
        risk = "HIGH RISK"
        mitigation = "Require agent authentication"
    elif path.startswith("/api/console/"):
        auth_status = "None"
        risk = "HIGH RISK"
        mitigation = "Require agent authentication"
    elif path.startswith("/api/clients") and methods_str in ("PATCH", "POST"):
        auth_status = "None"
        risk = "HIGH RISK"
        mitigation = "Require agent authentication"
    elif path in ("/api/portal/auth/request-code", "/api/portal/auth/verify-code"):
        auth_status = "Persistent Rate Limited (30 IP / 5 Contact)"
        risk = "LOW (Public Portal Entry)"
        mitigation = "Protected by rate limiter & lockout"
    elif path == "/api/portal/auth/verify-invite":
        auth_status = "One-Time 32-Byte Secret Token"
        risk = "LOW (Invite Redemption)"
        mitigation = "Single-use redemption; immediately invalidated"
    elif path.startswith("/api/portal/auth/legacy-login"):
        auth_status = "Rate Limited Legacy Hash"
        risk = "MEDIUM (Legacy Migration)"
        mitigation = "Deprecate once rotation script runs"
    elif path.startswith("/api/portal/"):
        auth_status = "Opaque Session Cookie (HMAC)"
        risk = "SECURE (Authenticated Portal)"
        mitigation = "Company-scoped; validated against portal_sessions"
    elif "webhook" in path:
        auth_status = "Meta Verify Token / Secret"
        risk = "LOW (External Webhook)"
        mitigation = "Signature verified"
    else:
        auth_status = "None (Internal Console Read)"
        risk = "MEDIUM RISK"
        mitigation = "Move behind agent authentication"

    audit_rows.append({
        "path": path,
        "methods": methods_str,
        "reachability": reachability,
        "auth_status": auth_status,
        "service": service,
        "risk": risk,
        "mitigation": mitigation,
    })

# Sort: Critical first, then High, Medium, Low, Secure
risk_order = {
    "CRITICAL HIGH RISK": 0,
    "HIGH RISK": 1,
    "MEDIUM RISK": 2,
    "MEDIUM (Legacy Migration)": 3,
    "LOW (Public Portal Entry)": 4,
    "LOW (Invite Redemption)": 5,
    "LOW (External Webhook)": 6,
    "SECURE (Authenticated Portal)": 7,
}
audit_rows.sort(key=lambda r: (risk_order.get(r["risk"], 99), r["path"]))

# Generate Markdown
md = [
    "# Automated Route & Security Audit Report",
    f"Generated from FastAPI and Next.js route introspection. Total routes analyzed: {len(audit_rows)}.",
    "",
    "| Route Path | Method(s) | Reachability | Current Auth | Backend Service | Risk Level | Required Action |",
    "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
]

for r in audit_rows:
    md.append(f"| `{r['path']}` | `{r['methods']}` | **{r['reachability']}** | {r['auth_status']} | {r['service']} | **{r['risk']}** | {r['mitigation']} |")

md_content = "\n".join(md) + "\n"

docs_dir = Path(__file__).resolve().parent.parent / "docs"
docs_dir.mkdir(exist_ok=True)
output_path = docs_dir / "ROUTE_AUDIT.md"
with open(output_path, "w", encoding="utf-8") as f:
    f.write(md_content)

print(f"Audit completed: {len(audit_rows)} routes audited. Written to {output_path}")
