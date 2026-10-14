"""
scripts/update_bff_routes.py
Updates the 43 agent BFF routes to import buildAgentUpstreamHeaders from '@/lib/agent-bff-auth'
and pass headers to all fetch() calls to FastAPI.
"""

import os
import re

AGENT_ROUTES = [
    "app/api/agents/route.ts",
    "app/api/cancel_viewing/[id]/route.ts",
    "app/api/chart_insight/route.ts",
    "app/api/clients/[clientId]/advance_stage/route.ts",
    "app/api/clients/[clientId]/purchases/route.ts",
    "app/api/clients/[clientId]/route.ts",
    "app/api/complete_viewing/[id]/route.ts",
    "app/api/confirm_demo/[viewingId]/route.ts",
    "app/api/daily_worklist/route.ts",
    "app/api/dashboard_briefing/route.ts",
    "app/api/insight/route.ts",
    "app/api/invite/mark_sent/route.ts",
    "app/api/invite/route.ts",
    "app/api/log_viewing/route.ts",
    "app/api/market_movements/route.ts",
    "app/api/model_status/route.ts",
    "app/api/pipeline_projection/route.ts",
    "app/api/prediction_accuracy/route.ts",
    "app/api/properties/[propertyId]/route.ts",
    "app/api/property_price_history/[propertyId]/route.ts",
    "app/api/re-evaluate/route.ts",
    "app/api/reasoning/route.ts",
    "app/api/record_outcome/route.ts",
    "app/api/retrain_model/route.ts",
    "app/api/schedule_viewing/route.ts",
    "app/api/scheduled_viewings/route.ts",
    "app/api/shortlist/[propertyId]/route.ts",
    "app/api/signals/[id]/dismiss/route.ts",
    "app/api/signals/route.ts",
    "app/api/simulate_market_day/route.ts",
    "app/api/simulate_price_change/[propertyId]/route.ts",
    "app/api/whatsapp/clear_opt_out/route.ts",
    "app/api/whatsapp/conversations/[conversationId]/read/route.ts",
    "app/api/whatsapp/conversations/route.ts",
    "app/api/whatsapp/messages/route.ts",
    "app/api/whatsapp/nudge/route.ts",
    "app/api/whatsapp/resume_automation/route.ts",
    "app/api/whatsapp/send/route.ts",
    "app/api/whatsapp/send_message/route.ts",
    "app/api/whatsapp/send_pitch/route.ts",
    "app/api/whatsapp/simulate_incoming/route.ts",
    "app/api/whatsapp/suggest_reply/route.ts",
    "app/api/whatsapp/window_status/route.ts",
]

def update_file(path):
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Ensure buildAgentUpstreamHeaders is imported
    if "buildAgentUpstreamHeaders" not in content:
        import_stmt = 'import { buildAgentUpstreamHeaders } from "@/lib/agent-bff-auth"\n'
        content = import_stmt + content

    # 2. Ensure exported route functions accept req
    # Match export async function GET() -> export async function GET(req: Request)
    for method in ["GET", "POST", "PUT", "PATCH", "DELETE"]:
        content = re.sub(
            rf"export\s+async\s+function\s+{method}\s*\(\s*\)",
            f"export async function {method}(req: Request)",
            content
        )

    # 3. In fetch calls, ensure headers are passed
    # Pattern A: headers: { "Content-Type": "application/json" } -> headers: buildAgentUpstreamHeaders(req)
    content = re.sub(
        r'headers:\s*\{\s*["\']Content-Type["\']:\s*["\']application/json["\']\s*\}',
        r'headers: buildAgentUpstreamHeaders(req)',
        content
    )

    # Pattern B: fetch(url, { cache: "no-store" }) -> fetch(url, { cache: "no-store", headers: buildAgentUpstreamHeaders(req) })
    content = re.sub(
        r'fetch\(([^,]+),\s*\{\s*cache:\s*["\']no-store["\']\s*\}\)',
        r'fetch(\1, { cache: "no-store", headers: buildAgentUpstreamHeaders(req) })',
        content
    )

    # Pattern C: fetch(url, { method: "POST" }) -> fetch(url, { method: "POST", headers: buildAgentUpstreamHeaders(req) })
    content = re.sub(
        r'fetch\(([^,]+),\s*\{\s*method:\s*["\'](POST|PUT|PATCH|DELETE)["\']\s*\}\)',
        r'fetch(\1, { method: "\2", headers: buildAgentUpstreamHeaders(req) })',
        content
    )

    # Pattern D: fetch(`${FASTAPI_URL}...`) with no options -> fetch(..., { headers: buildAgentUpstreamHeaders(req) })
    # Match fetch(url) where url doesn't have options argument
    # Be careful not to match fetch(..., { ... })
    content = re.sub(
        r'fetch\((`\$\{(?:FASTAPI_URL|BACKEND_URL)\}[^`]*`)\)',
        r'fetch(\1, { headers: buildAgentUpstreamHeaders(req) })',
        content
    )
    content = re.sub(
        r'fetch\(((?:backendUrl|url|upstreamUrl)(?:\.toString\(\))?)\)',
        r'fetch(\1, { headers: buildAgentUpstreamHeaders(req) })',
        content
    )

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

for p in AGENT_ROUTES:
    if os.path.exists(p):
        update_file(p)
        print(f"Updated: {p}")
    else:
        print(f"NOT FOUND: {p}")
