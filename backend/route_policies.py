"""
route_policies.py
Central route security policy registry and enforcement for PIPELINE.EV Logic Engine.

Every /api endpoint MUST declare exactly one policy:
- public: No authentication required (webhooks, health, public auth endpoints, signed calendar .ics)
- portal-session: Authenticated via Client Portal v2 session token (portal_sessions)
- any-agent: Authenticated via Agent session token (agent_sessions); accessible to any active agent
- client-scoped: Authenticated via Agent session token; strictly scoped to the agent's assigned client (returns 404 for other agents)
- admin-only: Authenticated via Agent session token; requires agent.role == 'admin' (global mutations, model retraining, user management)

Also specifies LLM routes subject to per-agent rate limits.
"""

from dataclasses import dataclass
from enum import Enum
import re
from typing import Dict, List, Optional, Tuple, Any
from fastapi import Request, HTTPException


class RoutePolicy(str, Enum):
    PUBLIC = "public"
    PORTAL_SESSION = "portal-session"
    ANY_AGENT = "any-agent"
    CLIENT_SCOPED = "client-scoped"
    ADMIN_ONLY = "admin-only"


@dataclass(frozen=True)
class RoutePolicyDecl:
    method: str
    pattern: str
    regex: re.Pattern
    policy: RoutePolicy
    is_llm: bool = False
    description: str = ""


