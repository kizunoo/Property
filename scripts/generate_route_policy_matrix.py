"""
scripts/generate_route_policy_matrix.py
Generates the authoritative Route Security Policy Matrix dynamically from FastAPI app.routes.
Validates that 100% of /api endpoints have a declared policy.
"""

import sys
from pathlib import Path

# Add backend to Python path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

import main
from route_policies import RoutePolicy, match_policy, ROUTE_POLICY_DECLARATIONS


def collect_app_routes(app):
    """Recursively collects all unique (method, path) pairs from FastAPI app."""
    routes = []
    
    def _recurse(route_list):
        for r in route_list:
            if hasattr(r, "original_router"):
                _recurse(r.original_router.routes)
            elif hasattr(r, "routes"):
                _recurse(r.routes)
            elif hasattr(r, "path") and hasattr(r, "methods"):
                for m in (r.methods or ["GET"]):
                    if m not in ("HEAD", "OPTIONS"):
                        routes.append((m, r.path))
                        
    _recurse(app.routes)
    return sorted(set(routes))


def generate_matrix():
    routes = collect_app_routes(main.app)
    api_routes = [(m, p) for m, p in routes if p.startswith("/api/")]

    rows = []
    missing_policies = []

    for method, path in api_routes:
        decl = match_policy(method, path)
        if not decl:
            missing_policies.append(f"{method} {path}")
            rows.append({
                "method": method,
                "path": path,
                "policy": "UNDECLARED",
                "is_llm": False,
                "description": "POLICY MISSING — SECURITY HAZARD",
            })
        else:
            rows.append({
                "method": method,
                "path": path,
                "policy": decl.policy.value,
                "is_llm": decl.is_llm,
                "description": decl.description,
            })

    output_lines = [
        "# PIPELINE.EV Logic Engine — Route Security Policy Matrix",
        "",
        "> Auto-generated from `backend/main.py:app.routes` by `scripts/generate_route_policy_matrix.py`.",
        "> Every `/api` endpoint is strictly bound to one of five security tiers.",
        "",
        "## Policy Definitions",
        "- **`public`**: Unauthenticated public endpoints (e.g., Meta webhooks, health checks, OTP request/verify, signed calendar `.ics`).",
        "- **`portal-session`**: Authenticated via Client Portal v2 session token (`portal_sessions`).",
        "- **`any-agent`**: Authenticated active agent session token (`agent_sessions`). Scoped to agent's assigned clients where applicable.",
        "- **`client-scoped`**: Authenticated active agent session token. Strictly scoped to agent's assigned client (`404 Not Found` for other agents).",
        "- **`admin-only`**: Requires agent session with `role == 'admin'`. Applied to all global mutators, retraining, and system administration.",
        "- **LLM Rate Limited**: Subject to per-agent sliding-window limiter (10 requests / minute) to prevent model exhaustion.",
        "",
        f"**Total Registered API Endpoints:** {len(api_routes)}  ",
        f"**Undeclared Policies:** {len(missing_policies)}",
        "",
        "| Method | Path | Security Policy | LLM Rate Limit | Purpose / Security Description |",
        "| :--- | :--- | :--- | :---: | :--- |",
    ]

    for r in sorted(rows, key=lambda x: (x["policy"], x["path"], x["method"])):
        llm_badge = "Yes" if r["is_llm"] else "-"
        output_lines.append(f"| `{r['method']}` | `{r['path']}` | **`{r['policy']}`** | {llm_badge} | {r['description']} |")

    content = "\n".join(output_lines) + "\n"

    out_file = Path(__file__).resolve().parent.parent / "docs" / "ROUTE_POLICY_MATRIX.md"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(content, encoding="utf-8")
    print(f"Successfully generated {out_file} with {len(api_routes)} endpoints.")

    if missing_policies:
        print("\nERROR: Found endpoints without declared security policies:")
        for mp in missing_policies:
            print(f"  - {mp}")
        sys.exit(1)
    else:
        print("Verification PASSED: 100% of API endpoints have declared security policies.")


if __name__ == "__main__":
    generate_matrix()
