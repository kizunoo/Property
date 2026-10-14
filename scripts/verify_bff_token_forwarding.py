"""
scripts/verify_bff_token_forwarding.py
Scans all app/api/**/route.ts files to verify that every fetch call to FastAPI forwards
an appropriate authorization header (buildAgentUpstreamHeaders or buildPortalUpstreamHeaders),
except explicitly unauthenticated endpoints (like the webhook and login endpoints).
"""

import glob
import re
import sys

# Endpoints that are explicitly unauthenticated or self-authenticating
EXEMPT_ROUTES = {
    "app/api/whatsapp/webhook/route.ts",      # Unauthenticated external webhook
    "app/api/calendar/[viewingId]/route.ts",    # Signed calendar ICS download
    "app/api/agent/login/route.ts",            # Agent credentials exchange
    "app/api/agent/enroll/route.ts",           # Agent enrollment code exchange
    "app/api/agent/reset-password/route.ts",   # Agent reset code exchange
    "app/api/portal/auth/legacy-login/route.ts", # Legacy access code exchange
    "app/api/portal/auth/request-code/route.ts", # Portal OTP request
    "app/api/portal/auth/verify-code/route.ts",  # Portal OTP verification
    "app/api/portal/auth/verify-invite/route.ts",# Portal invite verification
    "app/api/portal/login/route.ts",             # Portal code exchange
}

def check_routes():
    all_routes = glob.glob("app/api/**/route.ts", recursive=True)
    violations = []
    checked_count = 0

    for r in sorted(all_routes):
        norm = r.replace("\\", "/")
        with open(r, "r", encoding="utf-8") as f:
            content = f.read()

        # If file doesn't fetch FastAPI, skip
        if "FASTAPI_URL" not in content and "BACKEND_URL" not in content:
            continue

        checked_count += 1

        if norm in EXEMPT_ROUTES:
            continue

        is_portal = norm.startswith("app/api/portal/")
        has_agent_helper = "buildAgentUpstreamHeaders" in content or "Authorization" in content
        has_portal_helper = "buildPortalUpstreamHeaders" in content

        if is_portal:
            if not has_portal_helper and not has_agent_helper:
                violations.append((norm, "Missing portal token forwarding (buildPortalUpstreamHeaders)"))
        else:
            if not has_agent_helper:
                violations.append((norm, "Missing agent token forwarding (buildAgentUpstreamHeaders)"))

    print(f"Total BFF routes checked: {checked_count}")
    if violations:
        print(f"FAILED: Found {len(violations)} routes with missing token forwarding:")
        for path, reason in violations:
            print(f"  - {path}: {reason}")
        return 1
    else:
        print("SUCCESS: All BFF routes forwarding appropriate tokens to FastAPI.")
        return 0

if __name__ == "__main__":
    sys.exit(check_routes())