# Master Route Policy Declarations
# Ordered from most specific regex to least specific
ROUTE_POLICY_DECLARATIONS: List[RoutePolicyDecl] = [
    # ─── 1. PUBLIC ROUTES ────────────────────────────────────────────────────
    RoutePolicyDecl("GET", "/api/health", re.compile(r"^/api/health$"), RoutePolicy.PUBLIC, False, "Health check probe"),
    RoutePolicyDecl("GET", "/api/calendar/{viewing_id}.ics", re.compile(r"^/api/calendar/[^/]+\.ics$"), RoutePolicy.PUBLIC, False, "Signed calendar invite subscription"),
    RoutePolicyDecl("GET", "/api/calendar/{viewing_id}", re.compile(r"^/api/calendar/[^/.]+$"), RoutePolicy.PUBLIC, False, "Signed calendar invite subscription (without .ics extension)"),
    RoutePolicyDecl("GET", "/api/whatsapp/webhook", re.compile(r"^/api/whatsapp/webhook$"), RoutePolicy.PUBLIC, False, "WhatsApp Meta webhook challenge verification"),
    RoutePolicyDecl("POST", "/api/whatsapp/webhook", re.compile(r"^/api/whatsapp/webhook$"), RoutePolicy.PUBLIC, False, "WhatsApp Meta signed incoming events"),
    RoutePolicyDecl("POST", "/api/agent/login", re.compile(r"^/api/agent/login$"), RoutePolicy.PUBLIC, False, "Agent credential authentication"),
    RoutePolicyDecl("POST", "/api/agent/enroll", re.compile(r"^/api/agent/enroll$"), RoutePolicy.PUBLIC, False, "Agent one-time code enrollment"),
    RoutePolicyDecl("POST", "/api/agent/reset-password", re.compile(r"^/api/agent/reset-password$"), RoutePolicy.PUBLIC, False, "Agent password reset execution"),
    RoutePolicyDecl("POST", "/api/portal/auth/request-code", re.compile(r"^/api/portal/auth/request-code$"), RoutePolicy.PUBLIC, False, "Portal OTP SMS/WA request"),
    RoutePolicyDecl("POST", "/api/portal/auth/verify-code", re.compile(r"^/api/portal/auth/verify-code$"), RoutePolicy.PUBLIC, False, "Portal OTP verification"),
    RoutePolicyDecl("POST", "/api/portal/auth/verify-invite", re.compile(r"^/api/portal/auth/verify-invite$"), RoutePolicy.PUBLIC, False, "Portal invite token validation"),
    RoutePolicyDecl("POST", "/api/portal/auth/legacy-login", re.compile(r"^/api/portal/auth/legacy-login$"), RoutePolicy.PUBLIC, False, "Portal legacy access code authentication"),
    RoutePolicyDecl("POST", "/api/portal/login", re.compile(r"^/api/portal/login$"), RoutePolicy.PUBLIC, False, "Portal legacy login endpoint"),

    # ─── 2. PORTAL SESSION ROUTES ────────────────────────────────────────────
    RoutePolicyDecl("POST", "/api/portal/auth/logout", re.compile(r"^/api/portal/auth/logout$"), RoutePolicy.PORTAL_SESSION, False, "Portal session logout"),
    RoutePolicyDecl("GET", "/api/portal/auth/me", re.compile(r"^/api/portal/auth/me$"), RoutePolicy.PORTAL_SESSION, False, "Portal current session identity"),
    RoutePolicyDecl("GET", "/api/portal/{client_id}/activity", re.compile(r"^/api/portal/[^/]+/activity$"), RoutePolicy.PORTAL_SESSION, False, "Portal client activity stream"),
    RoutePolicyDecl("GET", "/api/portal/{client_id}/catalog", re.compile(r"^/api/portal/[^/]+/catalog$"), RoutePolicy.PORTAL_SESSION, False, "Portal client property catalog"),
    RoutePolicyDecl("PUT", "/api/portal/{client_id}/catalog/{property_id}/feedback", re.compile(r"^/api/portal/[^/]+/catalog/[^/]+/feedback$"), RoutePolicy.PORTAL_SESSION, False, "Portal client unit feedback"),
    RoutePolicyDecl("GET", "/api/portal/{client_id}/dashboard", re.compile(r"^/api/portal/[^/]+/dashboard$"), RoutePolicy.PORTAL_SESSION, False, "Portal client dashboard stats"),
    RoutePolicyDecl("GET", "/api/portal/{client_id}/inquiries", re.compile(r"^/api/portal/[^/]+/inquiries$"), RoutePolicy.PORTAL_SESSION, False, "Portal client inquiries list"),
    RoutePolicyDecl("POST", "/api/portal/{client_id}/inquiry", re.compile(r"^/api/portal/[^/]+/inquiry$"), RoutePolicy.PORTAL_SESSION, False, "Portal client submit inquiry"),
    RoutePolicyDecl("POST", "/api/portal/{client_id}/inquiries/{inquiry_id}/messages", re.compile(r"^/api/portal/[^/]+/inquiries/[^/]+/messages$"), RoutePolicy.PORTAL_SESSION, False, "Portal client submit inquiry message"),
    RoutePolicyDecl("POST", "/api/portal/{client_id}/inquiries/{inquiry_id}/read", re.compile(r"^/api/portal/[^/]+/inquiries/[^/]+/read$"), RoutePolicy.PORTAL_SESSION, False, "Portal client mark inquiry messages read"),
    RoutePolicyDecl("GET", "/api/portal/{client_id}/quotes", re.compile(r"^/api/portal/[^/]+/quotes$"), RoutePolicy.PORTAL_SESSION, False, "Portal client quotes list"),
    RoutePolicyDecl("POST", "/api/portal/{client_id}/quotes", re.compile(r"^/api/portal/[^/]+/quotes$"), RoutePolicy.PORTAL_SESSION, False, "Portal client request quote"),
    RoutePolicyDecl("POST", "/api/portal/{client_id}/quotes/{quote_id}/respond", re.compile(r"^/api/portal/[^/]+/quotes/[^/]+/respond$"), RoutePolicy.PORTAL_SESSION, False, "Portal client respond to quote"),
    RoutePolicyDecl("GET", "/api/portal/{client_id}/my_viewings", re.compile(r"^/api/portal/[^/]+/my_viewings$"), RoutePolicy.PORTAL_SESSION, False, "Portal client scheduled viewings"),
    RoutePolicyDecl("GET", "/api/portal/{client_id}/demos", re.compile(r"^/api/portal/[^/]+/demos$"), RoutePolicy.PORTAL_SESSION, False, "Portal client scheduled demos list"),
    RoutePolicyDecl("POST", "/api/portal/{client_id}/demos/{demo_id}/confirm", re.compile(r"^/api/portal/[^/]+/demos/[^/]+/confirm$"), RoutePolicy.PORTAL_SESSION, False, "Portal client confirm demo slot"),
    RoutePolicyDecl("POST", "/api/portal/{client_id}/demos/{demo_id}/cancel", re.compile(r"^/api/portal/[^/]+/demos/[^/]+/cancel$"), RoutePolicy.PORTAL_SESSION, False, "Portal client cancel demo"),
    RoutePolicyDecl("POST", "/api/portal/{client_id}/demos/{demo_id}/reschedule", re.compile(r"^/api/portal/[^/]+/demos/[^/]+/reschedule$"), RoutePolicy.PORTAL_SESSION, False, "Portal client reschedule demo"),
    RoutePolicyDecl("PATCH", "/api/portal/{client_id}/demos/{demo_id}/poc_criteria", re.compile(r"^/api/portal/[^/]+/demos/[^/]+/poc_criteria$"), RoutePolicy.PORTAL_SESSION, False, "Portal client update POC success criteria"),
    RoutePolicyDecl("POST", "/api/portal/{client_id}/demos/{demo_id}/poc_feedback", re.compile(r"^/api/portal/[^/]+/demos/[^/]+/poc_feedback$"), RoutePolicy.PORTAL_SESSION, False, "Portal client submit POC trial feedback"),
    RoutePolicyDecl("GET", "/api/portal/{client_id}/preferences", re.compile(r"^/api/portal/[^/]+/preferences$"), RoutePolicy.PORTAL_SESSION, False, "Portal client preferences get"),
    RoutePolicyDecl("PUT", "/api/portal/{client_id}/preferences", re.compile(r"^/api/portal/[^/]+/preferences$"), RoutePolicy.PORTAL_SESSION, False, "Portal client preferences update"),
    RoutePolicyDecl("PATCH", "/api/portal/{client_id}/preferences", re.compile(r"^/api/portal/[^/]+/preferences$"), RoutePolicy.PORTAL_SESSION, False, "Portal client preferences patch"),
    RoutePolicyDecl("POST", "/api/portal/{client_id}/request_demo", re.compile(r"^/api/portal/[^/]+/request_demo$"), RoutePolicy.PORTAL_SESSION, False, "Portal client request viewing"),

    # ─── 3. ADMIN-ONLY ROUTES ────────────────────────────────────────────────
    RoutePolicyDecl("POST", "/api/run_evaluations", re.compile(r"^/api/run_evaluations$"), RoutePolicy.ADMIN_ONLY, False, "Global pipeline evaluation recalculation"),
    RoutePolicyDecl("POST", "/api/retrain_model", re.compile(r"^/api/retrain_model$"), RoutePolicy.ADMIN_ONLY, False, "Retrain machine learning model on global outcomes"),
    RoutePolicyDecl("PATCH", "/api/properties/{property_id}", re.compile(r"^/api/properties/[^/]+$"), RoutePolicy.ADMIN_ONLY, False, "Mutate global property inventory"),
    RoutePolicyDecl("POST", "/api/simulate_market_day", re.compile(r"^/api/simulate_market_day$"), RoutePolicy.ADMIN_ONLY, False, "Simulate market price shifts across properties"),
    RoutePolicyDecl("POST", "/api/simulate_price_change/{property_id}", re.compile(r"^/api/simulate_price_change/[^/]+$"), RoutePolicy.ADMIN_ONLY, False, "Simulate price change for specific property"),
    RoutePolicyDecl("POST", "/api/whatsapp/simulate_incoming", re.compile(r"^/api/whatsapp/simulate_incoming$"), RoutePolicy.ADMIN_ONLY, False, "Simulate incoming WhatsApp webhook"),
    RoutePolicyDecl("POST", "/api/whatsapp/process_reminders", re.compile(r"^/api/whatsapp/process_reminders$"), RoutePolicy.ADMIN_ONLY, False, "Manual trigger for background WhatsApp reminder queue"),
    RoutePolicyDecl("GET", "/api/agents", re.compile(r"^/api/agents$"), RoutePolicy.ADMIN_ONLY, False, "List all agency accounts and credentials"),
    RoutePolicyDecl("POST", "/api/admin/agents/{agent_id}/issue-reset", re.compile(r"^/api/admin/agents/[^/]+/issue-reset$"), RoutePolicy.ADMIN_ONLY, False, "Admin issue password reset code for agent"),
    RoutePolicyDecl("POST", "/api/admin/agents/{agent_id}/reactivate", re.compile(r"^/api/admin/agents/[^/]+/reactivate$"), RoutePolicy.ADMIN_ONLY, False, "Admin reactivate agent account"),
    RoutePolicyDecl("POST", "/api/admin/agents/{agent_id}/revoke-all-sessions", re.compile(r"^/api/admin/agents/[^/]+/revoke-all-sessions$"), RoutePolicy.ADMIN_ONLY, False, "Admin revoke all active agent sessions"),
    RoutePolicyDecl("POST", "/api/admin/agents/{agent_id}/suspend", re.compile(r"^/api/admin/agents/[^/]+/suspend$"), RoutePolicy.ADMIN_ONLY, False, "Admin suspend agent account"),
    RoutePolicyDecl("POST", "/api/admin/agents/{agent_id}/unlock", re.compile(r"^/api/admin/agents/[^/]+/unlock$"), RoutePolicy.ADMIN_ONLY, False, "Admin unlock agent lockout"),
    RoutePolicyDecl("GET", "/api/model_status", re.compile(r"^/api/model_status$"), RoutePolicy.ADMIN_ONLY, False, "Current model training status and feature weights"),
    RoutePolicyDecl("GET", "/api/prediction_accuracy", re.compile(r"^/api/prediction_accuracy$"), RoutePolicy.ADMIN_ONLY, False, "Machine learning model performance metrics"),

    # ─── 4. CLIENT-SCOPED ROUTES (Agent must own client or be admin; 404 otherwise)
    RoutePolicyDecl("PATCH", "/api/clients/{client_id}", re.compile(r"^/api/clients/[^/]+$"), RoutePolicy.CLIENT_SCOPED, False, "Update client demographic or stage metadata"),
    RoutePolicyDecl("POST", "/api/clients/{client_id}/advance_stage", re.compile(r"^/api/clients/[^/]+/advance_stage$"), RoutePolicy.CLIENT_SCOPED, False, "Advance client relationship stage"),
    RoutePolicyDecl("GET", "/api/clients/{client_id}/purchases", re.compile(r"^/api/clients/[^/]+/purchases$"), RoutePolicy.CLIENT_SCOPED, False, "List purchases for assigned client"),
    RoutePolicyDecl("POST", "/api/clients/{client_id}/purchases", re.compile(r"^/api/clients/[^/]+/purchases$"), RoutePolicy.CLIENT_SCOPED, False, "Record purchase transaction for assigned client"),
    RoutePolicyDecl("POST", "/api/record_outcome", re.compile(r"^/api/record_outcome$"), RoutePolicy.CLIENT_SCOPED, False, "Record closed-won or closed-lost deal outcome"),
    RoutePolicyDecl("POST", "/api/generate_insight", re.compile(r"^/api/generate_insight$"), RoutePolicy.CLIENT_SCOPED, True, "Generate Groq LLM client insight card"),
    RoutePolicyDecl("POST", "/api/generate_chart_insight", re.compile(r"^/api/generate_chart_insight$"), RoutePolicy.CLIENT_SCOPED, True, "Generate Groq LLM chart narrative"),
    RoutePolicyDecl("POST", "/api/generate_reasoning", re.compile(r"^/api/generate_reasoning$"), RoutePolicy.CLIENT_SCOPED, True, "Generate Groq LLM deal reasoning narrative"),
    RoutePolicyDecl("POST", "/api/generate_invite", re.compile(r"^/api/generate_invite$"), RoutePolicy.CLIENT_SCOPED, True, "Generate Groq LLM personalized portal invitation copy"),
    RoutePolicyDecl("POST", "/api/invite/mark_sent", re.compile(r"^/api/invite/mark_sent$"), RoutePolicy.CLIENT_SCOPED, False, "Mark invitation as dispatched to client"),
    RoutePolicyDecl("POST", "/api/log_viewing", re.compile(r"^/api/log_viewing$"), RoutePolicy.CLIENT_SCOPED, False, "Log viewing session for client"),
    RoutePolicyDecl("POST", "/api/schedule_viewing", re.compile(r"^/api/schedule_viewing$"), RoutePolicy.CLIENT_SCOPED, False, "Schedule new property viewing appointment"),
    RoutePolicyDecl("PATCH", "/api/cancel_viewing/{viewing_id}", re.compile(r"^/api/cancel_viewing/[^/]+$"), RoutePolicy.CLIENT_SCOPED, False, "Cancel scheduled viewing appointment"),
    RoutePolicyDecl("PATCH", "/api/complete_viewing/{viewing_id}", re.compile(r"^/api/complete_viewing/[^/]+$"), RoutePolicy.CLIENT_SCOPED, False, "Complete viewing appointment and trigger evaluation"),
    RoutePolicyDecl("PATCH", "/api/confirm_demo/{viewing_id}", re.compile(r"^/api/confirm_demo/[^/]+$"), RoutePolicy.CLIENT_SCOPED, False, "Confirm viewing demo request"),
    RoutePolicyDecl("POST", "/api/whatsapp/suggest_reply", re.compile(r"^/api/whatsapp/suggest_reply$"), RoutePolicy.CLIENT_SCOPED, True, "Generate Groq LLM suggested reply for WhatsApp conversation"),
    RoutePolicyDecl("POST", "/api/whatsapp/clear_opt_out", re.compile(r"^/api/whatsapp/clear_opt_out$"), RoutePolicy.CLIENT_SCOPED, False, "Clear opt-out status on explicit client request"),
    RoutePolicyDecl("POST", "/api/whatsapp/resume_automation", re.compile(r"^/api/whatsapp/resume_automation$"), RoutePolicy.CLIENT_SCOPED, False, "Resume automated follow-ups for client conversation"),
    RoutePolicyDecl("GET", "/api/whatsapp/window_status", re.compile(r"^/api/whatsapp/window_status$"), RoutePolicy.CLIENT_SCOPED, False, "Check Meta 24-hour customer service window status"),
    RoutePolicyDecl("POST", "/api/whatsapp/conversations/{conversation_id}/read", re.compile(r"^/api/whatsapp/conversations/[^/]+/read$"), RoutePolicy.CLIENT_SCOPED, False, "Mark WhatsApp conversation messages as read"),
    RoutePolicyDecl("POST", "/api/whatsapp/send", re.compile(r"^/api/whatsapp/send$"), RoutePolicy.CLIENT_SCOPED, False, "Send WhatsApp message to client"),
    RoutePolicyDecl("POST", "/api/whatsapp/send_message", re.compile(r"^/api/whatsapp/send_message$"), RoutePolicy.CLIENT_SCOPED, False, "Direct WhatsApp outbound message"),
    RoutePolicyDecl("POST", "/api/whatsapp/send_pitch", re.compile(r"^/api/whatsapp/send_pitch$"), RoutePolicy.CLIENT_SCOPED, False, "Send property pitch message to client"),
    RoutePolicyDecl("POST", "/api/whatsapp/nudge", re.compile(r"^/api/whatsapp/nudge$"), RoutePolicy.CLIENT_SCOPED, False, "Trigger nudge message for stale client conversation"),
    # Console portal panel scoping routes:
    RoutePolicyDecl("GET", "/api/console/clients/{client_id}/portal/audit-log", re.compile(r"^/api/console/clients/[^/]+/portal/audit-log$"), RoutePolicy.CLIENT_SCOPED, False, "View client portal audit trail"),
    RoutePolicyDecl("GET", "/api/console/clients/{client_id}/portal/contacts", re.compile(r"^/api/console/clients/[^/]+/portal/contacts$"), RoutePolicy.CLIENT_SCOPED, False, "List portal contacts for assigned client"),
    RoutePolicyDecl("POST", "/api/console/clients/{client_id}/portal/contacts", re.compile(r"^/api/console/clients/[^/]+/portal/contacts$"), RoutePolicy.CLIENT_SCOPED, False, "Provision new portal contact for client"),
    RoutePolicyDecl("POST", "/api/console/clients/{client_id}/portal/contacts/{contact_id}/issue-code", re.compile(r"^/api/console/clients/[^/]+/portal/contacts/[^/]+/issue-code$"), RoutePolicy.CLIENT_SCOPED, False, "Issue new access code for portal contact"),
    RoutePolicyDecl("POST", "/api/console/clients/{client_id}/portal/contacts/{contact_id}/unlock", re.compile(r"^/api/console/clients/[^/]+/portal/contacts/[^/]+/unlock$"), RoutePolicy.CLIENT_SCOPED, False, "Unlock locked portal contact"),
    RoutePolicyDecl("POST", "/api/console/clients/{client_id}/portal/contacts/{contact_id}/revoke-code", re.compile(r"^/api/console/clients/[^/]+/portal/contacts/[^/]+/revoke-code$"), RoutePolicy.CLIENT_SCOPED, False, "Revoke access code for portal contact"),
    RoutePolicyDecl("PATCH", "/api/console/clients/{client_id}/portal/contacts/{contact_id}/deactivate", re.compile(r"^/api/console/clients/[^/]+/portal/contacts/[^/]+/deactivate$"), RoutePolicy.CLIENT_SCOPED, False, "Deactivate portal contact"),
    RoutePolicyDecl("POST", "/api/console/clients/{client_id}/portal/revoke-all-sessions", re.compile(r"^/api/console/clients/[^/]+/portal/revoke-all-sessions$"), RoutePolicy.CLIENT_SCOPED, False, "Revoke all portal sessions for client"),
    RoutePolicyDecl("POST", "/api/console/clients/{client_id}/portal/rotate-legacy-code", re.compile(r"^/api/console/clients/[^/]+/portal/rotate-legacy-code$"), RoutePolicy.CLIENT_SCOPED, False, "Rotate legacy access code for client"),
    RoutePolicyDecl("GET", "/api/console/clients/{client_id}/portal/profile-audit", re.compile(r"^/api/console/clients/[^/]+/portal/profile-audit$"), RoutePolicy.CLIENT_SCOPED, False, "View client profile audit trail"),
    RoutePolicyDecl("GET", "/api/console/clients/{client_id}/quotes", re.compile(r"^/api/console/clients/[^/]+/quotes$"), RoutePolicy.CLIENT_SCOPED, False, "List quotes for assigned client"),
    RoutePolicyDecl("POST", "/api/console/clients/{client_id}/quotes/{quote_id}/send", re.compile(r"^/api/console/clients/[^/]+/quotes/[^/]+/send$"), RoutePolicy.CLIENT_SCOPED, False, "Send quote to client"),
    RoutePolicyDecl("POST", "/api/console/clients/{client_id}/inquiries/{inquiry_id}/reply", re.compile(r"^/api/console/clients/[^/]+/inquiries/[^/]+/reply$"), RoutePolicy.CLIENT_SCOPED, False, "Rep reply to client inquiry"),

    # ─── 5. ANY-AGENT ROUTES (Authenticated agent; scoped to agent's clients) ──
    RoutePolicyDecl("GET", "/api/agent/me", re.compile(r"^/api/agent/me$"), RoutePolicy.ANY_AGENT, False, "Current agent account identity and permissions"),
    RoutePolicyDecl("POST", "/api/agent/logout", re.compile(r"^/api/agent/logout$"), RoutePolicy.ANY_AGENT, False, "Agent session logout and revocation"),
    RoutePolicyDecl("GET", "/api/console/quotes/pending", re.compile(r"^/api/console/quotes/pending$"), RoutePolicy.ANY_AGENT, True, "List pending quote requests for rep"),
    RoutePolicyDecl("POST", "/api/console/copilot", re.compile(r"^/api/console/copilot$"), RoutePolicy.ANY_AGENT, True, "Rep copilot (Google ADK agent)"),
    RoutePolicyDecl("GET", "/api/console/inquiries/priority", re.compile(r"^/api/console/inquiries/priority$"), RoutePolicy.ANY_AGENT, False, "Priority client inquiries for rep"),
    RoutePolicyDecl("GET", "/api/console/inquiry/{inquiry_id}", re.compile(r"^/api/console/inquiry/[^/]+$"), RoutePolicy.ANY_AGENT, False, "Rep inquiry detail view"),
    RoutePolicyDecl("POST", "/api/console/inquiry/{inquiry_id}/resolve", re.compile(r"^/api/console/inquiry/[^/]+/resolve$"), RoutePolicy.ANY_AGENT, False, "Rep mark inquiry resolved"),
    RoutePolicyDecl("POST", "/api/console/inquiry/{inquiry_id}/reopen", re.compile(r"^/api/console/inquiry/[^/]+/reopen$"), RoutePolicy.ANY_AGENT, False, "Rep reopen resolved inquiry"),
    RoutePolicyDecl("GET", "/api/console/clients/{client_id}/inquiry-history", re.compile(r"^/api/console/clients/[^/]+/inquiry-history$"), RoutePolicy.ANY_AGENT, False, "Company full inquiry history for rep"),
    RoutePolicyDecl("POST", "/api/console/inquiry/{inquiry_id}/suggest-reply", re.compile(r"^/api/console/inquiry/[^/]+/suggest-reply$"), RoutePolicy.ANY_AGENT, True, "AI-grounded reply draft for rep (never sends)"),
    RoutePolicyDecl("GET", "/api/daily_worklist", re.compile(r"^/api/daily_worklist$"), RoutePolicy.ANY_AGENT, False, "Daily prioritize tasks (scoped to agent)"),
    RoutePolicyDecl("GET", "/api/dashboard_briefing", re.compile(r"^/api/dashboard_briefing$"), RoutePolicy.ANY_AGENT, True, "Dashboard VIP narrative (LLM, scoped to agent)"),
    RoutePolicyDecl("GET", "/api/scheduled_viewings", re.compile(r"^/api/scheduled_viewings$"), RoutePolicy.ANY_AGENT, False, "Scheduled viewings list (scoped to agent)"),
    RoutePolicyDecl("GET", "/api/signals", re.compile(r"^/api/signals$"), RoutePolicy.ANY_AGENT, False, "Active market/tier signals (scoped to agent)"),
    RoutePolicyDecl("POST", "/api/signals/{signal_id}/dismiss", re.compile(r"^/api/signals/[^/]+/dismiss$"), RoutePolicy.ANY_AGENT, False, "Dismiss market signal"),
    RoutePolicyDecl("GET", "/api/shortlist/{property_id}", re.compile(r"^/api/shortlist/[^/]+$"), RoutePolicy.ANY_AGENT, False, "Shortlist matching clients for property (scoped to agent's clients)"),
    RoutePolicyDecl("GET", "/api/property_price_history/{property_id}", re.compile(r"^/api/property_price_history/[^/]+$"), RoutePolicy.ANY_AGENT, False, "Read historical pricing records for property"),
    RoutePolicyDecl("GET", "/api/market_movements", re.compile(r"^/api/market_movements$"), RoutePolicy.ANY_AGENT, False, "Summary of active market movements across inventory"),
    RoutePolicyDecl("GET", "/api/pipeline_projection", re.compile(r"^/api/pipeline_projection$"), RoutePolicy.ANY_AGENT, False, "Projected pipeline revenue (scoped to agent's assigned clients)"),
    RoutePolicyDecl("GET", "/api/whatsapp/conversations", re.compile(r"^/api/whatsapp/conversations$"), RoutePolicy.ANY_AGENT, False, "List active conversations (scoped to agent's assigned clients)"),
    RoutePolicyDecl("GET", "/api/whatsapp/messages", re.compile(r"^/api/whatsapp/messages$"), RoutePolicy.ANY_AGENT, False, "Read messages stream for active conversation"),
    RoutePolicyDecl("GET", "/api/whatsapp/pitch_template", re.compile(r"^/api/whatsapp/pitch_template$"), RoutePolicy.ANY_AGENT, False, "Get preconfigured pitch template text"),
    RoutePolicyDecl("GET", "/api/whatsapp/reminder_template_config", re.compile(r"^/api/whatsapp/reminder_template_config$"), RoutePolicy.ANY_AGENT, False, "Get reminder template config"),
]


def match_policy(method: str, path: str) -> Optional[RoutePolicyDecl]:
    """Finds matching RoutePolicyDecl for given HTTP method and path."""
    clean_method = method.upper()
    for decl in ROUTE_POLICY_DECLARATIONS:
        if decl.method == clean_method and decl.regex.match(path):
            return decl
    return None
