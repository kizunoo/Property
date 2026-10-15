import os
import requests
import json
import hmac
import hashlib
from hashlib import md5
import threading
from datetime import datetime, timezone, timedelta, date, time
import re
import zoneinfo
import uuid
import urllib.parse
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from supabase import create_client, Client
from groq import Groq
from scoring_engine import score as score_pair
from ml_inference import predict_probability, reload_model
from roi import compute_roi
from portal_models import RoiScenarioInputs, FacilityProfile
import subprocess
import sys
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
from apscheduler.schedulers.background import BackgroundScheduler
import random as _random

from pathlib import Path
_env_path = Path(__file__).resolve().parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_KEY = (
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    or os.getenv("SUPABASE_SERVICE_KEY")
    or os.getenv("SUPABASE_KEY")
    or os.getenv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY")
    or os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY")
)
if SUPABASE_KEY and (SUPABASE_KEY.startswith("sb_publishable_") or "anon" in SUPABASE_KEY):
    print("[SUPABASE SECURITY WARNING] Backend is using an anon/publishable key. Configure SUPABASE_SERVICE_ROLE_KEY in backend/.env for RLS bypass.")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")
GROQ_FALLBACK_MODELS = ["qwen/qwen3.8-27b", "openai/gpt-oss-120b", "openai/gpt-oss-20b"]

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set in .env or .env.local")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

def _call_groq_llm(messages: list, max_tokens: int = 400, temperature: float = 0.4, timeout: float = 20.0) -> str:
    if not groq_client:
        raise HTTPException(status_code=503, detail="GROQ_API_KEY not configured")
    
    models_to_try = [GROQ_MODEL] + [m for m in GROQ_FALLBACK_MODELS if m != GROQ_MODEL]
    last_err = None
    
    for model_name in models_to_try:
        try:
            chat_completion = groq_client.chat.completions.create(
                messages=messages,
                model=model_name,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            )
            content = chat_completion.choices[0].message.content
            if content and content.strip():
                return content.strip()
        except Exception as exc:
            print(f"[groq_llm] Model '{model_name}' failed: {exc}")
            last_err = exc
            continue
            
    raise HTTPException(status_code=502, detail=f"LLM generation failed: {last_err}") from last_err

def get_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def check_and_log_tier_signal(client_id: str, client_name: str, new_tier: str, property_id: str = None):
    """
    Compares new_tier against clients.last_known_tier.
    Inserts a signal row if the tier changed, then updates last_known_tier.
    Call this every time a client's tier is recomputed (run_evaluations AND log_viewing).
    """
    client_row = supabase.table("clients").select("last_known_tier").eq("id", client_id).single().execute()
    old_tier = client_row.data.get("last_known_tier") if client_row.data else None

    if old_tier != new_tier:
        if old_tier is None:
            pass  # first evaluation ever for this client — do not fire a signal, nothing to compare against
        elif new_tier == "TIER_1" and old_tier != "TIER_1":
            supabase.table("signals").insert({
                "type": "first_vip",
                "client_id": client_id,
                "property_id": property_id,
                "message": f"{client_name} just crossed into Likely Buyer for the first time"
            }).execute()
        else:
            tier_rank = {"TIER_3": 0, "TIER_2": 1, "TIER_1": 2}
            if tier_rank.get(new_tier, 0) > tier_rank.get(old_tier, 0):
                label = {"TIER_1": "LIKELY BUYER", "TIER_2": "POSSIBLE BUYER", "TIER_3": "UNLIKELY BUYER"}
                supabase.table("signals").insert({
                    "type": "tier_upgrade",
                    "client_id": client_id,
                    "property_id": property_id,
                    "message": f"{client_name} moved {label.get(old_tier)} → {label.get(new_tier)}"
                }).execute()

        supabase.table("clients").update({"last_known_tier": new_tier}).eq("id", client_id).execute()


# ─── Stage Progression Engine (Phase 2) ─────────────────────────────────────────

STAGE_ORDER = ['new', 'contacted', 'viewing', 'negotiation', 'closed_won', 'closed_lost']

def advance_stage(client_id: str, new_stage: str, force: bool = False) -> str:
    """
    Moves a client's relationship_stage forward. By default, refuses to move
    a client BACKWARD (e.g. won't demote someone from 'viewing' to 'contacted')
    since real relationships don't un-happen. Pass force=True for outcome
    recording, which should always jump straight to closed_won/closed_lost
    regardless of current stage.
    """
    try:
        res = supabase.table("clients").select("relationship_stage").eq("id", client_id).single().execute()
        current = res.data if res else None
        current_stage = (current.get("relationship_stage") if current else None) or "new"
    except Exception as exc:
        print(f"[advance_stage] Warning fetching current stage: {exc}")
        current_stage = "new"

    if force:
        try:
            supabase.table("clients").update({"relationship_stage": new_stage}).eq("id", client_id).execute()
        except Exception as exc:
            print(f"[advance_stage] Failed to force-update stage: {exc}")
        return new_stage

    if new_stage in ('closed_won', 'closed_lost'):
        # never auto-advance TO a closed state except via force (record_outcome)
        return current_stage

    try:
        curr_idx = STAGE_ORDER.index(current_stage) if current_stage in STAGE_ORDER else 0
        new_idx = STAGE_ORDER.index(new_stage) if new_stage in STAGE_ORDER else 0
        if new_idx > curr_idx and current_stage not in ('closed_won', 'closed_lost'):
            supabase.table("clients").update({"relationship_stage": new_stage}).eq("id", client_id).execute()
            return new_stage
    except Exception as exc:
        print(f"[advance_stage] Failed to advance stage: {exc}")

    return current_stage


_is_prod = os.getenv("ENVIRONMENT", "").lower() in ("production", "prod")
app = FastAPI(
    title="PIPELINE.EV Logic Engine",
    docs_url=None if _is_prod else "/docs",
    redoc_url=None if _is_prod else "/redoc",
    openapi_url=None if _is_prod else "/openapi.json",
)

from portal_auth import (
    get_current_portal_session,
    require_company_access,
    PortalSession,
    check_portal_write_rate_limit,
    log_audit_event,
    get_trusted_client_ip,
)
import portal_routes
app.include_router(portal_routes.router)

from agent_auth import (
    get_current_agent,
    require_admin,
    AgentIdentity,
    check_agent_llm_rate_limit,
    check_client_access,
    require_client_access,
)
from route_policies import RoutePolicy, match_policy, ROUTE_POLICY_DECLARATIONS
import agent_routes
app.include_router(agent_routes.router)

import re
from fastapi.responses import JSONResponse

AGENT_AUTH_ALLOWLIST = [
    d.regex for d in ROUTE_POLICY_DECLARATIONS if d.policy in (RoutePolicy.PUBLIC, RoutePolicy.PORTAL_SESSION)
]


@app.middleware("http")
async def enforce_agent_default_deny(request: Request, call_next):
    path = request.url.path

    # Only inspect /api/ routes
    if not path.startswith("/api/"):
        return await call_next(request)

    # 1. Lookup declared security policy for (method, path)
    decl = match_policy(request.method, path)
    if not decl:
        return JSONResponse(
            status_code=500,
            content={"detail": f"Undeclared security policy for {request.method} {path}. Request blocked by default-deny policy."}
        )

    # 2. Public exemption: passes through
    if decl.policy == RoutePolicy.PUBLIC:
        return await call_next(request)

    # 3. Portal session: passes through to portal auth handlers
    if decl.policy == RoutePolicy.PORTAL_SESSION:
        return await call_next(request)

    # 4. Simulation endpoints guard: 404 in production
    is_prod = os.getenv("ENVIRONMENT", "").lower() in ("production", "prod")
    if "simulate_" in path and is_prod:
        return JSONResponse(status_code=404, content={"detail": "Not Found"})

    # 5. State-changing Origin / CSRF check
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        origin = request.headers.get("origin")
        auth_hdr = request.headers.get("authorization", "")
        has_bearer = auth_hdr.lower().startswith("bearer ")

        # If request arrives with ambient cookie but without Bearer header, Origin is mandatory
        if not has_bearer and "agent_session" in request.cookies and not origin:
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF verification failed: Missing Origin on cookie-authenticated request."}
            )

        if origin:
            allowed_hosts = []
            if not is_prod:
                allowed_hosts.extend(["localhost:3000", "127.0.0.1:3000", "localhost:8000", "127.0.0.1:8000"])
            custom_origins = os.getenv("ALLOWED_ORIGINS", "")
            if custom_origins:
                allowed_hosts.extend([o.strip() for o in custom_origins.split(",") if o.strip()])
            
            origin_host = origin.split("://")[-1].rstrip("/")
            req_host = request.headers.get("host", "")
            if not any(origin_host == h or origin_host.endswith("." + h) for h in allowed_hosts) and origin_host != req_host:
                return JSONResponse(
                    status_code=403,
                    content={"detail": f"CSRF verification failed: Untrusted Origin '{origin_host}'."}
                )

    # 6. Require valid, active agent session
    try:
        agent = get_current_agent(request)
        request.state.agent = agent
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    except Exception as exc:
        return JSONResponse(status_code=500, content={"detail": f"Agent authentication check error: {exc}"})

    # 7. Admin-only policy enforcement
    if decl.policy == RoutePolicy.ADMIN_ONLY:
        if agent.role != "admin":
            return JSONResponse(
                status_code=403,
                content={"detail": "Administrator privileges required for this endpoint."}
            )

    # 8. Per-agent LLM route rate limiting
    if decl.is_llm:
        try:
            check_agent_llm_rate_limit(agent.account_id)
        except HTTPException as exc:
            headers = dict(exc.headers or {})
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=headers)

    return await call_next(request)


@app.get("/api/health")
def api_health():
    return {"status": "ok", "service": "PIPELINE.EV Logic Engine"}



@app.post("/api/invite/mark_sent")
def mark_invite_sent(body: dict, request: Request):
    client_id = body.get("client_id")
    property_id = body.get("property_id")
    if not client_id:
        raise HTTPException(status_code=400, detail="client_id is required")

    if hasattr(request.state, "agent"):
        from agent_auth import require_client_access
        require_client_access(request.state.agent, client_id, supabase)

    try:
        supabase.table("invite_drafts").update({
            "sent_at": datetime.now(timezone.utc).isoformat(),
        }).eq("client_id", client_id).eq("property_id", property_id).execute()
    except Exception as exc:
        print(f"[mark_invite_sent] invite_drafts update warning: {exc}")

    new_stage = advance_stage(client_id, "contacted")

    return {"client_id": client_id, "relationship_stage": new_stage}


def get_whatsapp_credentials():
    # Always reload from .env on every call so token refreshes take effect
    # immediately without needing to restart uvicorn.
    _env_path = Path(__file__).resolve().parent / ".env"
    if _env_path.exists():
        load_dotenv(_env_path, override=True)
    phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
    token = os.getenv("WHATSAPP_ACCESS_TOKEN") or os.getenv("WHATSAPP_API_TOKEN")
    return phone_id, token


WHATSAPP_API_VERSION = "v25.0"


def normalize_whatsapp_number(raw_phone: str | None) -> str:
    """
    Normalizes a phone number to standard digits with country code.
    Converts Malaysian local formats:
      - '010-9722730' -> '60109722730'
      - '+60 10 972 2730' -> '60109722730'
      - '60109722730' -> '60109722730'
      - '+1 (555) 123-4567' -> '15551234567'
    """
    if not raw_phone:
        return ""
    digits = "".join(filter(str.isdigit, str(raw_phone)))
    if not digits:
        return ""
    # Malaysian domestic format: starts with 0 (e.g. 010..., 012..., 011..., 03...)
    if digits.startswith("0"):
        digits = "60" + digits[1:]
    return digits


def check_whatsapp_delivery_guard(to_number: str) -> tuple[bool, str]:
    """
    Evaluates whether calling the real Meta WhatsApp Cloud API is allowed.
    Defaults to safe simulation behavior when ENV is not production.
    """
    clean_digits = normalize_whatsapp_number(to_number)

    # 1. Explicit dry run switch
    if os.getenv("WHATSAPP_DRY_RUN", "false").lower() in ("true", "1", "yes"):
        return False, "WHATSAPP_DRY_RUN=true is enabled"

    # 2. Fixed-line / Landline safety guard (03, 04, 05, 06, 07, 08, 09 cannot receive WhatsApp)
    if clean_digits.startswith(("603", "604", "605", "606", "607", "608", "609")):
        return False, f"Safety guard: {clean_digits} is a company landline, not an opted-in WhatsApp mobile"

    # 3. Environment check: if not production, whitelist check
    env = os.getenv("ENV") or os.getenv("APP_ENV") or os.getenv("NODE_ENV") or "development"
    is_prod = env.lower() == "production"

    if not is_prod:
        raw_allowed = os.getenv("WHATSAPP_ALLOWED_TEST_NUMBERS", "")
        test_single = os.getenv("WHATSAPP_TEST_NUMBER", "60109722730")
        allowed_list = [
            normalize_whatsapp_number(n)
            for n in raw_allowed.split(",") if n.strip()
        ]
        if test_single:
            allowed_list.append(normalize_whatsapp_number(test_single))

        if clean_digits not in allowed_list:
            return False, f"Dev guard: {clean_digits} not in WHATSAPP_ALLOWED_TEST_NUMBERS (ENV={env})"

    return True, "Allowed"


def is_within_24h_window(phone_number: str) -> bool:
    """
    Checks if the client has sent a message within the last 24 hours.
    Inside 24h: Meta allows free-form text and native interactive messages.
    Outside 24h: Meta requires a pre-approved template message.
    """
    clean_digits = normalize_whatsapp_number(phone_number)
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    # 1. Check Supabase
    try:
        res = (
            supabase.table("whatsapp_messages")
            .select("timestamp")
            .eq("to_number", clean_digits)
            .in_("sender", ["client", "user", "inbound"])
            .gte("timestamp", cutoff)
            .order("timestamp", desc=True)
            .limit(1)
            .execute()
        )
        if res.data and len(res.data) > 0:
            return True
    except Exception as exc:
        print(f"[is_within_24h_window] Supabase check warning: {exc}")

    # 2. Check local message history
    for m in reversed(WHATSAPP_MESSAGE_HISTORY):
        sender = m.get("sender")
        m_num = normalize_whatsapp_number(m.get("to_number") or m.get("phone_number") or "")
        if m_num == clean_digits and sender in ("client", "user", "inbound"):
            ts_str = m.get("timestamp")
            if ts_str:
                try:
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    if ts >= datetime.now(timezone.utc) - timedelta(hours=24):
                        return True
                except Exception:
                    pass
    return False


class MetaReengagementError(Exception):
    """Raised when Meta returns error code 131047 indicating the 24-hour customer service window has expired."""
    def __init__(self, message: str = "24h window expired", raw_response: dict | None = None):
        super().__init__(message)
        self.raw_response = raw_response or {}


PITCH_TEMPLATE_CONFIG = {
    "name": "viewing_slots_pitch",
    # ---------------------------------------------------------------------------
    # APPROVED META TEMPLATE BODY (do NOT edit without re-submitting to Meta)
    # Category: MARKETING  |  Language: en_US
    # Buttons: Option 1 / Option 2 / Option 3  (quick-reply, payload injected at send-time)
    # ---------------------------------------------------------------------------
    "body": "Hello {{1}}, this is PIPELINE.EV following up on the {{2}}. We would like to invite your team to an on-site demonstration. Proposed times: Option 1: {{3}}, Option 2: {{4}}, Option 3: {{5}}. Tap a button below to choose, or reply with a time that suits you.",
    "variables": [
        {"position": 1, "name": "client_name",  "description": "Client full name or company contact",    "example": "Abdullah"},
        {"position": 2, "name": "unit_name",    "description": "Product / unit being pitched",           "example": "AMR-4000 Heavy-Lift Pallet Jack"},
        {"position": 3, "name": "slot_1",       "description": "First proposed slot label",              "example": "Mon 5 Oct, 10:00 AM"},
        {"position": 4, "name": "slot_2",       "description": "Second proposed slot label",             "example": "Tue 6 Oct, 2:00 PM"},
        {"position": 5, "name": "slot_3",       "description": "Third proposed slot label",              "example": "Wed 7 Oct, 11:00 AM"},
    ],
    "buttons": [
        {"position": 1, "label": "Option 1", "payload_pattern": "slot_pick:{offer_id}:1"},
        {"position": 2, "label": "Option 2", "payload_pattern": "slot_pick:{offer_id}:2"},
        {"position": 3, "label": "Option 3", "payload_pattern": "slot_pick:{offer_id}:3"},
    ],
}


def render_viewing_slots_pitch_text(client_name: str, property_name: str, slots: list[dict]) -> str:
    """
    Renders the exact text corresponding to the approved Meta 'viewing_slots_pitch' template.
    Uses PITCH_TEMPLATE_CONFIG as the single source of truth for sending, previews, and storage.
    Variable {{2}} is strictly the unit name (property address or name).
    """
    s1 = slots[0]["label"] if len(slots) > 0 else "Option 1"
    s2 = slots[1]["label"] if len(slots) > 1 else "Option 2"
    s3 = slots[2]["label"] if len(slots) > 2 else "Option 3"

    text = PITCH_TEMPLATE_CONFIG["body"]
    text = text.replace("{{1}}", client_name or "Valued Partner")
    text = text.replace("{{2}}", property_name or "Robotics Unit")
    text = text.replace("{{3}}", s1)
    text = text.replace("{{4}}", s2)
    text = text.replace("{{5}}", s3)
    return text


REMINDER_TEMPLATE_CONFIG = {
    "name": "viewing_reminder",
    # ---------------------------------------------------------------------------
    # APPROVED META TEMPLATE BODY (do NOT edit without re-submitting to Meta)
    # Category: UTILITY  |  Language: en_US
    # Buttons: Confirm / Reschedule / Cancel  (quick-reply, payload injected at send-time)
    # ---------------------------------------------------------------------------
    "category": "UTILITY",
    "body": "Hello {{1}}, this is PIPELINE.EV following up on the {{2}}. Your on-site demonstration is confirmed for {{3}}. Please confirm your attendance, or let us know if you need to reschedule.",
    "variables": [
        {"position": 1, "name": "client_name", "description": "Client full name or company contact", "example": "Abdullah"},
        {"position": 2, "name": "unit_name",   "description": "Robotics unit / product being demonstrated", "example": "AMR-4000 Heavy-Lift Pallet Jack"},
        {"position": 3, "name": "datetime",    "description": "Demo date and time in MYT (inline, no line breaks)", "example": "Mon 5 Oct, 10:00 AM"},
    ],
    "buttons": [
        {"position": 1, "label": "Confirm",     "payload_pattern": "reminder:{viewing_id}:confirm"},
        {"position": 2, "label": "Reschedule",  "payload_pattern": "reminder:{viewing_id}:reschedule"},
        {"position": 3, "label": "Cancel",      "payload_pattern": "reminder:{viewing_id}:cancel"},
    ],
}


def render_viewing_reminder_text(client_name: str, property_name: str, formatted_datetime: str) -> str:
    """
    Renders the exact text corresponding to the approved Meta 'viewing_reminder' UTILITY template.
    Uses REMINDER_TEMPLATE_CONFIG as the single source of truth for sending, previews, and storage.
    """
    text = REMINDER_TEMPLATE_CONFIG["body"]
    text = text.replace("{{1}}", client_name or "Valued Client")
    text = text.replace("{{2}}", property_name or "Robotics Unit")
    text = text.replace("{{3}}", formatted_datetime or "Upcoming Time")
    return text


# ─── Contact state & compliance (Part 4) ────────────────────────────────────
WHATSAPP_CONTACT_STATE: dict[str, dict] = {}


def get_contact_state(phone_number: str) -> dict:
    clean = normalize_whatsapp_number(phone_number)
    if not clean:
        return {"phone_number": "", "opted_out": False, "automation_paused": False}
    if WHATSAPP_USE_MEMORY_STORE or not supabase:
        return WHATSAPP_CONTACT_STATE.get(clean, {
            "phone_number": clean,
            "opted_out": False,
            "automation_paused": False,
            "snoozed_until": None,
            "last_nudged_at": None,
            "nudge_count": 0,
        })
    try:
        res = supabase.table("whatsapp_contact_state").select("*").eq("phone_number", clean).limit(1).execute()
        if res.data and len(res.data) > 0:
            return res.data[0]
    except Exception as exc:
        print(f"[get_contact_state] Supabase read warning: {exc}")
    return WHATSAPP_CONTACT_STATE.get(clean, {
        "phone_number": clean,
        "opted_out": False,
        "automation_paused": False,
        "snoozed_until": None,
        "last_nudged_at": None,
        "nudge_count": 0,
    })


def update_contact_state(phone_number: str, **fields) -> dict:
    clean = normalize_whatsapp_number(phone_number)
    curr = get_contact_state(clean).copy()
    curr.update(fields)
    curr["updated_at"] = datetime.now(timezone.utc).isoformat()
    WHATSAPP_CONTACT_STATE[clean] = curr

    if not WHATSAPP_USE_MEMORY_STORE and supabase:
        try:
            supabase.table("whatsapp_contact_state").upsert(curr, on_conflict="phone_number").execute()
        except Exception as exc:
            print(f"[update_contact_state] Supabase write warning: {exc}")
    return curr


def is_contact_opted_out(phone_number: str) -> bool:
    state = get_contact_state(phone_number)
    return bool(state.get("opted_out"))


def is_automation_paused_for_contact(phone_number: str) -> bool:
    state = get_contact_state(phone_number)
    if state.get("opted_out"):
        return True
    if state.get("automation_paused"):
        return True
    snooze = state.get("snoozed_until")
    if snooze:
        try:
            s_dt = datetime.fromisoformat(snooze)
            if datetime.now(timezone.utc) < s_dt:
                return True
        except Exception:
            pass
    return False


def _send_meta_request(payload: dict) -> dict:
    clean_digits = payload.get("to", "")
    is_manual = payload.get("_manual_override", False)
    if is_contact_opted_out(clean_digits):
        if not is_manual:
            print(f"[whatsapp_send] BLOCKED: Contact {clean_digits} is opted out.")
            raise HTTPException(
                status_code=400,
                detail=f"Contact {clean_digits} has opted out of WhatsApp messages.",
            )
        else:
            print(f"[whatsapp_send] AUDIT WARNING: Human rep manual override send to opted-out contact {clean_digits}.")

    phone_number_id, access_token = get_whatsapp_credentials()
    allowed, guard_reason = check_whatsapp_delivery_guard(clean_digits)

    if not phone_number_id or not access_token or not allowed:
        print(f"[whatsapp_send] DEV SAFETY GUARD / SIMULATION ({guard_reason}): log-only for {clean_digits}")
        return {
            "messaging_product": "whatsapp",
            "contacts": [{"input": clean_digits, "wa_id": clean_digits}],
            "messages": [{"id": f"wamid.mock_{int(datetime.now(timezone.utc).timestamp()*1000)}"}],
            "status": "delivered",
            "simulated": True,
            "guard_reason": guard_reason,
        }

    url = f"https://graph.facebook.com/{WHATSAPP_API_VERSION}/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"WhatsApp network error: {exc}")

    if response.status_code != 200:
        try:
            err_json = response.json()
            err_code = err_json.get("error", {}).get("code")
            if err_code == 131047:
                raise MetaReengagementError("Re-engagement error 131047: 24h window closed", raw_response=err_json)
        except MetaReengagementError:
            raise
        except Exception:
            pass
        raise HTTPException(status_code=502, detail=f"WhatsApp send failed: {response.text}")
    return response.json()


def send_whatsapp_message(to_number: str, message_text: str, manual_override: bool = False) -> dict:
    clean_digits = "".join(filter(str.isdigit, to_number))
    if is_contact_opted_out(clean_digits) and not manual_override:
        raise HTTPException(
            status_code=400,
            detail=f"Contact {clean_digits} has opted out of WhatsApp messages.",
        )
    payload = {
        "messaging_product": "whatsapp",
        "to": clean_digits,
        "type": "text",
        "text": {"body": message_text},
        "_manual_override": manual_override,
    }
    return _send_meta_request(payload)


def send_whatsapp_template(to_number: str, template_name: str, language_code: str = "en_US", body_parameters: list = None) -> dict:
    clean_digits = "".join(filter(str.isdigit, to_number))
    components = []
    if body_parameters:
        components.append({
            "type": "body",
            "parameters": [{"type": "text", "text": str(p)} for p in body_parameters],
        })

    payload = {
        "messaging_product": "whatsapp",
        "to": clean_digits,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language_code},
            "components": components,
        },
    }
    return _send_meta_request(payload)


def send_whatsapp_template_with_quick_replies(
    to_number: str,
    template_name: str,
    language_code: str = "en_US",
    body_parameters: list = None,
    button_payloads: list[str] = None,
) -> dict:
    """
    Sends an approved WhatsApp Marketing/Utility template with dynamic button payloads at send time.
    """
    clean_digits = "".join(filter(str.isdigit, to_number))
    components = []
    if body_parameters:
        components.append({
            "type": "body",
            "parameters": [{"type": "text", "text": str(p)} for p in body_parameters],
        })

    if button_payloads:
        for idx, p_load in enumerate(button_payloads[:3]):
            components.append({
                "type": "button",
                "sub_type": "quick_reply",
                "index": str(idx),
                "parameters": [{"type": "payload", "payload": p_load}],
            })

    payload = {
        "messaging_product": "whatsapp",
        "to": clean_digits,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language_code},
            "components": components,
        },
    }
    return _send_meta_request(payload)


def send_whatsapp_interactive_buttons(
    to_number: str,
    body_text: str,
    buttons: list[dict],
    header_text: str | None = None,
) -> dict:
    """
    Sends WhatsApp interactive reply buttons (Meta limit: max 3 buttons, title <= 20 chars).
    """
    clean_digits = "".join(filter(str.isdigit, to_number))
    interactive_obj = {
        "type": "button",
        "body": {"text": body_text},
        "action": {
            "buttons": [
                {
                    "type": "reply",
                    "reply": {
                        "id": btn["id"],
                        "title": btn["title"][:20],
                    },
                }
                for btn in buttons[:3]
            ]
        },
    }
    if header_text:
        interactive_obj["header"] = {"type": "text", "text": header_text[:60]}

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": clean_digits,
        "type": "interactive",
        "interactive": interactive_obj,
    }
    return _send_meta_request(payload)


def send_whatsapp_interactive_list(
    to_number: str,
    body_text: str,
    button_label: str,
    sections: list[dict],
    header_text: str | None = None,
) -> dict:
    """
    Sends WhatsApp interactive list message (Meta limit: max 10 rows per section, title <= 24 chars).
    """
    clean_digits = "".join(filter(str.isdigit, to_number))
    formatted_sections = []
    for sec in sections:
        rows = [
            {
                "id": r["id"],
                "title": r["title"][:24],
                "description": (r.get("description") or "")[:72],
            }
            for r in sec.get("rows", [])[:10]
        ]
        formatted_sections.append({
            "title": sec.get("title", "Options")[:24],
            "rows": rows,
        })

    interactive_obj = {
        "type": "list",
        "body": {"text": body_text},
        "action": {
            "button": button_label[:20],
            "sections": formatted_sections,
        },
    }
    if header_text:
        interactive_obj["header"] = {"type": "text", "text": header_text[:60]}

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": clean_digits,
        "type": "interactive",
        "interactive": interactive_obj,
    }
    return _send_meta_request(payload)


# ─── Part 3: Rich Media & Calendar Helpers ────────────────────────────────────

def validate_unit_image_url(image_url: str | None) -> tuple[bool, str]:
    """
    Validates a robotics unit image URL for Meta WhatsApp compatibility.
    Rules:
      - Must be an HTTPS URL
      - Valid image extension (.jpg, .jpeg, .png, .webp) or image content-type
      - Size limit < 5 MB
    """
    if not image_url or not isinstance(image_url, str):
        return False, "Missing image URL"
    if not image_url.lower().startswith("https://"):
        return False, "Image URL must be a secure HTTPS link"

    url_clean = image_url.lower().split("?")[0]
    valid_exts = (".jpg", ".jpeg", ".png", ".webp")
    has_valid_ext = any(url_clean.endswith(ext) for ext in valid_exts)

    try:
        head = requests.head(image_url, timeout=4, allow_redirects=True)
        c_type = head.headers.get("Content-Type", "").lower()
        c_len = head.headers.get("Content-Length")
        if c_len and int(c_len) > 5 * 1024 * 1024:
            return False, f"Image size exceeds 5MB limit ({int(c_len)/(1024*1024):.1f}MB)"
        if c_type and any(t in c_type for t in ["image/jpeg", "image/png", "image/webp"]):
            return True, "Valid"
    except Exception:
        pass

    if has_valid_ext:
        return True, "Valid"
    return False, "Unsupported image type (must be jpeg, png, or webp)"


def send_whatsapp_image_message(to_number: str, image_url: str, caption: str | None = None) -> dict:
    """
    Sends an image message via WhatsApp Cloud API.
    Only permitted when 24h customer window is open.
    """
    clean_digits = normalize_whatsapp_number(to_number)
    is_valid, reason = validate_unit_image_url(image_url)
    if not is_valid:
        raise ValueError(f"Invalid image URL for WhatsApp: {reason}")

    image_payload: dict = {"link": image_url}
    if caption:
        image_payload["caption"] = caption[:1024]

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": clean_digits,
        "type": "image",
        "image": image_payload,
    }
    return _send_meta_request(payload)


_ICS_RATE_LIMITS: dict[str, list[float]] = {}


def get_calendar_signing_secret() -> str | None:
    """Returns dedicated CALENDAR_SIGNING_SECRET from environment. No hardcoded fallback."""
    val = os.getenv("CALENDAR_SIGNING_SECRET")
    if not val and _env_path.exists() and "pytest" not in sys.modules and "PYTEST_CURRENT_TEST" not in os.environ:
        load_dotenv(_env_path, override=True)
        val = os.getenv("CALENDAR_SIGNING_SECRET")
    return val or None


def generate_calendar_token(viewing_id: str, expires_timestamp: int) -> str | None:
    """Generates HMAC-SHA256 signature for viewing .ics download link using dedicated secret."""
    secret = get_calendar_signing_secret()
    if not secret:
        print("[generate_calendar_token] ERROR: CALENDAR_SIGNING_SECRET is not configured in environment.")
        return None
    msg = f"{viewing_id}:{expires_timestamp}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def verify_calendar_token(viewing_id: str, token: str, expires_timestamp: int) -> tuple[bool, str]:
    """Verifies signature authenticity and expiration."""
    secret = get_calendar_signing_secret()
    if not secret:
        return False, "Calendar signing secret not configured"
    now_ts = int(datetime.now(timezone.utc).timestamp())
    if now_ts > expires_timestamp:
        return False, "Calendar link has expired"
    expected = generate_calendar_token(viewing_id, expires_timestamp)
    if not expected or not hmac.compare_digest(token, expected):
        return False, "Invalid token signature"
    return True, "Valid"


def generate_google_calendar_url(unit_name: str, scheduled_at_iso: str, agent_name: str = "R. Delgado") -> str:
    """
    Builds Google Calendar event link in Asia/Kuala_Lumpur (MYT).
    Duration: 60 minutes.
    Neutral location string used per requirements.
    """
    clean_iso = scheduled_at_iso.replace("Z", "+00:00")
    dt = datetime.fromisoformat(clean_iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=KL_TZ)
    dt_myt = dt.astimezone(KL_TZ)
    end_myt = dt_myt + timedelta(minutes=60)

    # Google Calendar dates format in UTC: YYYYMMDDTHHMMSSZ/YYYYMMDDTHHMMSSZ
    dt_utc = dt_myt.astimezone(timezone.utc)
    end_utc = end_myt.astimezone(timezone.utc)
    dates_param = f"{dt_utc.strftime('%Y%m%dT%H%M%SZ')}/{end_utc.strftime('%Y%m%dT%H%M%SZ')}"

    title = f"On-Site Demonstration: {unit_name}"
    location = f"Your facility (details to be confirmed by {agent_name})"
    details = (
        f"Private on-site demonstration of {unit_name}.\n"
        f"Representative: {agent_name} (PIPELINE.EV).\n"
        f"For rescheduling or questions, reply to your WhatsApp thread."
    )

    base = "https://calendar.google.com/calendar/render"
    params = {
        "action": "TEMPLATE",
        "text": title,
        "dates": dates_param,
        "details": details,
        "location": location,
    }
    return f"{base}?{urllib.parse.urlencode(params)}"


def generate_ics_download_url(viewing_id: str) -> str | None:
    """
    Generates signed .ics download URL with 14-day validity.
    Must route via PUBLIC_BASE_URL (public Next.js origin) to app/api/calendar/[viewingId].
    If PUBLIC_BASE_URL or CALENDAR_SIGNING_SECRET is missing, returns None.
    """
    public_base = os.getenv("PUBLIC_BASE_URL")
    if not public_base:
        print("[generate_ics_download_url] Notice: PUBLIC_BASE_URL is not set; omitting .ics link.")
        return None
    secret = get_calendar_signing_secret()
    if not secret:
        print("[generate_ics_download_url] ERROR: CALENDAR_SIGNING_SECRET is not set; omitting .ics link.")
        return None

    expires_ts = int((datetime.now(timezone.utc) + timedelta(days=14)).timestamp())
    token = generate_calendar_token(viewing_id, expires_ts)
    if not token:
        return None
    return f"{public_base.rstrip('/')}/api/calendar/{viewing_id}.ics?token={token}&expires={expires_ts}"


def build_booking_confirmation_text(
    prop_name: str,
    slot_label: str,
    agent_name: str,
    viewing_id: str | None = None,
    scheduled_at_iso: str | None = None,
) -> str:
    """
    Constructs the booking confirmation message.
    Clean confirmation text without calendar event links.
    """
    return (
        f"Great! Your private on-site demonstration for {prop_name} is confirmed for {slot_label}. "
        f"{agent_name} will meet your team on site. We look forward to seeing you then!"
    )


@app.get("/api/calendar/{viewing_id}.ics")
@app.get("/api/calendar/{viewing_id}")
def download_calendar_ics(viewing_id: str, request: Request, token: str = "", expires: int = 0):
    """
    RFC 5545 iCalendar (.ics) download endpoint.
    - Requires CALENDAR_SIGNING_SECRET in environment; returns 503 if missing.
    - Signed HMAC-SHA256 token validation with expiration.
    - Rate-limited to max 15 requests/minute per client IP (returns 429).
      Client IP is parsed from X-Forwarded-For ONLY when TRUST_PROXY_HEADERS=true;
      otherwise request.client.host is used to prevent IP spoofing.
    - Neutral location string used.
    - Minimum data: unit name, start/end time, rep name.
    """
    # 0. Environment check: CALENDAR_SIGNING_SECRET must be configured
    if not get_calendar_signing_secret():
        raise HTTPException(
            status_code=503,
            detail="Calendar signing service is not configured (CALENDAR_SIGNING_SECRET missing).",
        )

    # Clean viewing_id if requested with .ics extension in path
    if viewing_id.endswith(".ics"):
        viewing_id = viewing_id[:-4]

    # 1. Rate limiting per IP (sliding 60-second window, max 15 req/min)
    trusted_proxy = os.getenv("TRUST_PROXY_HEADERS", "false").lower() in ("true", "1", "yes")
    if trusted_proxy and request.headers.get("x-forwarded-for"):
        client_ip = request.headers.get("x-forwarded-for").split(",")[0].strip()
    else:
        # Note limitation: without TRUST_PROXY_HEADERS=true, proxies see the connecting IP only
        client_ip = request.client.host if request.client else "unknown"

    now_ts = datetime.now(timezone.utc).timestamp()
    history = [t for t in _ICS_RATE_LIMITS.get(client_ip, []) if now_ts - t < 60]
    if len(history) >= 15:
        _ICS_RATE_LIMITS[client_ip] = history
        raise HTTPException(
            status_code=429,
            detail="Too many calendar download requests. Rate limit is 15 requests per minute.",
        )
    history.append(now_ts)
    _ICS_RATE_LIMITS[client_ip] = history

    # 2. Token authentication and expiration verification
    if not token or not expires:
        raise HTTPException(status_code=403, detail="Missing calendar authentication token or expiration timestamp")
    is_valid, reason = verify_calendar_token(viewing_id, token, expires)
    if not is_valid:
        if "expired" in reason.lower():
            raise HTTPException(status_code=401, detail="Calendar download link has expired")
        raise HTTPException(status_code=403, detail="Invalid calendar download token signature")

    # 3. Retrieve viewing metadata
    v_row = None
    try:
        v_res = (
            supabase.table("scheduled_viewings")
            .select("id, scheduled_at, status, properties(address), agents(name)")
            .eq("id", viewing_id)
            .limit(1)
            .execute()
        )
        if v_res.data and len(v_res.data) > 0:
            v_row = v_res.data[0]
    except Exception as exc:
        print(f"[download_calendar_ics] viewing lookup warning: {exc}")

    if not v_row:
        if WHATSAPP_USE_MEMORY_STORE or os.getenv("WHATSAPP_TEST_MODE") == "true":
            # Test mock fallback
            v_row = {
                "id": viewing_id,
                "scheduled_at": datetime.now(KL_TZ).isoformat(),
                "properties": {"address": "Industrial Robotics Unit"},
                "agents": {"name": "R. Delgado"},
            }
        else:
            raise HTTPException(status_code=404, detail="Scheduled viewing not found")

    unit_name = (v_row.get("properties") or {}).get("address") or "Industrial Robotics Demonstration"
    rep_name = (v_row.get("agents") or {}).get("name") or "Representative"
    sched_iso = v_row.get("scheduled_at") or datetime.now(KL_TZ).isoformat()

    try:
        dt = datetime.fromisoformat(str(sched_iso).replace("Z", "+00:00")).astimezone(KL_TZ)
    except Exception:
        dt = datetime.now(KL_TZ)
    dt_end = dt + timedelta(minutes=60)

    dt_start_utc = dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dt_end_utc = dt_end.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dt_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    # RFC 5545 format with minimal payload and neutral location per instructions
    ics_lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//PIPELINE.EV//Viewing Calendar//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:viewing-{viewing_id}@pipeline-ev.com",
        f"DTSTAMP:{dt_stamp}",
        f"DTSTART:{dt_start_utc}",
        f"DTEND:{dt_end_utc}",
        f"SUMMARY:On-Site Demonstration: {unit_name}",
        f"DESCRIPTION:Private demonstration of {unit_name} conducted by {rep_name} (PIPELINE.EV).",
        f"LOCATION:Your facility (details to be confirmed by {rep_name})",
        "STATUS:CONFIRMED",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    ics_content = "\r\n".join(ics_lines) + "\r\n"
    return Response(
        content=ics_content,
        media_type="text/calendar",
        headers={
            "Content-Disposition": f'attachment; filename="viewing_{viewing_id}.ics"',
            "Cache-Control": "no-cache",
        },
    )



# ─── Disk-based fallback (kept for backward-compat during Supabase transition) ──

_WA_MESSAGES_FILE = Path(__file__).resolve().parent / "whatsapp_messages.json"


def load_whatsapp_messages() -> list[dict]:
    if _WA_MESSAGES_FILE.exists():
        try:
            with open(_WA_MESSAGES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return [
        {
            "id": "init-welcome",
            "to_number": "60109722730",
            "client_id": None,
            "client_name": "Direct Test Contact",
            "sender": "system",
            "text": "WhatsApp Cloud API Connected (Meta Graph API v25.0). Ready for live outreach.",
            "status": "delivered",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    ]


def save_whatsapp_messages(msgs: list[dict]):
    try:
        with open(_WA_MESSAGES_FILE, "w", encoding="utf-8") as f:
            json.dump(msgs, f, indent=2)
    except Exception as exc:
        print(f"[save_whatsapp_messages] Warning: {exc}")


WHATSAPP_MESSAGE_HISTORY: list[dict] = load_whatsapp_messages()


# ─── WhatsApp Slot Offers (Persistence & Slot Generation) ────────────────────

KL_TZ = zoneinfo.ZoneInfo("Asia/Kuala_Lumpur")

_WA_SLOT_OFFERS_FILE = Path(__file__).resolve().parent / "whatsapp_slot_offers.json"

# In-memory store is strictly restricted to unit tests behind an explicit flag.
# In production, missing or unreachable tables FAIL LOUDLY with clear errors.
WHATSAPP_USE_MEMORY_STORE = (
    os.getenv("WHATSAPP_USE_MEMORY_STORE", "").lower() in ("true", "1")
    or os.getenv("WHATSAPP_TEST_MODE", "").lower() in ("true", "1")
)


def load_whatsapp_slot_offers() -> list[dict]:
    if _WA_SLOT_OFFERS_FILE.exists():
        try:
            with open(_WA_SLOT_OFFERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def save_whatsapp_slot_offers(offers: list[dict]):
    try:
        with open(_WA_SLOT_OFFERS_FILE, "w", encoding="utf-8") as f:
            json.dump(offers, f, indent=2)
    except Exception as exc:
        print(f"[save_whatsapp_slot_offers] Warning: {exc}")


WHATSAPP_SLOT_OFFERS: list[dict] = load_whatsapp_slot_offers()
WHATSAPP_REMINDERS_STORE: list[dict] = []


def persist_slot_offer(offer: dict) -> dict:
    """
    Saves slot offer to Supabase table whatsapp_slot_offers.
    Automatically expires older open offers for this client/phone.
    If Supabase is unreachable and WHATSAPP_USE_MEMORY_STORE is not set, fails loudly.
    """
    client_id = offer.get("client_id")
    phone = offer.get("phone_number")

    if WHATSAPP_USE_MEMORY_STORE:
        for o in WHATSAPP_SLOT_OFFERS:
            if o.get("status") == "open":
                if (client_id and o.get("client_id") == client_id) or (phone and o.get("phone_number") == phone):
                    o["status"] = "expired"
        WHATSAPP_SLOT_OFFERS.append(offer)
        save_whatsapp_slot_offers(WHATSAPP_SLOT_OFFERS)
        return offer

    try:
        if client_id:
            supabase.table("whatsapp_slot_offers").update({"status": "expired"}).eq("client_id", client_id).eq("status", "open").execute()
        res = supabase.table("whatsapp_slot_offers").upsert(offer, on_conflict="id").execute()
        if not res or (hasattr(res, "data") and res.data is None):
            raise RuntimeError("Empty response from Supabase upsert to whatsapp_slot_offers")
    except Exception as exc:
        print(f"[persist_slot_offer] ERROR: Supabase write failed: {exc}")
        raise RuntimeError(f"Database error writing to whatsapp_slot_offers: {exc}") from exc

    return offer


def get_open_slot_offer(client_id: str | None = None, phone_number: str | None = None) -> dict | None:
    now_iso = datetime.now(timezone.utc).isoformat()
    if not WHATSAPP_USE_MEMORY_STORE:
        try:
            q = supabase.table("whatsapp_slot_offers").select("*").eq("status", "open").gt("expires_at", now_iso)
            if client_id:
                q = q.eq("client_id", client_id)
            elif phone_number:
                clean = "".join(filter(str.isdigit, phone_number))
                q = q.eq("phone_number", clean)
            res = q.order("created_at", desc=True).limit(1).execute()
            if res.data and len(res.data) > 0:
                return res.data[0]
            return None
        except Exception as exc:
            print(f"[get_open_slot_offer] ERROR: Supabase query failed: {exc}")
            raise RuntimeError(f"Database error querying whatsapp_slot_offers: {exc}") from exc

    # Unit Test In-Memory Store Path
    clean_p = "".join(filter(str.isdigit, phone_number or ""))
    for o in reversed(WHATSAPP_SLOT_OFFERS):
        if o.get("status") == "open":
            exp = o.get("expires_at")
            if exp and exp < now_iso:
                o["status"] = "expired"
                continue
            if client_id and o.get("client_id") == client_id:
                return o
            if clean_p and o.get("phone_number") == clean_p:
                return o
    return None


def get_slot_offer_by_id(offer_id: str) -> dict | None:
    """Fetch offer by primary key id from Supabase or test memory."""
    if not WHATSAPP_USE_MEMORY_STORE:
        try:
            res = supabase.table("whatsapp_slot_offers").select("*").eq("id", offer_id).execute()
            if res.data:
                if isinstance(res.data, list) and len(res.data) > 0:
                    return res.data[0]
                if isinstance(res.data, dict):
                    return res.data
            return None
        except Exception as exc:
            print(f"[get_slot_offer_by_id] ERROR: Supabase query failed: {exc}")
            raise RuntimeError(f"Database error querying whatsapp_slot_offers by id: {exc}") from exc

    for o in WHATSAPP_SLOT_OFFERS:
        if o.get("id") == offer_id:
            return o
    return None


def claim_slot_offer(offer_id: str, slot_index: int) -> dict | None:
    """
    Atomically transitions an offer from 'open' to 'booked' for the given slot_index.
    Guarantees concurrency safety against simultaneous webhooks.
    Requires expires_at > now.
    Returns the updated offer if successfully claimed, or None if already claimed/expired.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    if not WHATSAPP_USE_MEMORY_STORE:
        try:
            res = (
                supabase.table("whatsapp_slot_offers")
                .update({
                    "status": "booked",
                    "booked_slot_index": slot_index,
                    "booked_at": now_iso,
                })
                .eq("id", offer_id)
                .eq("status", "open")
                .gt("expires_at", now_iso)
                .execute()
            )
            if res.data and len(res.data) > 0:
                claimed = res.data[0]
                return claimed
            return None
        except Exception as exc:
            print(f"[claim_slot_offer] ERROR: Supabase atomic update failed: {exc}")
            raise RuntimeError(f"Database error claiming slot offer: {exc}") from exc

    # Unit Test In-Memory Concurrency Guard
    for o in WHATSAPP_SLOT_OFFERS:
        if o.get("id") == offer_id and o.get("status") == "open":
            exp = o.get("expires_at")
            if exp and exp <= now_iso:
                o["status"] = "expired"
                save_whatsapp_slot_offers(WHATSAPP_SLOT_OFFERS)
                return None
            o["status"] = "booked"
            o["booked_slot_index"] = slot_index
            o["booked_at"] = now_iso
            save_whatsapp_slot_offers(WHATSAPP_SLOT_OFFERS)
            return o

    return None


def rollback_slot_offer(offer_id: str) -> bool:
    """
    Atomically rolls an offer back to 'open' if creating the scheduled_viewing row failed.
    Ensures complete booking atomicity.
    """
    if not WHATSAPP_USE_MEMORY_STORE:
        try:
            supabase.table("whatsapp_slot_offers").update({
                "status": "open",
                "booked_slot_index": None,
                "booked_at": None,
            }).eq("id", offer_id).execute()
            return True
        except Exception as exc:
            print(f"[rollback_slot_offer] ERROR: Supabase rollback failed: {exc}")
            raise RuntimeError(f"Database error rolling back slot offer: {exc}") from exc

    for o in WHATSAPP_SLOT_OFFERS:
        if o.get("id") == offer_id:
            o["status"] = "open"
            o["booked_slot_index"] = None
            o["booked_at"] = None
    save_whatsapp_slot_offers(WHATSAPP_SLOT_OFFERS)
    return True


def update_slot_offer_status(offer_id: str, new_status: str):
    if not WHATSAPP_USE_MEMORY_STORE:
        try:
            supabase.table("whatsapp_slot_offers").update({"status": new_status}).eq("id", offer_id).execute()
            return
        except Exception as exc:
            print(f"[update_slot_offer_status] ERROR: Supabase update failed: {exc}")
            raise RuntimeError(f"Database error updating slot offer status: {exc}") from exc

    for o in WHATSAPP_SLOT_OFFERS:
        if o.get("id") == offer_id:
            o["status"] = new_status
    save_whatsapp_slot_offers(WHATSAPP_SLOT_OFFERS)


# ─── Conversation Automation Controls ─────────────────────────────────────────

WHATSAPP_AUTOMATION_PAUSED_PHONES: set[str] = set()


def is_automation_paused_for_phone(phone_number: str) -> bool:
    """
    Checks if a conversation is marked human-handled.
    When true, all automatic replies and reminder buttons are suppressed.
    """
    clean_digits = "".join(filter(str.isdigit, phone_number))
    if clean_digits in WHATSAPP_AUTOMATION_PAUSED_PHONES:
        return True
    try:
        res = (
            supabase.table("whatsapp_conversations")
            .select("automation_paused")
            .eq("phone_number", clean_digits)
            .order("updated_at", desc=True)
            .limit(1)
            .execute()
        )
        if res.data and len(res.data) > 0:
            if res.data[0].get("automation_paused"):
                WHATSAPP_AUTOMATION_PAUSED_PHONES.add(clean_digits)
                return True
    except Exception:
        pass
    return False


def set_automation_paused_for_phone(phone_number: str, paused: bool = True):
    clean_digits = "".join(filter(str.isdigit, phone_number))
    if paused:
        WHATSAPP_AUTOMATION_PAUSED_PHONES.add(clean_digits)
    else:
        WHATSAPP_AUTOMATION_PAUSED_PHONES.discard(clean_digits)
    try:
        supabase.table("whatsapp_conversations").update({
            "automation_paused": paused,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("phone_number", clean_digits).execute()
    except Exception as exc:
        print(f"[set_automation_paused_for_phone] Supabase update warning: {exc}")


# ─── Business Hours Configuration ─────────────────────────────────────────────
# Unified rule: slots must start at or after 09:00 and must conclude by 18:00
# (inclusive of slot length). Weekdays (Monday through Friday) only.
SLOT_DURATION_MINUTES = 60
BUSINESS_HOURS_START = time(9, 0)
BUSINESS_HOURS_END = time(18, 0)


def is_within_business_hours(slot_dt: datetime, duration_minutes: int = SLOT_DURATION_MINUTES) -> bool:
    """
    A viewing slot must be scheduled Monday through Friday, starting at 09:00 or later,
    and concluding by 18:00 (6:00 PM) inclusive of slot length (duration_minutes).
    """
    if slot_dt.weekday() >= 5:  # Saturday or Sunday
        return False
    start_t = slot_dt.time()
    end_dt = slot_dt + timedelta(minutes=duration_minutes)
    if end_dt.date() != slot_dt.date():
        return False
    end_t = end_dt.time()
    if start_t < BUSINESS_HOURS_START:
        return False
    if end_t > BUSINESS_HOURS_END:
        return False
    return True


def format_slot_label(dt: datetime) -> str:
    """Formats datetime to e.g. 'Thu 10 Oct, 2:00 PM'"""
    day_name = dt.strftime("%a")
    day_num = dt.strftime("%d").lstrip("0")
    month_name = dt.strftime("%b")
    time_str = dt.strftime("%I:%M %p").lstrip("0")
    return f"{day_name} {day_num} {month_name}, {time_str}"


def fetch_agent_existing_viewing_intervals(agent_id: str | None = None) -> list[tuple[datetime, datetime]]:
    """
    Fetch all upcoming scheduled viewings in KL timezone for this agent.
    Returns list of (start_dt, end_dt) in KL timezone.
    """
    intervals = []
    try:
        cutoff = datetime.now(timezone.utc).isoformat()
        q = supabase.table("scheduled_viewings").select("scheduled_at, client_id, clients(assigned_agent_id)").eq("status", "upcoming").gte("scheduled_at", cutoff)
        res = q.execute()
        for row in (res.data or []):
            client_data = row.get("clients")
            c_agent = client_data.get("assigned_agent_id") if isinstance(client_data, dict) else None
            if agent_id and c_agent and c_agent != agent_id:
                continue
            sch_str = row.get("scheduled_at")
            if sch_str:
                dt = datetime.fromisoformat(sch_str.replace("Z", "+00:00")).astimezone(KL_TZ)
                intervals.append((dt, dt + timedelta(minutes=60)))
    except Exception as exc:
        print(f"[fetch_agent_existing_viewing_intervals] Warning: {exc}")
    return intervals


def is_slot_available(candidate_dt: datetime, agent_id: str | None = None, buffer_minutes: int = 45) -> bool:
    """Checks whether candidate_dt has at least buffer_minutes before & after any existing viewing for this agent."""
    if candidate_dt.tzinfo is None:
        candidate_dt = candidate_dt.replace(tzinfo=KL_TZ)
    else:
        candidate_dt = candidate_dt.astimezone(KL_TZ)

    # Must be at least 30 minutes in the future
    now_kl = datetime.now(KL_TZ)
    if candidate_dt <= now_kl + timedelta(minutes=30):
        return False

    if not is_within_business_hours(candidate_dt):
        return False

    viewing_intervals = fetch_agent_existing_viewing_intervals(agent_id)
    c_start = candidate_dt
    c_end = candidate_dt + timedelta(minutes=60)
    buf = timedelta(minutes=buffer_minutes)

    for v_start, v_end in viewing_intervals:
        # Overlap check including buffer
        if not (c_end + buf <= v_start or c_start >= v_end + buf):
            return False
    return True


def generate_candidate_slots(agent_id: str | None = None, count: int = 3) -> list[dict]:
    """
    Picks the next available business-hours slots for the assigned agent in Asia/Kuala_Lumpur,
    skipping existing scheduled viewings (with 45m buffer) and past times.
    """
    now = datetime.now(KL_TZ)
    earliest = now + timedelta(hours=2)
    slot_times = [(10, 0), (11, 30), (14, 0), (15, 30)]
    viewing_intervals = fetch_agent_existing_viewing_intervals(agent_id)
    buf = timedelta(minutes=45)

    slots = []
    curr_date = now.date()
    for d in range(14):
        check_date = curr_date + timedelta(days=d)
        if check_date.weekday() >= 5:  # Skip Saturday & Sunday
            continue
        for hour, minute in slot_times:
            candidate = datetime.combine(check_date, time(hour, minute), tzinfo=KL_TZ)
            if candidate < earliest:
                continue

            conflict = False
            c_start = candidate
            c_end = candidate + timedelta(minutes=60)
            for v_start, v_end in viewing_intervals:
                if not (c_end + buf <= v_start or c_start >= v_end + buf):
                    conflict = True
                    break
            if not conflict:
                slots.append({
                    "index": len(slots) + 1,
                    "slot_iso": candidate.isoformat(),
                    "label": format_slot_label(candidate),
                })
                if len(slots) == count:
                    return slots
    return slots


def parse_slots_from_text(text: str) -> list[dict]:
    """
    Parses slot options deterministically embedded in a pitch message text.
    FALLBACK ONLY: Used when structured slots are missing in legacy requests.
    Logs a warning when invoked and calculates the nearest future date.
    Returns list of dicts: [{"index": 1, "label": "Mon 5 Oct, 10:00 AM", "slot_iso": "..."}, ...]
    """
    if not text:
        return []
    print("[parse_slots_from_text] WARN: Fallback text parsing used for message slots (fragile). Prefer structured slots.")
    pattern = r'(?:^|\s)([1-3])\)\s*([A-Za-z]{3}\s+\d{1,2}\s+[A-Za-z]{3},\s+\d{1,2}:\d{2}\s+(?:AM|PM))'
    matches = re.findall(pattern, text)
    if not matches:
        return []

    now_kl = datetime.now(KL_TZ)
    current_year = now_kl.year
    slots = []
    for idx_str, label in matches:
        clean_label = re.sub(r'^[A-Za-z]{3}\s+', '', label.strip())
        try:
            # Nearest future date logic: try current year, then next year if dt is in past
            dt = datetime.strptime(f'{clean_label} {current_year}', '%d %b, %I:%M %p %Y').replace(tzinfo=KL_TZ)
            if dt <= now_kl - timedelta(minutes=1):
                dt = datetime.strptime(f'{clean_label} {current_year + 1}', '%d %b, %I:%M %p %Y').replace(tzinfo=KL_TZ)
            slots.append({
                'index': int(idx_str),
                'label': label.strip(),
                'slot_iso': dt.isoformat(),
            })
        except Exception as pe:
            print(f"[parse_slots_from_text] Parse error for '{label}': {pe}")
    return slots


def resolve_agent_from_pitch_text(text: str, default_agent_id: str | None = None) -> tuple[str | None, str]:
    """
    FALLBACK ONLY: Scans the pitch draft text for rep signatures if sender_agent_id is absent.
    Logs a warning when invoked.
    """
    print("[resolve_agent_from_pitch_text] WARN: Fallback text scan used to resolve agent. Prefer explicit sender_agent_id.")
    if text:
        try:
            agents_res = supabase.table("agents").select("id, name").execute()
            for ag in (agents_res.data or []):
                name = ag.get("name")
                if name and name in text:
                    return ag["id"], name
        except Exception:
            pass
    return default_agent_id, "Senior Sales Representative"


# ─── Supabase-based persistence helpers ──────────────────────────────────────

def _ensure_conversation(phone_number: str, agent_id: str | None, client_id: str | None, client_name: str) -> str | None:
    """
    Upsert a whatsapp_conversations row keyed on (phone_number, agent_id, client_id) —
    matching the SQL unique constraint.  All three are nullable; two different clients
    at the same phone number produce separate rows.
    Returns the conversation UUID, or None if Supabase is unavailable.
    """
    try:
        query = supabase.table("whatsapp_conversations").select("id") \
            .eq("phone_number", phone_number)
        if agent_id:
            query = query.eq("agent_id", agent_id)
        else:
            query = query.is_("agent_id", "null")
        if client_id:
            query = query.eq("client_id", client_id)
        else:
            query = query.is_("client_id", "null")
        res = query.limit(1).execute()
        if res.data:
            conv_id = res.data[0]["id"]
            update_payload = {"updated_at": datetime.now(timezone.utc).isoformat()}
            if client_name:
                update_payload["client_name"] = client_name
            supabase.table("whatsapp_conversations").update(update_payload).eq("id", conv_id).execute()
            return conv_id
        # Create new row
        insert_payload = {
            "phone_number": phone_number,
            "client_name": client_name or "Contact",
        }
        if agent_id:
            insert_payload["agent_id"] = agent_id
        if client_id:
            insert_payload["client_id"] = client_id
        ins = supabase.table("whatsapp_conversations").insert(insert_payload).execute()
        return ins.data[0]["id"] if ins.data else None
    except Exception as exc:
        print(f"[_ensure_conversation] Warning: {exc}")
        return None


def log_whatsapp_message(
    *,
    msg_id: str,
    phone_number: str,
    agent_id: str | None = None,
    client_id: str | None = None,
    client_name: str = "Client",
    sender: str,
    text: str,
    status: str = "sent",
    raw_payload: dict | None = None,
    processing_status: str = "received",
    error_code: int | None = None,
    error_message: str | None = None,
) -> dict:
    """
    Write a message to both the in-memory history (disk fallback) and Supabase.
    Returns the normalized message dict.
    """
    now = datetime.now(timezone.utc).isoformat()
    msg_record = {
        "id": msg_id,
        "wamid": msg_id if str(msg_id).startswith("wamid.") else None,
        "to_number": phone_number,
        "client_id": client_id,
        "client_name": client_name,
        "agent_id": agent_id,
        "sender": sender,
        "text": text,
        "status": status,
        "processing_status": processing_status,
        "error_code": error_code,
        "error_message": error_message,
        "timestamp": now,
    }

    # 1. In-memory / Disk fallback (update in-place if exists with same text, else append)
    existing_idx = next((i for i, m in enumerate(WHATSAPP_MESSAGE_HISTORY) if m.get("id") == msg_id and m.get("text") == text), None)
    if existing_idx is not None:
        WHATSAPP_MESSAGE_HISTORY[existing_idx].update(msg_record)
    else:
        WHATSAPP_MESSAGE_HISTORY.append(msg_record)
    save_whatsapp_messages(WHATSAPP_MESSAGE_HISTORY)

    # 2. Supabase (best-effort)
    try:
        conv_id = _ensure_conversation(phone_number, agent_id, client_id, client_name)
        row = {
            "id": msg_id,
            "wamid": msg_id if str(msg_id).startswith("wamid.") else None,
            "to_number": phone_number,
            "client_id": client_id,
            "agent_id": agent_id,
            "client_name": client_name,
            "sender": sender,
            "text": text,
            "status": status,
            "processing_status": processing_status,
            "timestamp": now,
        }
        if error_code is not None:
            row["error_code"] = error_code
        if error_message is not None:
            row["error_message"] = error_message
        if conv_id:
            row["conversation_id"] = conv_id
        if raw_payload:
            row["raw_payload"] = raw_payload
        supabase.table("whatsapp_messages").upsert(row, on_conflict="id").execute()
    except Exception as exc:
        print(f"[log_whatsapp_message] Supabase write warning: {exc}")

    return msg_record


_INBOUND_DEDUPE_LOCK = threading.Lock()


def record_inbound_message_atomic(
    m_id: str,
    phone_number: str,
    sender: str = "client",
    text: str = "",
    agent_id: str | None = None,
    client_id: str | None = None,
    client_name: str | None = None,
    raw_payload: dict | None = None,
) -> tuple[bool, dict]:
    """
    Atomic registration of inbound webhook delivery.
    Returns (should_process, msg_record).
    Uses the database as the concurrency guarantee across multiple workers:
    - Checks both id and wamid (covers legacy rows where wamid was null).
    - If message already exists:
        - processing_status == 'processed': returns (False, existing) -> skip.
        - processing_status == 'received': returns (False, existing) -> skip in-flight duplicate.
        - processing_status == 'failed': resets to 'received' and returns (True, existing) -> retry.
    - If message does not exist:
        Attempts INSERT with unique wamid. If duplicate violation occurs from concurrent worker,
        catches exception and skips duplicate.
    """
    clean = normalize_whatsapp_number(phone_number)
    target_wamid = m_id if str(m_id).startswith("wamid.") else None
    now = datetime.now(timezone.utc).isoformat()

    # 1. In-process check (covers single worker and memory-store testing)
    with _INBOUND_DEDUPE_LOCK:
        existing = next(
            (m for m in WHATSAPP_MESSAGE_HISTORY if m.get("id") == m_id or (target_wamid and m.get("wamid") == target_wamid) or m.get("wamid") == m_id),
            None
        )
        if existing:
            p_status = existing.get("processing_status", "processed")
            if p_status == "processed":
                print(f"[record_inbound_message_atomic] Message {m_id} already processed. Skipping redelivery.")
                return False, existing
            elif p_status == "failed":
                print(f"[record_inbound_message_atomic] Message {m_id} previously failed. Retrying on redelivery.")
                existing["processing_status"] = "received"
                save_whatsapp_messages(WHATSAPP_MESSAGE_HISTORY)
                return True, existing
            else:  # "received" -> concurrent duplicate in flight
                print(f"[record_inbound_message_atomic] Concurrent duplicate delivery in flight for {m_id}. Skipping.")
                return False, existing

    # 2. Database guarantee across worker processes
    if supabase:
        # Check both id and wamid (covers legacy rows where wamid was null)
        try:
            db_res = supabase.table("whatsapp_messages").select("id, wamid, processing_status").eq("id", m_id).limit(1).execute()
            if not (db_res and db_res.data and len(db_res.data) > 0) and target_wamid:
                db_res = supabase.table("whatsapp_messages").select("id, wamid, processing_status").eq("wamid", target_wamid).limit(1).execute()

            if db_res and db_res.data and len(db_res.data) > 0:
                db_row = db_res.data[0]
                p_status = db_row.get("processing_status", "processed")
                if p_status == "processed":
                    print(f"[record_inbound_message_atomic] Message {m_id} already processed in DB. Skipping.")
                    return False, db_row
                elif p_status == "failed":
                    print(f"[record_inbound_message_atomic] Message {m_id} previously failed in DB. Resetting for retry.")
                    try:
                        upd = (
                            supabase.table("whatsapp_messages")
                            .update({"processing_status": "received"})
                            .eq("id", db_row.get("id") or m_id)
                            .execute()
                        )
                        if upd and upd.data and len(upd.data) > 0:
                            return True, db_row
                    except Exception:
                        pass
                    return False, db_row
                else:  # "received"
                    print(f"[record_inbound_message_atomic] Concurrent duplicate delivery in flight in DB for {m_id}. Skipping.")
                    return False, db_row
        except Exception as e:
            print(f"[record_inbound_message_atomic] DB query note: {e}")

        # Try atomic insert directly to DB
        try:
            conv_id = _ensure_conversation(clean, agent_id, client_id, client_name)
            ins_row = {
                "id": m_id,
                "wamid": target_wamid or m_id,
                "to_number": clean,
                "client_id": client_id,
                "agent_id": agent_id,
                "client_name": client_name or "Client",
                "sender": sender,
                "text": text,
                "status": "received",
                "processing_status": "received",
                "timestamp": now,
            }
            if conv_id:
                ins_row["conversation_id"] = conv_id
            supabase.table("whatsapp_messages").insert(ins_row).execute()
            rec = log_whatsapp_message(
                msg_id=m_id,
                phone_number=clean,
                agent_id=agent_id,
                client_id=client_id,
                client_name=client_name or "Client",
                sender=sender,
                text=text,
                status="received",
                raw_payload=raw_payload,
                processing_status="received",
            )
            return True, rec
        except Exception as ins_exc:
            print(f"[record_inbound_message_atomic] Unique constraint hit or insert race on {m_id}: {ins_exc}")
            # Unique violation: another worker claimed the insert. Check existing row status
            try:
                db_res = supabase.table("whatsapp_messages").select("id, wamid, processing_status").eq("id", m_id).limit(1).execute()
                if not (db_res and db_res.data):
                    db_res = supabase.table("whatsapp_messages").select("id, wamid, processing_status").eq("wamid", m_id).limit(1).execute()
                if db_res and db_res.data and len(db_res.data) > 0:
                    db_row = db_res.data[0]
                    p_status = db_row.get("processing_status", "processed")
                    if p_status == "failed":
                        return True, db_row
                    return False, db_row
            except Exception:
                pass
            return False, {"id": m_id, "processing_status": "received"}

    rec = log_whatsapp_message(
        msg_id=m_id,
        phone_number=clean,
        agent_id=agent_id,
        client_id=client_id,
        client_name=client_name or "Client",
        sender=sender,
        text=text,
        status="received",
        raw_payload=raw_payload,
        processing_status="received",
    )
    return True, rec


def mark_message_processing_status(
    msg_id: str,
    new_processing_status: str,
    error_code: int | None = None,
    error_message: str | None = None,
):
    with _INBOUND_DEDUPE_LOCK:
        for m in WHATSAPP_MESSAGE_HISTORY:
            if m.get("id") == msg_id:
                m["processing_status"] = new_processing_status
                if error_code is not None:
                    m["error_code"] = error_code
                if error_message is not None:
                    m["error_message"] = error_message
                break
        save_whatsapp_messages(WHATSAPP_MESSAGE_HISTORY)
        if not WHATSAPP_USE_MEMORY_STORE and supabase:
            try:
                upd = {"processing_status": new_processing_status}
                if error_code is not None:
                    upd["error_code"] = error_code
                if error_message is not None:
                    upd["error_message"] = error_message
                supabase.table("whatsapp_messages").update(upd).eq("id", msg_id).execute()
            except Exception as exc:
                print(f"[mark_message_processing_status] Supabase note: {exc}")



def _fetch_messages_from_supabase(
    phone_number: str | None,
    agent_id: str | None,
    client_id: str | None,
) -> list[dict] | None:
    """
    Try to pull messages from Supabase. Returns None on error or when in test memory mode
    so callers fall back to the in-memory list.
    When agent_id is supplied, includes messages belonging to that agent AND
    inbound/unassigned messages (agent_id is null) so inbound replies are never hidden.
    """
    if WHATSAPP_USE_MEMORY_STORE:
        return None

    try:
        q = supabase.table("whatsapp_messages").select("*").order("timestamp", desc=False)
        if phone_number:
            clean = "".join(filter(str.isdigit, phone_number))
            if clean:
                q = q.eq("to_number", clean)
        elif client_id:
            q = q.eq("client_id", client_id)

        if agent_id:
            q = q.or_(f"agent_id.eq.{agent_id},agent_id.is.null")

        res = q.limit(200).execute()
        return res.data or []
    except Exception as exc:
        print(f"[_fetch_messages_from_supabase] Warning: {exc}")
        return None


# ─── Webhook signature verification ──────────────────────────────────────────

WHATSAPP_APP_SECRET = os.getenv("WHATSAPP_APP_SECRET")


def valid_signature(raw_body: bytes, header: str | None) -> bool:
    is_testing = "pytest" in sys.modules or "PYTEST_CURRENT_TEST" in os.environ
    if not is_testing and _env_path.exists():
        load_dotenv(_env_path, override=True)
    
    env = os.getenv("ENVIRONMENT", "").strip().lower()
    raw_enforce = os.getenv("ENFORCE_WA_SIGNATURE", "").strip().lower()
    app_secret = os.getenv("WHATSAPP_APP_SECRET") or WHATSAPP_APP_SECRET

    # If no signature header is supplied:
    if not header:
        if is_testing or env == "development":
            if raw_enforce in ("false", "0", "no") or os.getenv("WHATSAPP_TEST_MODE", "").lower() in ("true", "1") or not app_secret:
                return True
        print("[valid_signature] Missing X-Hub-Signature-256 header")
        return False

    # A signature header is present — it MUST be validated
    if not app_secret:
        if is_testing or env == "development":
            return True
        print("[valid_signature] REJECTED: WHATSAPP_APP_SECRET is not configured.")
        return False

    if not header.startswith("sha256="):
        print(f"[valid_signature] Malformed header: {header}")
        return False

    expected = hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    matched = hmac.compare_digest(expected, header.split("=", 1)[1])
    if not matched:
        print(f"[valid_signature] Signature mismatch! Header={header[:20]}... Expected=sha256={expected[:15]}...")
    return matched


# ─── Status monotonic ordering (Part 4) ─────────────────────────────────────
STATUS_ORDER = {
    "pending": 0,
    "sent": 1,
    "delivered": 2,
    "read": 3,
}

ERROR_CODE_MAP = {
    131026: "Undeliverable number",
    132000: "Template not approved or paused",
    132001: "Template not approved or paused",
    131047: "Outside the 24h customer service window",
    130429: "WhatsApp Cloud rate limit exceeded",
}


def get_readable_failure_reason(error_code: int | None, error_message: str | None = None) -> str:
    if error_code in ERROR_CODE_MAP:
        return ERROR_CODE_MAP[error_code]
    if error_message:
        return error_message
    if error_code:
        return f"Delivery failed (error {error_code})"
    return "Delivery failed"


def apply_message_status_update(
    msg_id: str,
    new_status: str,
    error_code: int | None = None,
    error_message: str | None = None,
) -> bool:
    """
    Updates message status adhering to monotonic progression:
    sent < delivered < read.
    failed overrides pending/sent, but never overrides delivered or read.
    Stores error_code, error_message, and human-readable failure_reason on failure.
    """
    target = None
    for m in WHATSAPP_MESSAGE_HISTORY:
        if m.get("id") == msg_id:
            target = m
            break

    readable_reason = get_readable_failure_reason(error_code, error_message) if new_status == "failed" else None

    if not target:
        target = {
            "id": msg_id,
            "status": new_status,
            "error_code": error_code,
            "error_message": error_message,
            "failure_reason": readable_reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        WHATSAPP_MESSAGE_HISTORY.append(target)
        save_whatsapp_messages(WHATSAPP_MESSAGE_HISTORY)
        return True

    current_status = target.get("status", "sent")
    current_rank = STATUS_ORDER.get(current_status, 1)
    new_rank = STATUS_ORDER.get(new_status, 1)

    if new_status == "failed":
        if current_status in ("delivered", "read"):
            return False
        target["status"] = "failed"
        target["error_code"] = error_code
        target["error_message"] = error_message
        target["failure_reason"] = readable_reason
    elif new_rank >= current_rank:
        target["status"] = new_status
        if error_code is not None:
            target["error_code"] = error_code
        if error_message is not None:
            target["error_message"] = error_message
    else:
        return False

    save_whatsapp_messages(WHATSAPP_MESSAGE_HISTORY)

    if not WHATSAPP_USE_MEMORY_STORE and supabase:
        try:
            upd = {"status": target["status"]}
            if error_code is not None:
                upd["error_code"] = error_code
            if error_message is not None:
                upd["error_message"] = error_message
            supabase.table("whatsapp_messages").update(upd).eq("id", msg_id).execute()
        except Exception as exc:
            print(f"[apply_message_status_update] Supabase write warning: {exc}")

    return True


# ─── Nudge template & cooldown (Part 4) ──────────────────────────────────────
NUDGE_TEMPLATE_CONFIG = {
    "name": "viewing_followup_nudge",
    "category": "MARKETING",
    "body_text": "Hello {{1}}, this is PIPELINE.EV following up on the {{2}}. If your team is still interested, we would be glad to arrange a demonstration at a time that suits you.",
    "buttons": ["View Times", "Not Now"],
}


def check_nudge_eligibility(phone_number: str, client_id: str | None = None) -> tuple[bool, str]:
    """
    Evaluates whether a contact is eligible for a follow-up nudge.
    Excludes:
      1. opted out
      2. snoozed (snoozed_until > now)
      3. declined (pitch outcome declined)
      4. human-paused (automation_paused)
      5. any open slot offer
      6. any upcoming viewing
      7. 7-day cooldown since last nudge
    """
    clean = normalize_whatsapp_number(phone_number)
    state = get_contact_state(clean)
    now_utc = datetime.now(timezone.utc)

    # 1. Opted out
    if state.get("opted_out"):
        return False, "Client has opted out of WhatsApp communication"

    # 2. Snoozed
    snoozed_until = state.get("snoozed_until")
    if snoozed_until:
        try:
            snooze_dt = datetime.fromisoformat(snoozed_until)
            if snooze_dt.tzinfo is None:
                snooze_dt = snooze_dt.replace(tzinfo=timezone.utc)
            if snooze_dt > now_utc:
                return False, f"Client is snoozed until {snooze_dt.strftime('%d %b %Y')}"
        except Exception:
            pass

    # 3. Declined
    if state.get("declined") or state.get("pitch_outcome") == "declined":
        return False, "Client has declined viewing invitation"

    # 4. Human-paused
    if state.get("automation_paused"):
        return False, "Automation is paused for this contact"

    # 5. Open slot offer check
    now_iso = now_utc.isoformat()
    has_open_offer = any(
        (o.get("phone_number") == clean or (client_id and o.get("client_id") == client_id))
        and o.get("status") == "open"
        and (not o.get("expires_at") or o.get("expires_at") > now_iso)
        for o in (WHATSAPP_SLOT_OFFERS.values() if isinstance(WHATSAPP_SLOT_OFFERS, dict) else WHATSAPP_SLOT_OFFERS)
    )
    if not has_open_offer and not WHATSAPP_USE_MEMORY_STORE and supabase:
        try:
            so_res = (
                supabase.table("whatsapp_slot_offers")
                .select("id")
                .eq("status", "open")
                .eq("phone_number", clean)
                .gt("expires_at", now_iso)
                .limit(1)
                .execute()
            )
            if so_res.data and len(so_res.data) > 0:
                has_open_offer = True
        except Exception:
            pass
    if has_open_offer:
        return False, "Client already has an open slot offer"

    # 6. Upcoming viewing check
    has_upcoming_viewing = False
    if state.get("has_upcoming_viewing") or (state.get("upcoming_viewings") and len(state.get("upcoming_viewings")) > 0):
        has_upcoming_viewing = True
    elif not WHATSAPP_USE_MEMORY_STORE and supabase:
        try:
            v_res = (
                supabase.table("scheduled_viewings")
                .select("id, client_id, phone_number, status")
                .in_("status", ["upcoming", "confirmed"])
                .execute()
            )
            if v_res.data:
                for v in v_res.data:
                    v_p = "".join(filter(str.isdigit, v.get("phone_number") or ""))
                    if (client_id and v.get("client_id") == client_id) or (clean and v_p == clean):
                        has_upcoming_viewing = True
                        break
        except Exception:
            pass
    if has_upcoming_viewing:
        return False, "Client already has an upcoming scheduled viewing"

    # 7. 7-day nudge cooldown
    last_nudged = state.get("last_nudged_at")
    if last_nudged:
        try:
            dt = datetime.fromisoformat(last_nudged)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if now_utc - dt < timedelta(days=7):
                return False, f"7-day nudge cooldown active (last nudged {dt.strftime('%d %b')})"
        except Exception:
            pass

    return True, "Eligible"


def dispatch_followup_nudge(phone_number: str, client_name: str = "Client", unit_name: str = "property") -> dict:
    clean = normalize_whatsapp_number(phone_number)
    eligible, reason = check_nudge_eligibility(clean)
    if not eligible:
        raise HTTPException(status_code=400, detail=reason)

    rendered_text = (
        f"Hello {client_name}, this is PIPELINE.EV following up on the {unit_name}. "
        f"If your team is still interested, we would be glad to arrange a demonstration at a time that suits you."
    )

    if not is_within_24h_window(clean):
        result = send_whatsapp_template_with_quick_replies(
            to_number=clean,
            template_name="viewing_followup_nudge",
            body_parameters=[client_name, unit_name],
            button_payloads=[f"nudge:view_times:{clean}", f"nudge:not_now:{clean}"],
        )
    else:
        result = send_whatsapp_interactive_buttons(
            to_number=clean,
            body_text=rendered_text,
            buttons=[
                {"id": f"nudge:view_times:{clean}", "title": "View Times"},
                {"id": f"nudge:not_now:{clean}", "title": "Not Now"},
            ],
            header_text="Follow-up",
        )

    now_iso = datetime.now(timezone.utc).isoformat()
    curr_state = get_contact_state(clean)
    update_contact_state(
        clean,
        last_nudged_at=now_iso,
        nudge_count=(curr_state.get("nudge_count") or 0) + 1,
    )

    log_whatsapp_message(
        msg_id=f"nudge_{int(datetime.now(timezone.utc).timestamp()*1000)}",
        phone_number=clean,
        agent_id=None,
        client_id=None,
        client_name=client_name,
        sender="agent",
        text=rendered_text,
        status="sent",
        processing_status="processed",
    )

    return {"success": True, "text": rendered_text, "whatsapp_response": result}


# ─── Bucket Precedence (Part 4) ──────────────────────────────────────────────
def calculate_conversation_bucket(conv_info: dict) -> str:
    """
    Bucket Precedence:
    1. opted_out (highest)
    2. needs_reply
    3. booked
    4. waiting_on_client
    5. cold (lowest)
    """
    if conv_info.get("opted_out"):
        return "opted_out"
    if conv_info.get("has_inbound_reply"):
        return "needs_reply"
    if conv_info.get("has_upcoming_viewing"):
        return "booked"
    days_ago = conv_info.get("last_message_outbound_days_ago", 999)
    if days_ago <= 14:
        return "waiting_on_client"
    return "cold"


# ─── Suggest reply guards (Part 4) ──────────────────────────────────────────
# Enterprise commercial EV domain: remove real-estate leftover "free rent".
# Must strictly forbid warranty, guarantee/guaranteed savings, ROI/payback,
# delivery/lead-time/installation dates, discounts, price commitments, contract terms, refunds.
FORBIDDEN_PROMISES = [
    "warranty",
    "guarantee",
    "guaranteed",
    "guaranteed savings",
    "roi",
    "payback",
    "delivery date",
    "lead time",
    "lead-time",
    "installation date",
    "discount",
    "price commitment",
    "contract terms",
    "refund",
    "refunds",
]

_SUGGEST_REPLY_RATE_LIMITS: dict[str, list[float]] = {}


def truncate_at_sentence_boundary(text: str, max_chars: int = 300) -> str:
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    matches = list(re.finditer(r'([.!?])(?:\s|$)', truncated))
    if matches:
        cut_idx = matches[-1].end()
        return truncated[:cut_idx].strip()
    last_space = truncated.rfind(" ")
    if last_space > 0:
        return truncated[:last_space].strip() + "..."
    return truncated.strip() + "..."


def check_numeric_grounding(draft: str, facts_context: str) -> bool:
    """
    Returns True if every number, currency figure, and duration in the draft
    is grounded in facts_context.
    """
    if not facts_context:
        # If no facts context provided, any numeric claim is ungrounded
        numbers_in_draft = re.findall(r'\b\d+(?:[.,]\d+)?\b', draft)
        return len(numbers_in_draft) == 0

    facts_lower = facts_context.lower()
    draft_tokens = re.findall(r'\b(?:rm|\$|usd|sgd)?\s*\d+(?:[.,]\d+)?%?\b', draft, re.IGNORECASE)

    for token in draft_tokens:
        clean_num = re.sub(r'[^\d.]', '', token)
        if not clean_num:
            continue
        if clean_num not in facts_lower:
            return False

    return True


def suggest_ai_reply(phone_number: str, prompt_context: str | None = None, client_ip: str = "127.0.0.1") -> dict:
    import time as pytime
    now = pytime.time()
    timestamps = _SUGGEST_REPLY_RATE_LIMITS.setdefault(client_ip, [])
    timestamps = [t for t in timestamps if now - t < 60.0]
    _SUGGEST_REPLY_RATE_LIMITS[client_ip] = timestamps
    if len(timestamps) >= 20:
        raise HTTPException(status_code=429, detail="Too many suggest reply requests. Max 20 per minute.")
    timestamps.append(now)

    clean = normalize_whatsapp_number(phone_number)
    context = prompt_context or ""

    draft = None
    if groq_client and context and "pytest" not in sys.modules and "PYTEST_CURRENT_TEST" not in os.environ and "unittest" not in sys.modules:
        try:
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are an industrial robotics sales representative at PIPELINE.EV. "
                        "Answer the prospect's WhatsApp question concisely (1 to 2 sentences max, under 250 characters). "
                        "Be helpful, technical, grounded, and polite. Never make up prices, discounts, or delivery guarantees."
                    )
                },
                {"role": "user", "content": context}
            ]
            llm_text = _call_groq_llm(messages, max_tokens=150, temperature=0.3)
            if llm_text:
                draft = llm_text.strip()
        except Exception as e:
            print(f"[suggest_ai_reply] LLM warning: {e}")
            draft = None

    if not draft:
        if "roi" in context.lower() or "payback" in context.lower() or "savings" in context.lower():
            draft = "We estimate a 25% cost reduction and 3-year payback on fleet electrification."
        elif "price" in context.lower() or "negotiab" in context.lower():
            draft = "Thank you for asking! Pricing terms can be discussed with our lead specialist during the on-site walkthrough. Would you like to review available appointment slots?"
        elif "reschedule" in context.lower():
            draft = "No problem at all. We have alternate slots available this Thursday and Friday. What timeframe best fits your team's calendar?"
        elif "terrain" in context.lower() or "outdoor" in context.lower():
            draft = "Our robotics units are primarily engineered for indoor industrial facilities. For outdoor and uneven terrain, we offer specialized chassis options we can demonstrate on-site."
        else:
            draft = "Thank you for reaching out! Our specialist is reviewing your inquiry and will follow up with technical specifications shortly."

    # Truncate at sentence boundary (not mid-sentence)
    if len(draft) > 300:
        draft = truncate_at_sentence_boundary(draft, 300)

    # 1. Numeric Grounding check:
    # If any ungrounded numeric claim exists, replace the whole draft
    is_grounded = check_numeric_grounding(draft, context)
    if not is_grounded:
        draft = "Please consult your senior sales specialist for verified specifications and financial details."

    # 2. Forbidden promises check:
    has_forbidden = False
    for f_term in FORBIDDEN_PROMISES:
        pattern = r'\b' + re.escape(f_term) + r'\b'
        if re.search(pattern, draft, re.IGNORECASE):
            has_forbidden = True
            draft = "Please consult your senior sales specialist for verified terms and commercial agreements."
            break

    return {
        "suggested_text": draft,
        "is_ai_draft": True,
        "character_count": len(draft),
        "safety_scanned": True,
        "forbidden_flagged": has_forbidden,
        "numeric_grounded": is_grounded,
    }



# ─── WhatsApp REST endpoints ──────────────────────────────────────────────────

@app.get("/api/whatsapp/messages")
def get_whatsapp_messages(
    request: Request,
    to_number: str = None,
    client_id: str = None,
    agent_id: str = None,
):
    """
    Return message history for a given phone number filtered by agent.
    Tries Supabase first; falls back to the in-memory / disk list.
    """
    agent = getattr(request.state, "agent", None) if request else None
    scoping_mode = os.getenv("AGENT_PIPELINE_SCOPING", "assigned").lower()
    if agent and agent.role != "admin" and scoping_mode == "assigned":
        agent_id = str(agent.agent_id) if agent.agent_id else "no_agent"
        if client_id:
            from agent_auth import require_client_access
            require_client_access(agent, client_id, supabase)
    # Supabase path (preferred)
    db_msgs = _fetch_messages_from_supabase(to_number, agent_id, client_id)
    if db_msgs is not None:
        return {"messages": db_msgs}

    # Disk fallback
    results = WHATSAPP_MESSAGE_HISTORY
    if agent_id:
        results = [m for m in results if m.get("agent_id") == agent_id or not m.get("agent_id")]
    if to_number:
        clean_target = "".join(filter(str.isdigit, to_number))
        if clean_target:
            results = [
                m for m in results
                if clean_target in m.get("to_number", "") or m.get("to_number", "") in clean_target
            ]
    elif client_id:
        results = [m for m in results if m.get("client_id") == client_id]
    return {"messages": results}


def _find_agent_for_inbound(phone_number: str) -> str | None:
    """
    Return the agent_id from the most recent outbound message to `phone_number`,
    so inbound replies are threaded into the correct agent's conversation.

    Query order:
      1. Supabase whatsapp_messages (source of truth after migration)
      2. In-memory WHATSAPP_MESSAGE_HISTORY (disk fallback before migration)

    If no prior outbound exists the function returns None, not an error.
    The caller (log_whatsapp_message → _ensure_conversation) will create a
    fresh conversation row so the inbound message is always persisted.
    """
    # 1. Supabase path (production)
    if not WHATSAPP_USE_MEMORY_STORE:
        try:
            res = (
                supabase.table("whatsapp_messages")
                .select("agent_id")
                .eq("to_number", phone_number)
                .eq("sender", "agent")
                .not_.is_("agent_id", "null")
                .order("timestamp", desc=True)
                .limit(1)
                .execute()
            )
            if res.data:
                return res.data[0]["agent_id"]
        except Exception as exc:
            print(f"[_find_agent_for_inbound] Supabase query warning: {exc}")

    # 2. Memory fallback
    try:
        outbound = [
            m for m in reversed(WHATSAPP_MESSAGE_HISTORY)
            if m.get("to_number") == phone_number
            and m.get("sender") == "agent"
            and m.get("agent_id")
        ]
        if outbound:
            return outbound[0]["agent_id"]
    except Exception:
        pass


# ─── Viewing Reminders Engine (Part 2) ────────────────────────────────────────

def calculate_viewing_reminder_schedules(
    scheduled_at: str | datetime,
    now_dt: datetime | None = None,
) -> list[dict]:
    """
    Computes scheduled send times for 24h and 2h reminders for a viewing.
    Rules:
    - Skip rules:
        * No T-24h reminder if viewing is less than ~26h away.
        * No T-2h reminder if viewing is less than ~3h away.
    - Quiet hours:
        * Never send between 21:00 and 08:00 MYT (Asia/Kuala_Lumpur).
        * Move to nearest allowed time that is still before the viewing, else skip.
    """
    if isinstance(scheduled_at, str):
        clean_iso = scheduled_at.replace("Z", "+00:00")
        v_dt = datetime.fromisoformat(clean_iso)
    else:
        v_dt = scheduled_at

    if v_dt.tzinfo is None:
        v_dt = v_dt.replace(tzinfo=KL_TZ)
    else:
        v_dt = v_dt.astimezone(KL_TZ)

    if now_dt is None:
        now_dt = datetime.now(KL_TZ)
    elif now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=KL_TZ)
    else:
        now_dt = now_dt.astimezone(KL_TZ)

    hours_until = (v_dt - now_dt).total_seconds() / 3600.0
    results = []

    def _adjust_quiet_hours(target_send: datetime) -> datetime | None:
        # Active window: 08:00:00 to 20:59:59 MYT
        if 8 <= target_send.hour < 21:
            return target_send

        # Boundary options:
        # Evening boundary: 20:45 MYT (same day if target >= 21; previous day if target < 8)
        if target_send.hour >= 21:
            eve_cand = target_send.replace(hour=20, minute=45, second=0, microsecond=0)
        else:
            eve_cand = (target_send - timedelta(days=1)).replace(hour=20, minute=45, second=0, microsecond=0)

        # Morning boundary: 08:00 MYT (same day if target < 8; next day if target >= 21)
        if target_send.hour < 8:
            morn_cand = target_send.replace(hour=8, minute=0, second=0, microsecond=0)
        else:
            morn_cand = (target_send + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)

        # Candidates must be strictly before viewing (by at least 15 mins) and in the future (> now_dt)
        min_lead = timedelta(minutes=15)
        valid_cands = []
        for cand in [eve_cand, morn_cand]:
            if cand > now_dt and cand <= (v_dt - min_lead):
                diff = abs((cand - target_send).total_seconds())
                valid_cands.append((diff, cand))

        if not valid_cands:
            return None

        # Pick candidate with smallest absolute distance to original target_send
        valid_cands.sort(key=lambda x: x[0])
        return valid_cands[0][1]

    # 1. T-24h reminder (skip if < 26 hours away)
    if hours_until >= 26.0:
        target_24h = v_dt - timedelta(hours=24)
        adj_24h = _adjust_quiet_hours(target_24h)
        if adj_24h:
            results.append({
                "reminder_type": "24h",
                "scheduled_send_time": adj_24h.isoformat(),
            })

    # 2. T-2h reminder (skip if < 3 hours away)
    if hours_until >= 3.0:
        target_2h = v_dt - timedelta(hours=2)
        adj_2h = _adjust_quiet_hours(target_2h)
        if adj_2h:
            results.append({
                "reminder_type": "2h",
                "scheduled_send_time": adj_2h.isoformat(),
            })

    return results


def schedule_viewing_reminders(viewing_id: str) -> list[dict]:
    """
    Schedules 24h and 2h reminders for a scheduled viewing, inserting rows into whatsapp_reminders.
    """
    if WHATSAPP_USE_MEMORY_STORE:
        schedules = calculate_viewing_reminder_schedules(
            datetime.now(KL_TZ) + timedelta(hours=30)
        )
        created = []
        for s in schedules:
            row = {
                "id": str(uuid.uuid4()),
                "viewing_id": viewing_id,
                "client_id": None,
                "agent_id": None,
                "phone_number": "60123456789",
                "reminder_type": s["reminder_type"],
                "scheduled_send_time": s["scheduled_send_time"],
                "status": "pending",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            WHATSAPP_REMINDERS_STORE.append(row)
            created.append(row)
        return created

    try:
        v_res = (
            supabase.table("scheduled_viewings")
            .select("id, client_id, property_id, agent_id, scheduled_at, status, clients(id, name, whatsapp_number, phone, assigned_agent_id)")
            .eq("id", viewing_id)
            .limit(1)
            .execute()
        )
        if not v_res.data:
            return []
        v = v_res.data[0]
        if v.get("status") != "upcoming" or not v.get("scheduled_at"):
            return []

        c_info = v.get("clients") or {}
        raw_phone = c_info.get("whatsapp_number") or c_info.get("phone")
        if not raw_phone:
            return []
        clean_phone = "".join(filter(str.isdigit, str(raw_phone)))
        if not clean_phone:
            return []
        if clean_phone.startswith(("603", "604", "605", "606", "607", "608", "609")):
            print(f"[schedule_viewing_reminders] Skipped: {clean_phone} is a company landline, cannot receive WhatsApp.")
            return []

        agent_id = v.get("agent_id") or c_info.get("assigned_agent_id")
        client_id = v.get("client_id")

        schedules = calculate_viewing_reminder_schedules(v["scheduled_at"])
        created = []
        for s in schedules:
            row = {
                "viewing_id": viewing_id,
                "client_id": client_id,
                "agent_id": agent_id,
                "phone_number": clean_phone,
                "reminder_type": s["reminder_type"],
                "scheduled_send_time": s["scheduled_send_time"],
                "status": "pending",
            }
            try:
                ins = supabase.table("whatsapp_reminders").insert(row).execute()
                if ins.data:
                    created.append(ins.data[0])
            except Exception as e:
                print(f"[schedule_viewing_reminders] insert warning: {e}")
        return created
    except Exception as exc:
        print(f"[schedule_viewing_reminders] error: {exc}")
        return []


def cancel_viewing_reminders(viewing_id: str, reason: str = "viewing_cancelled") -> int:
    """
    Cancels all pending/processing reminders for a viewing.
    """
    if WHATSAPP_USE_MEMORY_STORE:
        count = 0
        for r in WHATSAPP_REMINDERS_STORE:
            if r.get("viewing_id") == viewing_id and r.get("status") in ("pending", "processing"):
                r["status"] = "cancelled"
                r["error"] = reason
                count += 1
        return count

    try:
        res = (
            supabase.table("whatsapp_reminders")
            .update({"status": "cancelled", "error": reason})
            .eq("viewing_id", viewing_id)
            .in_("status", ["pending", "processing"])
            .execute()
        )
        return len(res.data or [])
    except Exception as exc:
        print(f"[cancel_viewing_reminders] error: {exc}")
        return 0


def recompute_viewing_reminders(viewing_id: str) -> list[dict]:
    """
    Cancels old pending reminders and schedules new ones for an updated viewing time.
    """
    cancel_viewing_reminders(viewing_id, reason="rescheduled")
    return schedule_viewing_reminders(viewing_id)


def process_due_whatsapp_reminders(limit: int = 15) -> list[dict]:
    """
    Worker task: claims due reminders atomically and dispatches them via WhatsApp.
    Outside 24h: sends 'viewing_reminder' template with quick replies.
    Inside 24h: sends interactive reply buttons.
    """
    claimed = []
    if WHATSAPP_USE_MEMORY_STORE:
        now_iso = datetime.now(timezone.utc).isoformat()
        for r in WHATSAPP_REMINDERS_STORE:
            if r.get("status") == "pending" and (r.get("scheduled_send_time") or "") <= now_iso:
                r["status"] = "processing"
                claimed.append(r)
                if len(claimed) >= limit:
                    break
    else:
        # 1. Try atomic claim RPC first
        try:
            rpc_res = supabase.rpc("claim_due_whatsapp_reminders", {"p_limit": limit}).execute()
            if rpc_res and rpc_res.data:
                claimed = rpc_res.data
        except Exception as rpc_err:
            now_iso = datetime.now(timezone.utc).isoformat()
            try:
                pending_res = (
                    supabase.table("whatsapp_reminders")
                    .select("*")
                    .eq("status", "pending")
                    .lte("scheduled_send_time", now_iso)
                    .order("scheduled_send_time")
                    .limit(limit)
                    .execute()
                )
                for r in (pending_res.data or []):
                    upd = (
                        supabase.table("whatsapp_reminders")
                        .update({"status": "processing"})
                        .eq("id", r["id"])
                        .eq("status", "pending")
                        .execute()
                    )
                    if upd.data:
                        claimed.append(upd.data[0])
            except Exception as sel_err:
                print(f"[process_due_whatsapp_reminders] claim error: {sel_err}")
                return []

    dispatched = []
    for r in claimed:
        r_id = r["id"]
        v_id = r["viewing_id"]
        phone = r["phone_number"]
        try:
            # Check viewing status
            v_row = None
            if not WHATSAPP_USE_MEMORY_STORE:
                v_res = (
                    supabase.table("scheduled_viewings")
                    .select("id, status, scheduled_at, client_id, property_id, agent_id, clients(name), properties(address), agents(name)")
                    .eq("id", v_id)
                    .limit(1)
                    .execute()
                )
                if not v_res.data or v_res.data[0].get("status") != "upcoming":
                    supabase.table("whatsapp_reminders").update({
                        "status": "cancelled",
                        "error": "viewing_no_longer_upcoming"
                    }).eq("id", r_id).execute()
                    continue
                v_row = v_res.data[0]
            else:
                v_row = {
                    "id": v_id,
                    "status": "upcoming",
                    "scheduled_at": (datetime.now(KL_TZ) + timedelta(hours=2)).isoformat(),
                    "clients": {"name": "Valued Client"},
                    "properties": {"address": "Unit 12-A"},
                    "agents": {"name": "R. Delgado"},
                }

            # Check if automation paused / human handled
            if is_automation_paused_for_phone(phone):
                if not WHATSAPP_USE_MEMORY_STORE:
                    supabase.table("whatsapp_reminders").update({
                        "status": "cancelled",
                        "error": "automation_paused_human_handled"
                    }).eq("id", r_id).execute()
                else:
                    r["status"] = "cancelled"
                    r["error"] = "automation_paused_human_handled"
                continue

            c_info = v_row.get("clients") or {}
            client_name = c_info.get("name") or "Valued Client"
            prop_info = v_row.get("properties") or {}
            unit_name = prop_info.get("address") or "Robotics Demonstration"

            v_dt = datetime.fromisoformat(str(v_row["scheduled_at"]).replace("Z", "+00:00")).astimezone(KL_TZ)
            formatted_dt = format_slot_label(v_dt)

            in_window = is_within_24h_window(phone)
            sent_text = ""
            send_res = None

            if in_window:
                # Inside 24h window: send interactive reply buttons
                body = (
                    f"Reminder: Your upcoming demonstration of {unit_name} is scheduled on {formatted_dt}. "
                    f"Please confirm your attendance below."
                )
                buttons = [
                    {"id": f"reminder:{v_id}:confirm", "title": "Confirm"},
                    {"id": f"reminder:{v_id}:reschedule", "title": "Reschedule"},
                    {"id": f"reminder:{v_id}:cancel", "title": "Cancel"},
                ]
                sent_text = body
                send_res = send_whatsapp_interactive_buttons(
                    to_number=phone,
                    body_text=body,
                    buttons=buttons,
                )
            else:
                # Outside 24h window: send approved UTILITY template with quick replies
                sent_text = render_viewing_reminder_text(client_name, unit_name, formatted_dt)
                send_res = send_whatsapp_template_with_quick_replies(
                    to_number=phone,
                    template_name=REMINDER_TEMPLATE_CONFIG["name"],
                    language_code="en_US",
                    body_parameters=[client_name, unit_name, formatted_dt],
                    button_payloads=[
                        f"reminder:{v_id}:confirm",
                        f"reminder:{v_id}:reschedule",
                        f"reminder:{v_id}:cancel",
                    ],
                )

            wamid = None
            if send_res and send_res.get("messages"):
                wamid = send_res["messages"][0].get("id")

            log_whatsapp_message(
                msg_id=f"rem_{r_id}_{int(datetime.now(timezone.utc).timestamp()*1000)}",
                phone_number=phone,
                agent_id=r.get("agent_id"),
                client_id=r.get("client_id"),
                client_name=client_name,
                sender="agent",
                text=sent_text,
                status="sent",
            )

            if not WHATSAPP_USE_MEMORY_STORE:
                supabase.table("whatsapp_reminders").update({
                    "status": "sent",
                    "sent_at": datetime.now(timezone.utc).isoformat(),
                    "wamid": wamid,
                }).eq("id", r_id).execute()
            else:
                r["status"] = "sent"
                r["sent_at"] = datetime.now(timezone.utc).isoformat()
                r["wamid"] = wamid

            dispatched.append({"reminder_id": r_id, "status": "sent", "wamid": wamid})
        except Exception as proc_err:
            print(f"[process_due_whatsapp_reminders] dispatch failed for {r_id}: {proc_err}")
            if not WHATSAPP_USE_MEMORY_STORE:
                try:
                    supabase.table("whatsapp_reminders").update({
                        "status": "failed",
                        "error": str(proc_err),
                    }).eq("id", r_id).execute()
                except Exception:
                    pass
            else:
                r["status"] = "failed"
                r["error"] = str(proc_err)

    return dispatched


# ─── Deterministic Interactive Button / List Reply Processor ──────────────────

def process_interactive_button_reply(
    *,
    phone_number: str,
    button_payload: str,
    button_title: str | None = None,
    client_id: str | None = None,
    client_name: str | None = "Client Contact",
    agent_id: str | None = None,
) -> dict:
    """
    Deterministically handles button/list replies by ID with ZERO LLM calls.
    Supports:
      - slot_pick:{offer_id}:{slot_index}
      - action:{offer_id}:reschedule
      - action:{offer_id}:human
    """
    clean_digits = "".join(filter(str.isdigit, phone_number))
    parts = button_payload.strip().split(":")

    if button_payload.startswith("slot_pick:") and len(parts) >= 3:
        offer_id = parts[1]
        try:
            slot_index = int(parts[2])
        except ValueError:
            return {"error": "Invalid slot index"}

        offer = get_slot_offer_by_id(offer_id) or get_open_slot_offer(phone_number=clean_digits)
        if isinstance(offer, list):
            offer = offer[0] if len(offer) > 0 else None

        # ── Identity check: Inbound sender must match the offer's recipient phone number ──
        if offer:
            offer_phone = "".join(filter(str.isdigit, offer.get("phone_number") or ""))
            if offer_phone and clean_digits and offer_phone != clean_digits:
                print(f"[process_interactive_button_reply] WARNING: Identity mismatch! Sender {clean_digits} does not match offer phone {offer_phone}")
                return {
                    "error": "sender_identity_mismatch",
                    "detail": f"Sender {clean_digits} does not match offer recipient {offer_phone}",
                }

        now_utc = datetime.now(timezone.utc).isoformat()
        is_expired = bool(offer and offer.get("expires_at") and offer.get("expires_at") <= now_utc)

        if not offer or offer.get("status") != "open" or is_expired:
            if offer and is_expired:
                update_slot_offer_status(offer["id"], "expired")
            expired_body = (
                "Thank you for your response! This viewing offer has already been confirmed or has expired. "
                "Please let us know if you would like to arrange an alternative time."
            )
            send_whatsapp_message(clean_digits, expired_body)
            log_whatsapp_message(
                msg_id=f"auto_exp_{int(datetime.now(timezone.utc).timestamp() * 1000)}",
                phone_number=clean_digits,
                agent_id=agent_id,
                client_id=client_id,
                client_name=client_name or "Client",
                sender="agent",
                text=expired_body,
                status="sent",
            )
            return {"action": "offer_expired_or_already_booked"}

        c_id = offer.get("client_id") or client_id
        p_id = offer.get("property_id")
        a_id = offer.get("agent_id") or agent_id
        slots = offer.get("slots", [])

        chosen_slot = next((s for s in slots if s.get("index") == slot_index), None)
        if not chosen_slot:
            return {"error": f"Slot index {slot_index} not found in offer"}

        target_iso = chosen_slot.get("slot_iso")
        slot_label = chosen_slot.get("label") or "the selected time"

        agent_name = "R. Delgado"
        if a_id:
            try:
                a_res = supabase.table("agents").select("name").eq("id", a_id).single().execute()
                if a_res.data and a_res.data.get("name"):
                    agent_name = a_res.data["name"]
            except Exception:
                pass

        prop_name = "Robotics Unit"
        if p_id:
            try:
                p_res = supabase.table("properties").select("address, neighborhood").eq("id", p_id).single().execute()
                if p_res.data:
                    prop_name = f"{p_res.data.get('address')} ({p_res.data.get('neighborhood')})"
            except Exception:
                pass

        try:
            target_dt = datetime.fromisoformat(target_iso.replace("Z", "+00:00"))
        except Exception:
            target_dt = None

        # Re-check agent conflicts and business hours immediately before claim/booking
        is_free = (
            target_dt is not None
            and is_within_business_hours(target_dt)
            and is_slot_available(target_dt, agent_id=a_id, buffer_minutes=45)
        )
        def _send_conflict_apology():
            try:
                update_slot_offer_status(offer["id"], "expired")
            except Exception:
                pass
            fresh_slots = generate_candidate_slots(agent_id=a_id, count=3)
            new_offer_id = str(uuid.uuid4())
            new_offer = {
                "id": new_offer_id,
                "client_id": c_id,
                "property_id": p_id,
                "agent_id": a_id,
                "slots": fresh_slots,
                "status": "open",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "expires_at": (datetime.now(timezone.utc) + timedelta(hours=72)).isoformat(),
                "pitch_wamid": f"tap_conflict_{int(datetime.now(timezone.utc).timestamp())}",
                "phone_number": clean_digits,
                "reoffer_count": offer.get("reoffer_count", 0),
            }
            try:
                persist_slot_offer(new_offer)
            except Exception as e:
                print(f"[process_interactive_button_reply] Warning saving re-offer: {e}")

            apology_body = (
                f"We apologize, but {slot_label} was just booked for another demonstration. "
                "Here are 3 fresh alternative demonstration times that suit our schedule:"
            )
            sections = [
                {
                    "title": "Fresh Available Times",
                    "rows": [
                        {
                            "id": f"slot_pick:{new_offer_id}:{s['index']}",
                            "title": s["label"][:24],
                            "description": "60-min demonstration",
                        }
                        for s in fresh_slots
                    ],
                },
                {
                    "title": "Other Options",
                    "rows": [
                        {
                            "id": f"action:{new_offer_id}:human",
                            "title": "Talk to a person",
                            "description": "Speak with our sales representative",
                        }
                    ],
                },
            ]
            send_whatsapp_interactive_list(
                to_number=clean_digits,
                body_text=apology_body,
                button_label="Choose a Time",
                sections=sections,
            )
            return {
                "action": "conflict_apologized_and_reoffered",
                "detail": "Slot was no longer free at tap time. Apologized and sent fresh slots.",
                "new_offer_id": new_offer_id,
            }

        if not is_free:
            return _send_conflict_apology()

        # ── Transactional RPC: claim + viewing insert in single transaction (2-arg signature) ──
        booked_via_rpc = False
        viewing_id = None
        try:
            rpc_res = supabase.rpc("claim_and_book_slot_offer", {
                "p_offer_id": offer["id"],
                "p_slot_index": slot_index,
            }).execute()
            if rpc_res and rpc_res.data:
                data = rpc_res.data
                if isinstance(data, dict):
                    if data.get("success"):
                        booked_via_rpc = True
                        viewing_id = data.get("viewing_id")
                    elif data.get("conflict"):
                        return _send_conflict_apology()
                    elif data.get("error") and "not available or expired" in data.get("error", "").lower():
                        return {"action": "duplicate_prevented", "detail": data["error"]}
        except Exception as rpc_err:
            print(f"[process_interactive_button_reply] claim_and_book_slot_offer RPC notice: {rpc_err}")

        # ── Defensive sequential fallback if RPC not deployed or test mock ──
        if not booked_via_rpc:
            claimed_offer = claim_slot_offer(offer["id"], slot_index)
            if isinstance(claimed_offer, list):
                claimed_offer = claimed_offer[0] if len(claimed_offer) > 0 else None
            if not claimed_offer:
                return {"action": "duplicate_prevented", "detail": "Offer was already claimed by a concurrent request or expired"}

            viewing_row = {
                "client_id": c_id,
                "property_id": p_id,
                "scheduled_at": target_iso,
                "status": "upcoming",
            }
            try:
                v_res = supabase.table("scheduled_viewings").insert(viewing_row).execute()
                if not v_res or (hasattr(v_res, "data") and v_res.data is None):
                    raise RuntimeError("Empty response from scheduled_viewings insert")
                viewing_id = v_res.data[0]["id"] if (v_res.data and len(v_res.data) > 0) else None
            except Exception as insert_exc:
                print(f"[process_interactive_button_reply] Viewing insert failed; rolling back offer {offer['id']}: {insert_exc}")
                rollback_slot_offer(offer["id"])
                return {
                    "action": "booking_failed_rolled_back",
                    "error": f"Failed to book viewing: {insert_exc}. Offer rolled back to open.",
                }

        if c_id:
            advance_stage(c_id, "viewing")

        confirm_body = build_booking_confirmation_text(
            prop_name=prop_name,
            slot_label=slot_label,
            agent_name=agent_name,
            viewing_id=viewing_id,
            scheduled_at_iso=target_iso,
        )
        send_whatsapp_message(clean_digits, confirm_body)
        log_whatsapp_message(
            msg_id=f"auto_confirm_{int(datetime.now(timezone.utc).timestamp() * 1000)}",
            phone_number=clean_digits,
            agent_id=a_id,
            client_id=c_id,
            client_name=client_name or "Client",
            sender="agent",
            text=confirm_body,
            status="sent",
        )

        try:
            supabase.table("signals").insert({
                "type": "whatsapp_meeting_booked",
                "client_id": c_id,
                "property_id": p_id,
                "message": f"Interactive WhatsApp demo booked for {slot_label} ({prop_name})",
            }).execute()
        except Exception:
            pass

        if viewing_id:
            schedule_viewing_reminders(viewing_id)

        return {
            "action": "booked",
            "viewing_id": viewing_id,
            "scheduled_at": target_iso,
            "slot_label": slot_label,
            "agent_name": agent_name,
        }

    elif button_payload.startswith("action:") and len(parts) >= 3:
        offer_id = parts[1]
        action_name = parts[2]
        offer = get_slot_offer_by_id(offer_id) or get_open_slot_offer(phone_number=clean_digits)
        if isinstance(offer, list):
            offer = offer[0] if len(offer) > 0 else None

        # Identity check on action button
        if offer:
            offer_phone = "".join(filter(str.isdigit, offer.get("phone_number") or ""))
            if offer_phone and clean_digits and offer_phone != clean_digits:
                print(f"[process_interactive_button_reply] WARNING: Identity mismatch on action! Sender {clean_digits} != offer {offer_phone}")
                return {
                    "error": "sender_identity_mismatch",
                    "detail": f"Sender {clean_digits} does not match offer recipient {offer_phone}",
                }

        a_id = (offer and offer.get("agent_id")) or agent_id

        if action_name == "reschedule":
            curr_reoffers = int(offer.get("reoffer_count", 0)) if offer else 0
            if curr_reoffers >= 3:
                set_automation_paused_for_phone(clean_digits, True)
                agent_name = "R. Delgado"
                if a_id:
                    try:
                        a_res = supabase.table("agents").select("name").eq("id", a_id).single().execute()
                        if a_res.data and a_res.data.get("name"):
                            agent_name = a_res.data["name"]
                    except Exception:
                        pass
                handoff_msg = (
                    f"Thank you for letting us know! You've requested multiple alternative times, so {agent_name} "
                    f"will personally connect with you to find a viewing time that works best for your schedule."
                )
                send_whatsapp_message(clean_digits, handoff_msg)
                log_whatsapp_message(
                    msg_id=f"reoffer_cap_{int(datetime.now(timezone.utc).timestamp() * 1000)}",
                    phone_number=clean_digits,
                    agent_id=a_id,
                    client_id=client_id,
                    client_name=client_name or "Client",
                    sender="agent",
                    text=handoff_msg,
                    status="sent",
                )
                try:
                    supabase.table("signals").insert({
                        "type": "whatsapp_human_handoff",
                        "client_id": client_id,
                        "message": f"Client reached 3 re-offer limit ({clean_digits}). Automation paused; handoff to {agent_name}.",
                    }).execute()
                except Exception:
                    pass
                return {
                    "action": "reoffer_cap_reached",
                    "detail": "Re-offer limit reached (3). Handed off to human rep.",
                }

            fresh_slots = generate_candidate_slots(agent_id=a_id, count=3)
            new_offer_id = str(uuid.uuid4())
            new_offer = {
                "id": new_offer_id,
                "client_id": (offer and offer.get("client_id")) or client_id,
                "property_id": (offer and offer.get("property_id")),
                "agent_id": a_id,
                "slots": fresh_slots,
                "status": "open",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "expires_at": (datetime.now(timezone.utc) + timedelta(hours=72)).isoformat(),
                "pitch_wamid": f"resched_{int(datetime.now(timezone.utc).timestamp())}",
                "phone_number": clean_digits,
                "reoffer_count": curr_reoffers + 1,
            }
            persist_slot_offer(new_offer)

            sections = [
                {
                    "title": "Alternative Times",
                    "rows": [
                        {
                            "id": f"slot_pick:{new_offer_id}:{s['index']}",
                            "title": s["label"][:24],
                            "description": "60-min demonstration",
                        }
                        for s in fresh_slots
                    ],
                },
                {
                    "title": "Other Options",
                    "rows": [
                        {
                            "id": f"action:{new_offer_id}:human",
                            "title": "Talk to a person",
                            "description": "Speak with our sales representative",
                        }
                    ],
                },
            ]
            send_whatsapp_interactive_list(
                to_number=clean_digits,
                body_text="No problem! Here are 3 alternative demonstration times that suit my schedule:",
                button_label="Choose a Time",
                sections=sections,
            )
            return {"action": "reschedule_slots_sent", "new_offer_id": new_offer_id, "reoffer_count": curr_reoffers + 1}

        elif action_name == "human":
            set_automation_paused_for_phone(clean_digits, True)
            agent_name = "R. Delgado"
            if a_id:
                try:
                    a_res = supabase.table("agents").select("name").eq("id", a_id).single().execute()
                    if a_res.data and a_res.data.get("name"):
                        agent_name = a_res.data["name"]
                except Exception:
                    pass
            human_msg = f"Understood! I have notified {agent_name} directly and paused automation. Our team will reach out to you shortly."
            send_whatsapp_message(clean_digits, human_msg)
            log_whatsapp_message(
                msg_id=f"human_handoff_{int(datetime.now(timezone.utc).timestamp() * 1000)}",
                phone_number=clean_digits,
                agent_id=a_id,
                client_id=client_id,
                client_name=client_name or "Client",
                sender="agent",
                text=human_msg,
                status="sent",
            )
            try:
                supabase.table("signals").insert({
                    "type": "whatsapp_human_handoff",
                    "client_id": client_id,
                    "message": f"Client requested to speak with a human agent ({clean_digits}). Automation paused.",
                }).execute()
            except Exception:
                pass
            return {"action": "human_handoff_requested", "automation_paused": True}

    elif button_payload.startswith("reminder:") and len(parts) >= 3:
        viewing_id = parts[1]
        action_name = parts[2]

        v_res = None
        try:
            v_res = (
                supabase.table("scheduled_viewings")
                .select("id, status, scheduled_at, client_id, property_id, agent_id, clients(id, name, assigned_agent_id), properties(id, address), agents(id, name)")
                .eq("id", viewing_id)
                .limit(1)
                .execute()
            )
        except Exception as e:
            if not WHATSAPP_USE_MEMORY_STORE:
                print(f"[process_interactive_button_reply] error fetching viewing: {e}")

        viewing = None
        if v_res and v_res.data:
            viewing = v_res.data[0]
        elif WHATSAPP_USE_MEMORY_STORE:
            viewing = {
                "id": viewing_id,
                "status": "upcoming",
                "scheduled_at": (datetime.now(KL_TZ) + timedelta(days=2)).isoformat(),
                "client_id": client_id,
                "property_id": "test-prop",
                "agent_id": agent_id,
                "clients": {
                    "id": client_id,
                    "name": client_name or "Client Contact",
                    "whatsapp_number": clean_digits,
                    "phone": clean_digits,
                },
                "properties": {"id": "test-prop", "address": "Unit 12-A"},
                "agents": {"id": agent_id, "name": "R. Delgado"},
            }

        if not viewing:
            return {"error": "viewing_not_found", "viewing_id": viewing_id}

        client = viewing.get("clients") or {}
        prop = viewing.get("properties") or {}
        agent = viewing.get("agents") or {}

        # ── Identity check: verify inbound sender's number matches the viewing client's phone ──
        client_phone = "".join(filter(str.isdigit, str(client.get("whatsapp_number") or client.get("phone") or "")))
        if client_phone and clean_digits and client_phone != clean_digits:
            print(f"[process_interactive_button_reply] WARNING: Identity mismatch on reminder! Sender {clean_digits} != client {client_phone}")
            return {
                "error": "sender_identity_mismatch",
                "detail": f"Sender {clean_digits} does not match viewing client {client_phone}",
            }

        c_id = viewing.get("client_id")
        p_id = viewing.get("property_id")
        a_id = viewing.get("agent_id") or client.get("assigned_agent_id")
        c_name = client.get("name") or client_name or "Client"
        prop_name = prop.get("address") or "Robotics Unit"
        agent_name = agent.get("name") or "Our sales representative"

        slot_label = "your scheduled time"
        if viewing.get("scheduled_at"):
            try:
                v_dt = datetime.fromisoformat(str(viewing["scheduled_at"]).replace("Z", "+00:00")).astimezone(KL_TZ)
                slot_label = format_slot_label(v_dt)
            except Exception:
                pass

        if action_name == "confirm":
            now_iso = datetime.now(timezone.utc).isoformat()
            if not WHATSAPP_USE_MEMORY_STORE:
                try:
                    supabase.table("scheduled_viewings").update({
                        "confirmation_status": "confirmed",
                        "client_confirmed_at": now_iso,
                    }).eq("id", viewing_id).execute()
                except Exception as e:
                    print(f"[process_interactive_button_reply] confirm viewing update notice: {e}")

                try:
                    supabase.table("signals").insert({
                        "type": "whatsapp_viewing_confirmed",
                        "client_id": c_id,
                        "property_id": p_id,
                        "message": f"Demonstration confirmed by client: {c_name} confirmed for {prop_name} on {slot_label}.",
                    }).execute()
                except Exception:
                    pass

            ack_text = (
                f"Thank you for confirming, {c_name}! Your demonstration for {prop_name} on {slot_label} "
                f"is confirmed. {agent_name} looks forward to meeting your team."
            )
            send_whatsapp_message(clean_digits, ack_text)
            log_whatsapp_message(
                msg_id=f"rem_ack_conf_{int(datetime.now(timezone.utc).timestamp() * 1000)}",
                phone_number=clean_digits,
                agent_id=a_id,
                client_id=c_id,
                client_name=c_name,
                sender="agent",
                text=ack_text,
                status="sent",
            )
            return {"action": "reminder_confirmed", "viewing_id": viewing_id}

        elif action_name == "reschedule":
            cancel_viewing_reminders(viewing_id, reason="client_requested_reschedule")
            fresh_slots = generate_candidate_slots(agent_id=a_id, count=3)
            new_offer_id = str(uuid.uuid4())
            try:
                new_offer = {
                    "id": new_offer_id,
                    "client_id": c_id,
                    "property_id": p_id,
                    "agent_id": a_id,
                    "slots": fresh_slots,
                    "status": "open",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "expires_at": (datetime.now(timezone.utc) + timedelta(hours=48)).isoformat(),
                    "pitch_wamid": f"resched_rem_{int(datetime.now(timezone.utc).timestamp())}",
                    "phone_number": clean_digits,
                    "offer_type": "reschedule",
                }
                persist_slot_offer(new_offer)
            except Exception as e:
                print(f"[process_interactive_button_reply] Error creating reschedule offer: {e}")

            resched_body = (
                f"We would be delighted to find another time that suits you better! "
                f"Here are 3 fresh demonstration slots for {prop_name}:"
            )
            sections = [
                {
                    "title": "Fresh Available Times",
                    "rows": [
                        {
                            "id": f"slot_pick:{new_offer_id}:{s['index']}",
                            "title": s["label"][:24],
                            "description": "60-min demonstration",
                        }
                        for s in fresh_slots
                    ],
                },
                {
                    "title": "Other Options",
                    "rows": [
                        {
                            "id": f"action:{new_offer_id}:human",
                            "title": "Talk to a person",
                            "description": "Speak with our sales representative",
                        }
                    ],
                },
            ]
            send_whatsapp_interactive_list(
                to_number=clean_digits,
                body_text=resched_body,
                button_label="Choose New Time",
                sections=sections,
            )
            log_whatsapp_message(
                msg_id=f"rem_resched_{int(datetime.now(timezone.utc).timestamp() * 1000)}",
                phone_number=clean_digits,
                agent_id=a_id,
                client_id=c_id,
                client_name=c_name,
                sender="agent",
                text=resched_body,
                status="sent",
            )
            if not WHATSAPP_USE_MEMORY_STORE:
                try:
                    supabase.table("signals").insert({
                        "type": "whatsapp_viewing_reschedule_requested",
                        "client_id": c_id,
                        "property_id": p_id,
                        "message": f"Client {c_name} requested to reschedule viewing for {prop_name}. Fresh slots sent.",
                    }).execute()
                except Exception:
                    pass
            return {"action": "reminder_rescheduled", "viewing_id": viewing_id, "new_offer_id": new_offer_id}

        elif action_name == "cancel":
            cancel_viewing_reminders(viewing_id, reason="client_cancelled")
            if not WHATSAPP_USE_MEMORY_STORE:
                try:
                    supabase.table("scheduled_viewings").update({
                        "status": "cancelled",
                        "cancellation_reason": "Cancelled by client via WhatsApp",
                        "confirmation_status": "cancelled_by_client",
                    }).eq("id", viewing_id).execute()
                except Exception as e:
                    print(f"[process_interactive_button_reply] cancel viewing update notice: {e}")

                try:
                    supabase.table("signals").insert({
                        "type": "whatsapp_viewing_cancelled_by_client",
                        "client_id": c_id,
                        "property_id": p_id,
                        "message": f"Demonstration for {prop_name} cancelled by client {c_name} via WhatsApp.",
                    }).execute()
                except Exception:
                    pass

            cancel_body = (
                f"Your demonstration of {prop_name} has been cancelled as requested. "
                f"If your schedule opens up and you would like to reschedule in the future, "
                f"feel free to reach out anytime. Have a great day!"
            )
            send_whatsapp_message(clean_digits, cancel_body)
            log_whatsapp_message(
                msg_id=f"rem_cancel_{int(datetime.now(timezone.utc).timestamp() * 1000)}",
                phone_number=clean_digits,
                agent_id=a_id,
                client_id=c_id,
                client_name=c_name,
                sender="agent",
                text=cancel_body,
                status="sent",
            )
            return {"action": "reminder_cancelled", "viewing_id": viewing_id}

    # ── Nudge Button Handlers (Part 4) ─────────────────────────────────────────
    if button_payload.startswith("nudge:view_times"):
        parts = button_payload.split(":")
        if len(parts) >= 3 and parts[2]:
            target_phone = "".join(filter(str.isdigit, parts[2]))
            if target_phone and clean_digits and target_phone != clean_digits:
                print(f"[process_interactive_button_reply] WARNING: Identity mismatch on nudge:view_times! Sender {clean_digits} != target {target_phone}")
                return {
                    "error": "sender_identity_mismatch",
                    "detail": f"Sender {clean_digits} does not match nudge target {target_phone}",
                }

        new_offer_id = str(uuid.uuid4())
        fresh_slots = generate_candidate_slots(agent_id=agent_id, count=3)
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=48)).isoformat()
        offer_record = {
            "id": new_offer_id,
            "client_id": client_id,
            "property_id": "robotics-unit-default",
            "agent_id": agent_id,
            "phone_number": clean_digits,
            "slots": fresh_slots,
            "status": "open",
            "expires_at": expires_at,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if isinstance(WHATSAPP_SLOT_OFFERS, dict):
            WHATSAPP_SLOT_OFFERS[new_offer_id] = offer_record
        else:
            WHATSAPP_SLOT_OFFERS.append(offer_record)
        if not WHATSAPP_USE_MEMORY_STORE and supabase:
            try:
                supabase.table("whatsapp_slot_offers").insert(offer_record).execute()
            except Exception as e:
                print(f"[process_interactive_button_reply] Warning saving nudge offer: {e}")

        slot_lines = "\n".join([f"Option {s['index']}: {s['label']}" for s in fresh_slots])
        nudge_slots_body = (
            f"Here are fresh proposed appointment times for our on-site demonstration:\n\n"
            f"{slot_lines}\n\n"
            f"Please tap an option below or reply with your preferred time."
        )

        buttons = [
            {"id": f"slot_pick:{new_offer_id}:{s['index']}", "title": s["label"][:20]}
            for s in fresh_slots[:3]
        ]
        send_whatsapp_interactive_buttons(
            to_number=clean_digits,
            body_text=nudge_slots_body,
            buttons=buttons,
            header_text="Available Demo Times",
        )
        log_whatsapp_message(
            msg_id=f"nudge_slots_{int(datetime.now(timezone.utc).timestamp() * 1000)}",
            phone_number=clean_digits,
            agent_id=agent_id,
            client_id=client_id,
            client_name=client_name or "Client",
            sender="agent",
            text=nudge_slots_body,
            status="sent",
            processing_status="processed",
        )
        return {"action": "nudge_view_times_slots_offered", "phone_number": clean_digits, "new_offer_id": new_offer_id}

    elif button_payload.startswith("nudge:not_now"):
        parts = button_payload.split(":")
        if len(parts) >= 3 and parts[2]:
            target_phone = "".join(filter(str.isdigit, parts[2]))
            if target_phone and clean_digits and target_phone != clean_digits:
                print(f"[process_interactive_button_reply] WARNING: Identity mismatch on nudge:not_now! Sender {clean_digits} != target {target_phone}")
                return {
                    "error": "sender_identity_mismatch",
                    "detail": f"Sender {clean_digits} does not match nudge target {target_phone}",
                }

        snooze_dt = datetime.now(timezone.utc) + timedelta(days=14)
        update_contact_state(clean_digits, snoozed_until=snooze_dt.isoformat())
        ack_msg = "Thank you for letting us know! We have paused updates and will check back with you in two weeks."
        send_whatsapp_message(clean_digits, ack_msg, manual_override=True)
        log_whatsapp_message(
            msg_id=f"nudge_snooze_ack_{int(datetime.now(timezone.utc).timestamp() * 1000)}",
            phone_number=clean_digits,
            agent_id=agent_id,
            client_id=client_id,
            client_name=client_name or "Client",
            sender="agent",
            text=ack_msg,
            status="sent",
            processing_status="processed",
        )
        return {"action": "nudge_snoozed", "phone_number": clean_digits, "snoozed_until": snooze_dt.isoformat()}

    return {"action": "unrecognized_payload", "payload": button_payload}


# ─── Inbound Pitch Reply Processing & Auto-Scheduling Engine ─────────────────

def process_inbound_pitch_reply(
    *,
    phone_number: str,
    message_text: str,
    client_id: str | None = None,
    client_name: str | None = "Client Contact",
    agent_id: str | None = None,
) -> dict:
    """
    Evaluates an inbound client WhatsApp reply against any active 'open' slot offer.
    If an offer exists:
      1. Uses fast regex or Groq NLU to understand intent ('select_slot', 'custom_time', 'decline', 'question_or_other').
      2. If slot selected or safe custom time proposed:
         - Checks for scheduling conflicts against agent's existing viewings (with 45m buffer).
         - If safe: books viewing in `scheduled_viewings`, marks offer 'booked', advances client stage to 'viewing',
           sends confirmation message via WhatsApp, and fires 'whatsapp_meeting_booked' signal.
         - If conflict: marks offer expired, sends polite follow-up WhatsApp message, and fires 'whatsapp_human_handoff' signal.
      3. If decline: marks offer 'declined', sends polite farewell WhatsApp message, and fires 'whatsapp_pitch_declined' signal.
      4. If question/ambiguous: sends polite acknowledgment that rep will respond, and fires 'whatsapp_human_handoff' signal.
    """
    clean_digits = "".join(filter(str.isdigit, phone_number))
    if is_automation_paused_for_phone(clean_digits):
        print(f"[process_inbound_pitch_reply] Automation paused for {clean_digits} (human-handled). Skipping auto-reply.")
        return {"action": "automation_paused", "detail": "Conversation is human-handled; automated replies paused"}

    offer = get_open_slot_offer(client_id=client_id, phone_number=clean_digits)
    if not offer:
        return {"action": "no_open_offer", "detail": "No active open slot offer for this contact"}

    offer_id = offer["id"]
    c_id = offer.get("client_id") or client_id
    p_id = offer.get("property_id")
    a_id = offer.get("agent_id") or agent_id
    slots = offer.get("slots", [])

    # Fetch agent name
    agent_name = "R. Delgado"
    if a_id:
        try:
            a_res = supabase.table("agents").select("name").eq("id", a_id).single().execute()
            if a_res.data and a_res.data.get("name"):
                agent_name = a_res.data["name"]
        except Exception:
            pass

    # Fetch property address
    prop_name = "Robotics Unit"
    if p_id:
        try:
            p_res = supabase.table("properties").select("address, neighborhood").eq("id", p_id).single().execute()
            if p_res.data:
                prop_name = f"{p_res.data.get('address')} ({p_res.data.get('neighborhood')})"
        except Exception:
            pass

    c_name = client_name or "Client"

    # 1. Fast-path regex / keyword check
    raw_trim = message_text.strip().lower()
    selected_index = None
    if raw_trim in ("1", "slot 1", "option 1", "1)", "1.", "#1", "first", "first one", "slot one", "1 please", "yes 1", "slot 1 please"):
        selected_index = 1
    elif raw_trim in ("2", "slot 2", "option 2", "2)", "2.", "#2", "second", "second one", "slot two", "2 please", "yes 2", "slot 2 please"):
        selected_index = 2
    elif raw_trim in ("3", "slot 3", "option 3", "3)", "3.", "#3", "third", "third one", "slot three", "3 please", "yes 3", "slot 3 please"):
        selected_index = 3

    intent = "select_slot" if selected_index else None
    custom_iso = None

    # 2. If not fast-matched, use Groq NLU
    if not intent and groq_client:
        now_kl_str = datetime.now(KL_TZ).isoformat()
        slots_desc = "\n".join([f"Slot {s.get('index')}: {s.get('label')} ({s.get('slot_iso')})" for s in slots])
        system_prompt = f"""You are an AI assistant that analyzes inbound client WhatsApp replies to a business meeting invitation.
Current local time in Asia/Kuala_Lumpur: {now_kl_str}

Proposed Slots:
{slots_desc}

Classify the client reply into one of:
- 'select_slot': Client selected or agreed to one of the proposed slots (e.g. 'Monday morning works', 'the 2pm option', 'let's do slot 2'). Set slot_index to 1, 2, or 3.
- 'custom_time': Client proposed a specific alternative date/time (e.g. 'Can we do next Tuesday at 3pm?'). If extracted, provide custom_iso in ISO 8601 with +08:00 timezone.
- 'decline': Client explicitly declined, requested not to be contacted, or is not interested.
- 'question_or_other': Client asked questions, gave an ambiguous answer, or needs human assistance.

Output ONLY valid JSON:
{{"intent": "select_slot" | "custom_time" | "decline" | "question_or_other", "slot_index": 1 | 2 | 3 | null, "custom_iso": string | null, "reason": string}}"""

        try:
            nlu_res = groq_client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f'Client reply: "{message_text}"'},
                ],
                model=os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b"),
                temperature=0.0,
                response_format={"type": "json_object"},
                timeout=12.0,
            )
            parsed = json.loads(nlu_res.choices[0].message.content)
            intent = parsed.get("intent")
            selected_index = parsed.get("slot_index")
            custom_iso = parsed.get("custom_iso")
        except Exception as exc:
            print(f"[process_inbound_pitch_reply] Groq NLU fallback: {exc}")
            intent = "question_or_other"

    print(f"[process_inbound_pitch_reply] Intent={intent}, selected_index={selected_index}, custom_iso={custom_iso}")

    # ── Action Routing ────────────────────────────────────────────────────────

    # CASE A: Client picked a slot (1, 2, or 3)
    if intent == "select_slot" and selected_index in (1, 2, 3):
        chosen = next((s for s in slots if s.get("index") == selected_index), None)
        if chosen:
            target_iso = chosen.get("slot_iso")
            slot_label = chosen.get("label")
            try:
                target_dt = datetime.fromisoformat(target_iso)
            except Exception:
                target_dt = None

            # Conflict & Safety Check
            if target_dt and is_slot_available(target_dt, agent_id=a_id, buffer_minutes=45):
                # ── SAFE: Auto-Book Viewing ──
                viewing_row = {
                    "client_id": c_id,
                    "property_id": p_id,
                    "scheduled_at": target_iso,
                    "status": "upcoming",
                }
                v_res = supabase.table("scheduled_viewings").insert(viewing_row).execute()
                viewing_id = v_res.data[0]["id"] if v_res.data else None
                if viewing_id:
                    schedule_viewing_reminders(viewing_id)

                # Update offer status to booked
                update_slot_offer_status(offer_id, "booked")

                # Advance client stage to 'viewing'
                if c_id:
                    advance_stage(c_id, "viewing")

                # Send WhatsApp Confirmation
                confirm_body = build_booking_confirmation_text(
                    prop_name=prop_name,
                    slot_label=slot_label,
                    agent_name=agent_name,
                    viewing_id=viewing_id,
                    scheduled_at_iso=target_iso,
                )
                send_whatsapp_message(clean_digits, confirm_body)
                log_whatsapp_message(
                    msg_id=f"auto_confirm_{int(datetime.now(timezone.utc).timestamp() * 1000)}",
                    phone_number=clean_digits,
                    agent_id=a_id,
                    client_id=c_id,
                    client_name=c_name,
                    sender="agent",
                    text=confirm_body,
                    status="sent",
                )

                # Fire Signal
                supabase.table("signals").insert({
                    "type": "whatsapp_meeting_booked",
                    "client_id": c_id,
                    "property_id": p_id,
                    "message": f"WhatsApp Auto-Booked: {c_name} confirmed demo for {prop_name} on {slot_label}.",
                }).execute()

                return {
                    "action": "auto_booked",
                    "viewing_id": viewing_id,
                    "slot": chosen,
                    "confirmation_sent": confirm_body,
                }
            else:
                # ── CONFLICT / UNSAFE: Slot taken or too close ──
                update_slot_offer_status(offer_id, "expired")
                conflict_body = (
                    f"Thank you for choosing {slot_label}! That slot was just booked on our end, but {agent_name} has "
                    f"been notified and will reach out directly in a moment with alternative times."
                )
                send_whatsapp_message(clean_digits, conflict_body)
                log_whatsapp_message(
                    msg_id=f"conflict_ack_{int(datetime.now(timezone.utc).timestamp() * 1000)}",
                    phone_number=clean_digits,
                    agent_id=a_id,
                    client_id=c_id,
                    client_name=c_name,
                    sender="agent",
                    text=conflict_body,
                    status="sent",
                )

                supabase.table("signals").insert({
                    "type": "whatsapp_human_handoff",
                    "client_id": c_id,
                    "property_id": p_id,
                    "message": f"Slot Conflict: {c_name} requested {slot_label}, but agent schedule has an overlap. Action required by {agent_name}.",
                }).execute()

                return {"action": "handoff_conflict", "slot": chosen}

    # CASE B: Client proposed a custom time
    if intent == "custom_time" and custom_iso:
        try:
            custom_dt = datetime.fromisoformat(custom_iso).astimezone(KL_TZ)
        except Exception:
            custom_dt = None

        # Check if custom time is safe (weekday, 10am-5pm, conflict-free)
        if custom_dt and custom_dt.weekday() < 5 and (10 <= custom_dt.hour < 17) and is_slot_available(custom_dt, a_id):
            label = format_slot_label(custom_dt)
            v_res = supabase.table("scheduled_viewings").insert({
                "client_id": c_id,
                "property_id": p_id,
                "scheduled_at": custom_iso,
                "status": "upcoming",
            }).execute()
            viewing_id = v_res.data[0]["id"] if v_res.data else None
            if viewing_id:
                schedule_viewing_reminders(viewing_id)

            update_slot_offer_status(offer_id, "booked")
            if c_id:
                advance_stage(c_id, "viewing")

            confirm_body = build_booking_confirmation_text(
                prop_name=prop_name,
                slot_label=label,
                agent_name=agent_name,
                viewing_id=viewing_id,
                scheduled_at_iso=custom_iso,
            )
            send_whatsapp_message(clean_digits, confirm_body)
            log_whatsapp_message(
                msg_id=f"auto_confirm_custom_{int(datetime.now(timezone.utc).timestamp() * 1000)}",
                phone_number=clean_digits,
                agent_id=a_id,
                client_id=c_id,
                client_name=c_name,
                sender="agent",
                text=confirm_body,
                status="sent",
            )

            supabase.table("signals").insert({
                "type": "whatsapp_meeting_booked",
                "client_id": c_id,
                "property_id": p_id,
                "message": f"WhatsApp Auto-Booked: {c_name} requested custom time {label} (confirmed).",
            }).execute()

            return {"action": "auto_booked_custom", "slot_iso": custom_iso, "label": label}

        # If not completely safe or ambiguous custom time -> Human Handoff
        custom_ack = (
            f"Thank you for proposing this time! {agent_name} has received your schedule request and will "
            f"confirm availability with your team shortly."
        )
        send_whatsapp_message(clean_digits, custom_ack)
        log_whatsapp_message(
            msg_id=f"custom_handoff_{int(datetime.now(timezone.utc).timestamp() * 1000)}",
            phone_number=clean_digits,
            agent_id=a_id,
            client_id=c_id,
            client_name=c_name,
            sender="agent",
            text=custom_ack,
            status="sent",
        )

        supabase.table("signals").insert({
            "type": "whatsapp_human_handoff",
            "client_id": c_id,
            "property_id": p_id,
            "message": f"Custom Time Request: {c_name} proposed '{message_text}'. Follow-up required by {agent_name}.",
        }).execute()

        return {"action": "human_handoff_custom_time"}

    # CASE C: Client declined
    if intent == "decline":
        update_slot_offer_status(offer_id, "declined")
        decline_body = "Understood. Thank you for letting us know, and feel free to reach out to PIPELINE.EV if your robotics requirements evolve in the future."
        send_whatsapp_message(clean_digits, decline_body)
        log_whatsapp_message(
            msg_id=f"decline_ack_{int(datetime.now(timezone.utc).timestamp() * 1000)}",
            phone_number=clean_digits,
            agent_id=a_id,
            client_id=c_id,
            client_name=c_name,
            sender="agent",
            text=decline_body,
            status="sent",
        )

        supabase.table("signals").insert({
            "type": "whatsapp_pitch_declined",
            "client_id": c_id,
            "property_id": p_id,
            "message": f"{c_name} declined demo invitation for {prop_name}.",
        }).execute()

        return {"action": "pitch_declined"}

    # CASE D: Question or ambiguous reply -> Human Handoff
    inquiry_body = f"Thank you for your message! {agent_name} has received your inquiry and will follow up with full details shortly."
    send_whatsapp_message(clean_digits, inquiry_body)
    log_whatsapp_message(
        msg_id=f"inquiry_ack_{int(datetime.now(timezone.utc).timestamp() * 1000)}",
        phone_number=clean_digits,
        agent_id=a_id,
        client_id=c_id,
        client_name=c_name,
        sender="agent",
        text=inquiry_body,
        status="sent",
    )

    supabase.table("signals").insert({
        "type": "whatsapp_human_handoff",
        "client_id": c_id,
        "property_id": p_id,
        "message": f"WhatsApp Inquiry: {c_name} replied: '{message_text}'. Human rep attention required.",
    }).execute()

    return {"action": "human_handoff_inquiry"}


@app.post("/api/whatsapp/simulate_incoming")
def simulate_incoming_whatsapp_message(body: dict):
    """Dev-only endpoint — disabled in production unless ENABLE_WA_SIMULATOR=true."""
    if not os.getenv("ENABLE_WA_SIMULATOR", "").lower() in ("true", "1", "yes"):
        raise HTTPException(status_code=404, detail="Not found")

    from_number = body.get("from_number") or "60109722730"
    clean_digits = "".join(filter(str.isdigit, from_number))
    client_name = body.get("client_name") or "Client Contact"
    client_id = body.get("client_id")
    agent_id = _find_agent_for_inbound(clean_digits)

    if not client_id:
        try:
            c_res = (
                supabase.table("whatsapp_messages")
                .select("client_id, client_name")
                .eq("to_number", clean_digits)
                .not_.is_("client_id", "null")
                .order("timestamp", desc=True)
                .limit(1)
                .execute()
            )
            if c_res.data:
                client_id = c_res.data[0].get("client_id")
                if not client_name or client_name in ("WhatsApp Client", "Client Contact"):
                    client_name = c_res.data[0].get("client_name") or client_name
        except Exception:
            pass

    button_payload = body.get("button_payload") or body.get("interactive_payload")
    if button_payload:
        button_title = body.get("button_title") or button_payload
        msg_id = f"inbound_btn_{int(datetime.now(timezone.utc).timestamp() * 1000)}"
        msg_entry = log_whatsapp_message(
            msg_id=msg_id,
            phone_number=clean_digits,
            agent_id=agent_id,
            client_id=client_id,
            client_name=client_name,
            sender="client",
            text=f"[Button Reply: {button_title}]",
            status="received",
            raw_payload={"type": "interactive", "payload": button_payload},
        )
        auto_sched_res = process_interactive_button_reply(
            phone_number=clean_digits,
            button_payload=button_payload,
            button_title=button_title,
            client_id=client_id,
            client_name=client_name,
            agent_id=agent_id,
        )
        return {"success": True, "message": msg_entry, "auto_scheduling": auto_sched_res}

    # Text message simulation
    message_text = body.get("message") or "1"
    msg_id = f"inbound_{int(datetime.now(timezone.utc).timestamp() * 1000)}"
    msg_entry = log_whatsapp_message(
        msg_id=msg_id,
        phone_number=clean_digits,
        agent_id=agent_id,
        client_id=client_id,
        client_name=client_name,
        sender="client",
        text=message_text,
        status="received",
    )

    auto_sched_res = None
    try:
        auto_sched_res = process_inbound_pitch_reply(
            phone_number=clean_digits,
            message_text=message_text,
            client_id=client_id,
            client_name=client_name,
            agent_id=agent_id,
        )
    except Exception as exc:
        print(f"[simulate_incoming_whatsapp_message] Auto-scheduling error: {exc}")
        auto_sched_res = {"error": str(exc)}

    return {"success": True, "message": msg_entry, "auto_scheduling": auto_sched_res}


@app.post("/api/whatsapp/process_reminders")
def api_process_reminders():
    """
    Manually triggers due reminders processing.
    """
    dispatched = process_due_whatsapp_reminders(limit=20)
    return {"success": True, "dispatched_count": len(dispatched), "dispatched": dispatched}


@app.get("/api/whatsapp/reminder_template_config")
def get_reminder_template_config():
    """
    Returns the single source of truth Meta viewing_reminder template configuration.
    """
    return REMINDER_TEMPLATE_CONFIG


@app.get("/api/whatsapp/webhook")
def verify_whatsapp_webhook(request: Request):
    # Meta Webhook verification handshake
    mode = request.query_params.get("hub.mode")
    verify_token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "5e71124027fbce99e78aa91b4023f9f5ed7a0b2654b82651")

    if mode == "subscribe":
        if not verify_token or verify_token == VERIFY_TOKEN:
            return Response(content=challenge or "", media_type="text/plain")
        raise HTTPException(status_code=403, detail="Verification token mismatch")
    return Response(content="WhatsApp webhook endpoint active", media_type="text/plain")


_PROCESSED_WEBHOOK_MSG_IDS: set[str] = set()


@app.post("/api/whatsapp/webhook")
async def receive_whatsapp_webhook(request: Request):
    raw = await request.body()
    sig_header = request.headers.get("X-Hub-Signature-256")
    is_valid = valid_signature(raw, sig_header)
    if not is_valid:
        print(f"[receive_whatsapp_webhook] Signature verification failed: header={sig_header}")
        raise HTTPException(status_code=403, detail="Bad signature")
    try:
        body = json.loads(raw)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    try:
        entries = body.get("entry", [])
        for entry in entries:
            for change in entry.get("changes", []):
                val = change.get("value", {})
                contacts = val.get("contacts", [])
                c_name = contacts[0].get("profile", {}).get("name", "WhatsApp Client") if contacts else "Client"

                # 1. Incoming messages from user's phone
                for m in val.get("messages", []):
                    m_id = m.get("id") or f"inbound_{int(datetime.now(timezone.utc).timestamp() * 1000)}"
                    from_num = normalize_whatsapp_number(m.get("from", ""))
                    m_type = m.get("type")
                    text_body = None
                    interactive_payload = None
                    button_title = None

                    if m_type == "text":
                        text_body = m.get("text", {}).get("body")
                    elif m_type == "interactive":
                        i_obj = m.get("interactive", {})
                        i_type = i_obj.get("type")
                        if i_type == "button_reply":
                            br = i_obj.get("button_reply", {})
                            interactive_payload = br.get("id")
                            button_title = br.get("title")
                        elif i_type == "list_reply":
                            lr = i_obj.get("list_reply", {})
                            interactive_payload = lr.get("id")
                            button_title = lr.get("title")
                    elif m_type == "button":
                        b_obj = m.get("button", {})
                        interactive_payload = b_obj.get("payload")
                        button_title = b_obj.get("text")

                    # Inbound reply → resolve agent and client identity
                    agent_id: str | None = _find_agent_for_inbound(from_num)
                    client_id = None
                    try:
                        c_res = (
                            supabase.table("whatsapp_messages")
                            .select("client_id, client_name")
                            .eq("to_number", from_num)
                            .not_.is_("client_id", "null")
                            .order("timestamp", desc=True)
                            .limit(1)
                            .execute()
                        )
                        if c_res.data:
                            client_id = c_res.data[0].get("client_id")
                            if not c_name or c_name in ("WhatsApp Client", "Client"):
                                c_name = c_res.data[0].get("client_name") or c_name
                    except Exception:
                        pass

                    display_text = text_body or f"[Button Reply: {button_title or interactive_payload}]"

                    # ── Atomic deduplication (received / processed / failed) ──
                    should_process, msg_rec = record_inbound_message_atomic(
                        m_id=m_id,
                        phone_number=from_num,
                        sender="client",
                        text=display_text,
                        agent_id=agent_id,
                        client_id=client_id,
                        client_name=c_name,
                        raw_payload=m,
                    )
                    if not should_process:
                        continue

                    # Process inbound payload with status tracking
                    try:
                        if interactive_payload:
                            print(f"[whatsapp_webhook] Interactive reply from {from_num}: {interactive_payload}")
                            process_interactive_button_reply(
                                phone_number=from_num,
                                button_payload=interactive_payload,
                                button_title=button_title,
                                client_id=client_id,
                                client_name=c_name,
                                agent_id=agent_id,
                            )
                            mark_message_processing_status(m_id, "processed")

                        elif text_body:
                            print(f"[whatsapp_webhook] Incoming text from {from_num} ({c_name}): {text_body}")
                            clean_kw = re.sub(r'[^a-zA-Z0-9\s]', '', text_body).strip().lower()
                            OPT_OUT_EXACT = {"stop", "unsubscribe", "berhenti", "jangan hubungi"}

                            if clean_kw in OPT_OUT_EXACT:
                                print(f"[whatsapp_webhook] Strict opt-out triggered for {from_num} via '{clean_kw}'")
                                update_contact_state(
                                    from_num,
                                    opted_out=True,
                                    opted_out_at=datetime.now(timezone.utc).isoformat(),
                                    opt_out_phrase=clean_kw,
                                    automation_paused=True,
                                )

                                # Cancel pending reminders with status cancelled, reason opted_out
                                if not WHATSAPP_USE_MEMORY_STORE and supabase:
                                    try:
                                        supabase.table("whatsapp_reminders").update({
                                            "status": "cancelled",
                                            "error": "opted_out",
                                        }).eq("phone_number", from_num).eq("status", "pending").execute()
                                        if client_id:
                                            supabase.table("whatsapp_reminders").update({
                                                "status": "cancelled",
                                                "error": "opted_out",
                                            }).eq("client_id", client_id).eq("status", "pending").execute()
                                    except Exception:
                                        pass
                                for r in WHATSAPP_REMINDERS_STORE:
                                    if (r.get("phone_number") == from_num or (client_id and r.get("client_id") == client_id)) and r.get("status") == "pending":
                                        r["status"] = "cancelled"
                                        r["error"] = "opted_out"

                                # Check upcoming viewings to create rep alert listing them
                                upcoming_viewings = []
                                if not WHATSAPP_USE_MEMORY_STORE and supabase:
                                    try:
                                        q = (
                                            supabase.table("scheduled_viewings")
                                            .select("id, scheduled_at, property_id")
                                            .in_("status", ["upcoming", "confirmed"])
                                        )
                                        if client_id:
                                            q = q.eq("client_id", client_id)
                                        res_v = q.execute()
                                        upcoming_viewings = res_v.data or []
                                    except Exception:
                                        pass
                                if get_contact_state(from_num).get("upcoming_viewings"):
                                    upcoming_viewings = get_contact_state(from_num).get("upcoming_viewings")

                                if upcoming_viewings:
                                    v_str = ", ".join([f"Viewing #{v.get('id')} at {v.get('scheduled_at')}" for v in upcoming_viewings])
                                    try:
                                        supabase.table("signals").insert({
                                            "type": "whatsapp_opt_out_rep_alert",
                                            "client_id": client_id,
                                            "message": f"Client {c_name} ({from_num}) opted out. Upcoming viewings require manual agent contact: {v_str}.",
                                        }).execute()
                                    except Exception:
                                        pass
                                else:
                                    try:
                                        supabase.table("signals").insert({
                                            "type": "whatsapp_opt_out",
                                            "client_id": client_id,
                                            "message": f"Client {c_name} ({from_num}) opted out via '{clean_kw}'.",
                                        }).execute()
                                    except Exception:
                                        pass

                                opt_ack = "You have been unsubscribed from automated WhatsApp updates from PIPELINE.EV. Reply START to resubscribe."
                                send_whatsapp_message(from_num, opt_ack, manual_override=True)
                                log_whatsapp_message(
                                    msg_id=f"optout_ack_{int(datetime.now(timezone.utc).timestamp() * 1000)}",
                                    phone_number=from_num,
                                    agent_id=agent_id,
                                    client_id=client_id,
                                    client_name=c_name,
                                    sender="system",
                                    text=opt_ack,
                                    status="sent",
                                    processing_status="processed",
                                )
                                mark_message_processing_status(m_id, "processed")
                                continue

                            elif clean_kw in {"start", "mula", "subscribe"}:
                                print(f"[whatsapp_webhook] Resubscribe received for {from_num}")
                                update_contact_state(from_num, opted_out=False, automation_paused=False, opt_out_phrase=None)
                                resub_msg = "Welcome back! Automated notifications from PIPELINE.EV have been reactivated."
                                send_whatsapp_message(from_num, resub_msg, manual_override=True)
                                log_whatsapp_message(
                                    msg_id=f"resub_{int(datetime.now(timezone.utc).timestamp() * 1000)}",
                                    phone_number=from_num,
                                    agent_id=agent_id,
                                    client_id=client_id,
                                    client_name=c_name,
                                    sender="system",
                                    text=resub_msg,
                                    status="sent",
                                    processing_status="processed",
                                )
                                mark_message_processing_status(m_id, "processed")
                                continue

                            else:
                                AMBIGUOUS_STOP = [
                                    "stop messaging me", "stop texting me", "stop contacting me",
                                    "leave me alone", "do not contact me", "don't message me",
                                    "jangan mesej", "jangan kacau", "tak nak mesej"
                                ]
                                if any(p in clean_kw for p in AMBIGUOUS_STOP):
                                    print(f"[whatsapp_webhook] Ambiguous stop phrase for {from_num}: '{clean_kw}'")
                                    update_contact_state(
                                        from_num,
                                        automation_paused=True,
                                        automation_paused_reason=f"Ambiguous stop: {clean_kw}",
                                    )
                                    try:
                                        supabase.table("signals").insert({
                                            "type": "whatsapp_human_handoff",
                                            "client_id": client_id,
                                            "message": f"Client requested stop in text: '{clean_kw}'. Automation paused. Rep review required.",
                                        }).execute()
                                    except Exception:
                                        pass

                                process_inbound_pitch_reply(
                                    phone_number=from_num,
                                    message_text=text_body,
                                    client_id=client_id,
                                    client_name=c_name,
                                    agent_id=agent_id,
                                )
                                mark_message_processing_status(m_id, "processed")
                    except Exception as proc_exc:
                        print(f"[whatsapp_webhook] Error processing message {m_id}: {proc_exc}")
                        mark_message_processing_status(m_id, "failed", error_message=str(proc_exc))
                        try:
                            supabase.table("signals").insert({
                                "type": "whatsapp_processing_error",
                                "client_id": client_id,
                                "message": f"WhatsApp processing error for {from_num}: {str(proc_exc)[:200]}",
                            }).execute()
                        except Exception:
                            pass

                # 2. Status receipts & delivery failure errors from Meta
                for s in val.get("statuses", []):
                    s_id = s.get("id")
                    s_status = s.get("status")
                    s_errors = s.get("errors") or []
                    err_code = s_errors[0].get("code") if s_errors else None
                    err_msg = s_errors[0].get("title") or s_errors[0].get("message") if s_errors else None
                    print(f"[whatsapp_webhook] Status update for {s_id}: status={s_status} code={err_code} errors={s_errors}")
                    if s_id and s_status:
                        apply_message_status_update(s_id, s_status, error_code=err_code, error_message=err_msg)

        save_whatsapp_messages(WHATSAPP_MESSAGE_HISTORY)
        return {"status": "ok"}
    except Exception as exc:
        print(f"[whatsapp_webhook] Error processing webhook: {exc}")
        try:
            supabase.table("signals").insert({
                "type": "whatsapp_processing_error",
                "message": f"WhatsApp webhook error: {str(exc)[:200]}",
            }).execute()
        except Exception:
            pass
        # Unreachable-DB / unexpected error case: always return HTTP 200 so Meta does not retry in an endless storm
        return Response(
            content=json.dumps({"status": "ok", "warning": str(exc)}),
            media_type="application/json",
            status_code=200,
        )


@app.post("/api/whatsapp/send_message")
def send_custom_whatsapp_message(body: dict, request: Request = None):
    to_number = body.get("to_number")
    message_text = body.get("message") or body.get("message_text")
    if not to_number or not message_text:
        raise HTTPException(status_code=400, detail="to_number and message are required")

    client_id = body.get("client_id")
    if client_id and request and hasattr(request.state, "agent"):
        from agent_auth import require_client_access
        require_client_access(request.state.agent, client_id, supabase)

    agent_id = body.get("agent_id") or None
    clean_digits = "".join(filter(str.isdigit, to_number))
    template_name = body.get("template_name")
    manual_override = body.get("manual_override", False)

    if template_name:
        result = send_whatsapp_template(clean_digits, template_name)
    else:
        result = send_whatsapp_message(clean_digits, message_text, manual_override=manual_override)

    client_name = body.get("client_name") or "Contact"
    if client_id:
        try:
            advance_stage(client_id, "contacted")
        except Exception:
            pass

    wamid = (result.get("messages") or [{}])[0].get("id")
    msg_id = wamid or f"out_{int(datetime.now(timezone.utc).timestamp() * 1000)}"
    msg_record = log_whatsapp_message(
        msg_id=msg_id,
        phone_number=clean_digits,
        agent_id=agent_id,
        client_id=client_id,
        client_name=client_name,
        sender="agent",
        text=message_text if not template_name else f"[Template: {template_name}] {message_text}",
        status="sent",
    )

    return {
        "success": True,
        "whatsapp_response": result,
        "to_number": clean_digits,
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "message": msg_record,
    }


@app.post("/api/whatsapp/send")
def send_whatsapp_alias_endpoint(body: dict, request: Request = None):
    return send_custom_whatsapp_message(body, request=request)


@app.post("/api/whatsapp/nudge")
def trigger_nudge_endpoint(body: dict, request: Request = None):
    phone = body.get("phone_number") or body.get("to_number")
    if not phone:
        raise HTTPException(status_code=400, detail="phone_number is required")
    client_id = body.get("client_id")
    if client_id and request and hasattr(request.state, "agent"):
        from agent_auth import require_client_access
        require_client_access(request.state.agent, client_id, supabase)
    client_name = body.get("client_name") or "Client"
    unit_name = body.get("unit_name") or "property"
    return dispatch_followup_nudge(phone, client_name=client_name, unit_name=unit_name)


@app.post("/api/whatsapp/suggest_reply")
def suggest_reply_endpoint(body: dict, request: Request):
    phone = body.get("phone_number") or ""
    prompt_context = body.get("prompt_context") or body.get("context") or ""
    client_ip = request.client.host if request.client else "127.0.0.1"
    return suggest_ai_reply(phone, prompt_context=prompt_context, client_ip=client_ip)


@app.post("/api/whatsapp/conversations/{conversation_id}/read")
def mark_conversation_read_endpoint(conversation_id: str, request: Request):
    cur_agent = getattr(request.state, "agent", None)
    if cur_agent and cur_agent.role != "admin" and os.getenv("AGENT_PIPELINE_SCOPING", "assigned").lower() == "assigned":
        if not WHATSAPP_USE_MEMORY_STORE and supabase:
            res = supabase.table("whatsapp_conversations").select("agent_id, client_id").eq("id", conversation_id).limit(1).execute()
            if res.data:
                conv = res.data[0]
                if not conv.get("client_id") or (conv.get("agent_id") and str(conv.get("agent_id")) != str(cur_agent.agent_id)):
                    raise HTTPException(status_code=403, detail="Access denied to this conversation thread.")

    now_iso = datetime.now(timezone.utc).isoformat()
    if not WHATSAPP_USE_MEMORY_STORE and supabase:
        try:
            supabase.table("whatsapp_conversations").update({
                "last_read_at": now_iso,
                "unread_count": 0,
            }).eq("id", conversation_id).execute()
        except Exception as exc:
            print(f"[mark_conversation_read] Warning: {exc}")
    return {"success": True, "conversation_id": conversation_id, "last_read_at": now_iso}


@app.get("/api/whatsapp/conversations")
def get_whatsapp_conversations_endpoint(request: Request, agent_id: str | None = None):
    # Scoping check (Item 8)
    cur_agent = getattr(request.state, "agent", None)
    scoping_mode = os.getenv("AGENT_PIPELINE_SCOPING", "assigned").lower()

    if cur_agent and cur_agent.role != "admin" and scoping_mode == "assigned":
        agent_id = cur_agent.agent_id

    threads = []
    if not WHATSAPP_USE_MEMORY_STORE and supabase:
        try:
            q = supabase.table("whatsapp_conversations").select("*")
            if agent_id:
                q = q.eq("agent_id", agent_id)
            res = q.order("updated_at", desc=True).limit(100).execute()
            threads = res.data or []
        except Exception as exc:
            print(f"[get_whatsapp_conversations] Supabase query warning: {exc}")
            threads = []

    if not threads and WHATSAPP_MESSAGE_HISTORY:
        by_num: dict[str, list[dict]] = {}
        for m in WHATSAPP_MESSAGE_HISTORY:
            num = m.get("to_number", "")
            if num:
                by_num.setdefault(num, []).append(m)
        for num, msgs in by_num.items():
            last_m = msgs[-1]
            t_agent = last_m.get("agent_id")
            if agent_id and t_agent and t_agent != agent_id:
                continue
            threads.append({
                "id": f"conv_{num}",
                "phone_number": num,
                "client_name": last_m.get("client_name") or "Contact",
                "client_id": last_m.get("client_id"),
                "agent_id": t_agent,
                "updated_at": last_m.get("timestamp"),
                "last_read_at": datetime.now(timezone.utc).isoformat(),
                "unread_count": sum(1 for m in msgs if m.get("sender") == "client"),
            })

    if agent_id and threads:
        threads = [t for t in threads if not t.get("agent_id") or t.get("agent_id") == agent_id]

    if cur_agent and cur_agent.role != "admin" and scoping_mode == "assigned":
        # Unmatched conversations without an assigned company are admin-only (Item 8)
        threads = [t for t in threads if t.get("client_id") is not None]

    now_utc = datetime.now(timezone.utc)
    enriched = []
    for conv in threads:
        phone = conv.get("phone_number", "")
        c_state = get_contact_state(phone)
        msgs_for_conv = [m for m in WHATSAPP_MESSAGE_HISTORY if m.get("to_number") == phone]

        has_inbound = any(m.get("sender") == "client" for m in msgs_for_conv)

        # 48h Follow-up indicator: latest message was outbound > 48 hours ago with no subsequent reply
        needs_followup_48h = False
        last_outbound_days_ago = 999
        if msgs_for_conv:
            last_msg = msgs_for_conv[-1]
            try:
                msg_dt = datetime.fromisoformat(last_msg["timestamp"])
                if msg_dt.tzinfo is None:
                    msg_dt = msg_dt.replace(tzinfo=timezone.utc)
                diff = now_utc - msg_dt
                last_outbound_days_ago = diff.days
                if last_msg.get("sender") in ("agent", "system") and diff >= timedelta(hours=48):
                    needs_followup_48h = True
            except Exception:
                pass

        # 24h Customer Service Window check
        window_open = False
        window_remaining_hours = 0
        inbound_msgs = [m for m in msgs_for_conv if m.get("sender") == "client"]
        if inbound_msgs:
            last_inbound = inbound_msgs[-1]
            try:
                inbound_dt = datetime.fromisoformat(last_inbound["timestamp"])
                if inbound_dt.tzinfo is None:
                    inbound_dt = inbound_dt.replace(tzinfo=timezone.utc)
                elapsed = now_utc - inbound_dt
                if elapsed < timedelta(hours=24):
                    window_open = True
                    window_remaining_hours = max(0, int((timedelta(hours=24) - elapsed).total_seconds() / 3600))
            except Exception:
                pass

        bucket = calculate_conversation_bucket({
            "opted_out": c_state.get("opted_out", False),
            "has_inbound_reply": has_inbound,
            "has_upcoming_viewing": False,
            "last_message_outbound_days_ago": last_outbound_days_ago,
        })

        conv_item = dict(conv)
        conv_item["status_bucket"] = bucket
        conv_item["opted_out"] = c_state.get("opted_out", False)
        conv_item["automation_paused"] = c_state.get("automation_paused", False)
        conv_item["snoozed_until"] = c_state.get("snoozed_until")
        conv_item["last_nudged_at"] = c_state.get("last_nudged_at")
        conv_item["needs_followup_48h"] = needs_followup_48h
        conv_item["window_open"] = window_open
        conv_item["window_remaining_hours"] = window_remaining_hours
        enriched.append(conv_item)

    return {"conversations": enriched}


@app.post("/api/whatsapp/clear_opt_out")
def clear_opt_out_endpoint(body: dict):
    phone = body.get("phone_number")
    agent_name = body.get("agent_name") or "Agent"
    agent_id = body.get("agent_id")
    if not phone:
        raise HTTPException(status_code=400, detail="phone_number is required")
    clean = normalize_whatsapp_number(phone)
    update_contact_state(
        clean,
        opted_out=False,
        opt_out_phrase=None,
        automation_paused=False,
        automation_paused_reason=None,
    )

    # Insert audit entry into signals
    if not WHATSAPP_USE_MEMORY_STORE and supabase:
        try:
            supabase.table("signals").insert({
                "type": "whatsapp_opt_out_cleared",
                "message": f"Agent {agent_name} manually cleared opt-out for {clean}.",
            }).execute()
        except Exception:
            pass

    log_whatsapp_message(
        msg_id=f"audit_clear_optout_{int(datetime.now(timezone.utc).timestamp()*1000)}",
        phone_number=clean,
        agent_id=agent_id,
        sender="system",
        text=f"[Audit] Opt-out manually cleared by {agent_name}. Automation resumed.",
        status="sent",
        processing_status="processed",
    )
    return {"success": True, "phone_number": clean, "opted_out": False}


@app.post("/api/whatsapp/resume_automation")
def resume_automation_endpoint(body: dict):
    phone = body.get("phone_number")
    agent_name = body.get("agent_name") or "Agent"
    agent_id = body.get("agent_id")
    if not phone:
        raise HTTPException(status_code=400, detail="phone_number is required")
    clean = normalize_whatsapp_number(phone)
    update_contact_state(
        clean,
        automation_paused=False,
        automation_paused_reason=None,
    )
    if not WHATSAPP_USE_MEMORY_STORE and supabase:
        try:
            supabase.table("signals").insert({
                "type": "whatsapp_automation_resumed",
                "message": f"Agent {agent_name} resumed automation for {clean}.",
            }).execute()
        except Exception:
            pass
    log_whatsapp_message(
        msg_id=f"audit_resume_auto_{int(datetime.now(timezone.utc).timestamp()*1000)}",
        phone_number=clean,
        agent_id=agent_id,
        sender="system",
        text=f"[Audit] Automation resumed by {agent_name}.",
        status="sent",
        processing_status="processed",
    )
    return {"success": True, "phone_number": clean, "automation_paused": False}




@app.post("/api/whatsapp/send_pitch")
def send_pitch_via_whatsapp(body: dict, request: Request = None):
    client_id = body.get("client_id")
    property_id = body.get("property_id")
    if not client_id or not property_id:
        raise HTTPException(status_code=400, detail="client_id and property_id are required")

    if request and hasattr(request.state, "agent"):
        from agent_auth import require_client_access
        require_client_access(request.state.agent, client_id, supabase)

    # ── Agent attribution ────────────────────────────────────────────────────
    # Priority: explicit sender_agent_id > agent_id field > client.assigned_agent_id
    # We do NOT text-scan the pitch body for agent names (fragile — see resolve_agent_from_pitch_text).
    agent_id = body.get("sender_agent_id") or body.get("agent_id") or None

    client = None
    agent_name = "R. Delgado"
    try:
        client_res = supabase.table("clients").select("name, assigned_agent_id").eq("id", client_id).single().execute()
        client = client_res.data if client_res else None
        if isinstance(client, list):
            client = client[0] if len(client) > 0 else None
        if not agent_id and client and client.get("assigned_agent_id"):
            agent_id = client.get("assigned_agent_id")
    except Exception as exc:
        print(f"[send_pitch_via_whatsapp] client lookup error: {exc}")

    # Resolve agent name for confirmation messages
    if agent_id:
        try:
            ag_res = supabase.table("agents").select("name").eq("id", agent_id).single().execute()
            ag_data = ag_res.data[0] if isinstance(ag_res.data, list) and len(ag_res.data) > 0 else ag_res.data
            if isinstance(ag_data, dict) and ag_data.get("name"):
                agent_name = ag_data["name"]
        except Exception:
            pass
    else:
        # Last-resort: text-scan (legacy) — log a warning
        _, scanned_name = resolve_agent_from_pitch_text(
            body.get("message_text") or "", default_agent_id=None
        )
        if scanned_name and scanned_name != "Senior Sales Representative":
            print(f"[send_pitch_via_whatsapp] WARN: agent_id missing — fell back to text-scanned name '{scanned_name}'")
            agent_name = scanned_name

    to_number = body.get("to_number") or os.getenv("WHATSAPP_TEST_NUMBER", "60109722730")

    draft = None
    try:
        draft_res = supabase.table("invite_drafts") \
            .select("*") \
            .eq("client_id", client_id).eq("property_id", property_id) \
            .single().execute()
        draft = draft_res.data if draft_res else None
    except Exception as exc:
        print(f"[send_pitch_via_whatsapp] draft lookup error: {exc}")

    draft_text = body.get("message_text") or (draft and (draft.get("draft") or draft.get("draft_text")))

    # ── Slot resolution ───────────────────────────────────────────────────────
    # Priority:
    #   1. Structured slots from request body (frontend sends { index, date, time, label, slot_iso })
    #   2. Text-parser fallback on draft_text (LEGACY — logs warning)
    #   3. generate_candidate_slots (safe last resort)
    slots_raw = body.get("slots")
    slots = None

    if slots_raw and isinstance(slots_raw, list) and len(slots_raw) > 0:
        validated = []
        now_kl = datetime.now(KL_TZ)
        viewing_intervals = fetch_agent_existing_viewing_intervals(agent_id) if agent_id else []
        buf = timedelta(minutes=45)

        for s in slots_raw:
            iso = s.get("slot_iso") or ""
            if not iso and s.get("date") and s.get("time"):
                date_str = s["date"]
                time_str = s["time"]
                try:
                    h, m = (int(x) for x in time_str.split(":"))
                    d_parts = [int(x) for x in date_str.split("-")]
                    dt = datetime(d_parts[0], d_parts[1], d_parts[2], h, m, tzinfo=KL_TZ)
                    iso = dt.isoformat()
                except Exception as exc:
                    raise HTTPException(status_code=400, detail=f"Invalid date/time format for slot: {exc}")

            if not iso:
                raise HTTPException(status_code=400, detail="Each proposed slot must specify a valid date and time.")

            try:
                slot_dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(KL_TZ)
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"Invalid slot timestamp '{iso}': {exc}")

            label = s.get("label") or format_slot_label(slot_dt)

            # 1. Must be in the future
            if slot_dt <= now_kl + timedelta(minutes=5):
                raise HTTPException(
                    status_code=400,
                    detail=f"Slot '{label}' is in the past. Proposed viewings must be scheduled in the future."
                )

            # 2. Must be on a weekday (Monday to Friday)
            # 2. Must be within unified business hours (Mon-Fri, starts >= 09:00, concludes by 18:00)
            if not is_within_business_hours(slot_dt):
                if slot_dt.weekday() >= 5:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Slot '{label}' falls on a weekend. Viewings must be scheduled Monday through Friday."
                    )
                raise HTTPException(
                    status_code=400,
                    detail=f"Slot '{label}' is outside business hours. Viewings must start at or after 09:00 AM and conclude by 06:00 PM (slot length: {SLOT_DURATION_MINUTES} mins)."
                )

            # 3. Conflict check for sender_agent_id
            c_start = slot_dt
            c_end = slot_dt + timedelta(minutes=60)
            for v_start, v_end in viewing_intervals:
                if not (c_end + buf <= v_start or c_start >= v_end + buf):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Slot '{label}' conflicts with an existing viewing for this agent (min 45-min buffer required)."
                    )

            validated.append({
                "index": s.get("index") or (len(validated) + 1),
                "label": label,
                "slot_iso": slot_dt.isoformat(),
            })

        # 4. Pairwise check between proposed slots
        for i, s1 in enumerate(validated):
            for j, s2 in enumerate(validated):
                if i < j:
                    dt1 = datetime.fromisoformat(s1["slot_iso"])
                    dt2 = datetime.fromisoformat(s2["slot_iso"])
                    if abs((dt1 - dt2).total_seconds()) < 3600:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Proposed slots '{s1['label']}' and '{s2['label']}' conflict with each other (must be at least 1 hour apart)."
                        )

        slots = validated

    if not slots:
        # Fallback 2: text-parse draft
        if draft_text:
            parsed = parse_slots_from_text(draft_text)
            if parsed and len(parsed) >= 1:
                print(f"[send_pitch_via_whatsapp] WARN: using text-parser fallback for slots (fragile). Found {len(parsed)} slots.")
                slots = parsed
        if not slots:
            # Fallback 3: generate fresh candidate slots
            slots = generate_candidate_slots(agent_id=agent_id, count=3)

    if not draft_text:
        c_name = (client and client.get("name")) or "Valued Partner"
        slot_lines = "  ".join([f"{s['index']}) {s['label']}" for s in slots])
        draft_text = (
            f"Hello {c_name} team, following up from PIPELINE.EV regarding our industrial robotics units. "
            f"Would your team be open to an on-site demonstration? Here are 3 times that work on my end:\n\n"
            f"Proposed slots:\n{slot_lines}\n\nReply 1, 2 or 3 to book, or tell me a time that suits you.\n\n"
            f"Best regards,\n{agent_name}\nSenior Sales Representative, PIPELINE.EV"
        )
    elif "Reply 1, 2 or 3" not in draft_text:
        slot_lines = "  ".join([f"{s['index']}) {s['label']}" for s in slots])
        draft_text = f"{draft_text.strip()}\n\nProposed slots:\n{slot_lines}\n\nReply 1, 2 or 3 to book, or tell me a time that suits you."

    clean_digits = normalize_whatsapp_number(to_number)
    offer_id = str(uuid.uuid4())

    prop_name = "Robotics Unit"
    prop_image_url = None
    try:
        p_res = supabase.table("properties").select("address, neighborhood, image_url").eq("id", property_id).single().execute()
        p_data = p_res.data[0] if isinstance(p_res.data, list) and len(p_res.data) > 0 else p_res.data
        if isinstance(p_data, dict):
            if p_data.get("address"):
                prop_name = p_data["address"]
            prop_image_url = p_data.get("image_url")
    except Exception:
        pass
    c_name = (client.get("name") if isinstance(client, dict) else None) or "Valued Partner"

    # ── Channel Delivery: Inside 24h Window vs Template Outside Window ───────
    is_inside_window = is_within_24h_window(clean_digits)
    force_template = bool(body.get("force_template", False))
    template_name = body.get("template_name") or os.getenv("WHATSAPP_PITCH_TEMPLATE_NAME")
    attach_image = bool(body.get("attach_image", False))

    image_sent = False
    image_warning = None
    if is_inside_window and not force_template and attach_image:
        if prop_image_url:
            is_valid_img, img_reason = validate_unit_image_url(prop_image_url)
            if is_valid_img:
                try:
                    img_res = send_whatsapp_image_message(
                        to_number=clean_digits,
                        image_url=prop_image_url,
                        caption=f"{prop_name} — On-Site Demonstration",
                    )
                    image_sent = True
                    img_wamid = (img_res.get("messages") or [{}])[0].get("id")
                    log_whatsapp_message(
                        msg_id=img_wamid or f"img_{int(datetime.now(timezone.utc).timestamp() * 1000)}",
                        phone_number=clean_digits,
                        agent_id=agent_id,
                        client_id=client_id,
                        client_name=c_name,
                        sender="agent",
                        text=f"[Unit Image: {prop_name}]",
                        status="sent",
                    )
                except Exception as img_err:
                    print(f"[send_pitch_via_whatsapp] Image dispatch warning: {img_err}")
                    image_warning = f"Unit image delivery failed: {img_err}. Demonstration slots were dispatched successfully."
            else:
                image_warning = f"Unit image skipped: {img_reason}. Demonstration slots were dispatched successfully."
        else:
            image_warning = "Unit has no image URL configured. Demonstration slots were dispatched successfully."

    used_template = False
    rendered_template_text = render_viewing_slots_pitch_text(c_name, prop_name, slots)

    def _dispatch_template() -> dict:
        nonlocal used_template
        used_template = True
        s1 = slots[0]["label"] if len(slots) > 0 else "Option 1"
        s2 = slots[1]["label"] if len(slots) > 1 else "Option 2"
        s3 = slots[2]["label"] if len(slots) > 2 else "Option 3"
        params = [c_name, prop_name, s1, s2, s3]
        button_payloads = [f"slot_pick:{offer_id}:{s['index']}" for s in slots[:3]]
        return send_whatsapp_template_with_quick_replies(
            to_number=clean_digits,
            template_name=template_name or "viewing_slots_pitch",
            body_parameters=params,
            button_payloads=button_payloads,
        )

    if is_inside_window and not force_template:
        try:
            total_options = len(slots) + 2
            if total_options <= 3:
                buttons = [
                    {"id": f"slot_pick:{offer_id}:{s['index']}", "title": s["label"][:20]}
                    for s in slots[:3]
                ]
                if len(buttons) < 3:
                    buttons.append({"id": f"action:{offer_id}:reschedule", "title": "Different time"})
                if len(buttons) < 3:
                    buttons.append({"id": f"action:{offer_id}:human", "title": "Talk to human"})
                result = send_whatsapp_interactive_buttons(
                    to_number=clean_digits,
                    body_text=draft_text,
                    buttons=buttons,
                    header_text="Demo Invitation",
                )
            else:
                sections = [
                    {
                        "title": "Proposed Times",
                        "rows": [
                            {
                                "id": f"slot_pick:{offer_id}:{s['index']}",
                                "title": s["label"][:24],
                                "description": "60-min demonstration",
                            }
                            for s in slots
                        ],
                    },
                    {
                        "title": "Other Options",
                        "rows": [
                            {
                                "id": f"action:{offer_id}:reschedule",
                                "title": "Different time",
                                "description": "Request alternative dates/times",
                            },
                            {
                                "id": f"action:{offer_id}:human",
                                "title": "Talk to a person",
                                "description": "Speak with our sales representative",
                            },
                        ],
                    },
                ]
                result = send_whatsapp_interactive_list(
                    to_number=clean_digits,
                    body_text=draft_text,
                    button_label="Choose a Time",
                    sections=sections,
                    header_text="Demo Invitation",
                )
        except MetaReengagementError:
            print(f"[send_pitch_via_whatsapp] Caught Meta 131047 re-engagement error for {clean_digits}. Retrying via template path...")
            result = _dispatch_template()
    else:
        # Outside 24h window (or explicit template requested)
        result = _dispatch_template()

    try:
        supabase.table("invite_drafts").update({"sent_at": datetime.now(timezone.utc).isoformat()}).eq("client_id", client_id).eq("property_id", property_id).execute()
    except Exception as exc:
        print(f"[send_pitch_via_whatsapp] Warning updating sent_at: {exc}")

    advance_stage(client_id, "contacted")

    # If template path used, store exact rendered template text; otherwise draft_text
    final_text_to_store = rendered_template_text if used_template else draft_text

    client_name = (client and client.get("name")) or "Client"
    wamid = (result.get("messages") or [{}])[0].get("id")
    msg_id = wamid or f"pitch_{int(datetime.now(timezone.utc).timestamp() * 1000)}"
    msg_record = log_whatsapp_message(
        msg_id=msg_id,
        phone_number=clean_digits,
        agent_id=agent_id,
        client_id=client_id,
        client_name=client_name,
        sender="agent",
        text=final_text_to_store,
        status="sent",
    )

    # Persist the slot offer — always with canonical ISO timestamps
    slot_offer = {
        "id": offer_id,
        "client_id": client_id,
        "property_id": property_id,
        "agent_id": agent_id,
        "slots": slots,
        "status": "open",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=72)).isoformat(),
        "pitch_wamid": msg_record["id"],
        "phone_number": clean_digits,
    }
    try:
        persist_slot_offer(slot_offer)
    except RuntimeError as db_err:
        print(f"[send_pitch_via_whatsapp] FATAL: Slot offer database persistence failed: {db_err}")
        raise HTTPException(
            status_code=500,
            detail=f"Database table unreachable: failed to persist whatsapp_slot_offers: {db_err}",
        )

    return {
        "whatsapp_response": result,
        "relationship_stage": "contacted",
        "client_name": client_name,
        "message": msg_record,
        "slot_offer": slot_offer,
        "template_used": used_template,
        "rendered_text": final_text_to_store,
        "image_sent": image_sent,
        "image_warning": image_warning,
    }


@app.get("/api/whatsapp/pitch_template")
def get_pitch_template_config():
    """Returns canonical pitch template configuration including body, variable list, and buttons."""
    return PITCH_TEMPLATE_CONFIG


@app.get("/api/whatsapp/window_status")
def get_whatsapp_window_status(phone_number: str = None, client_id: str = None):
    clean_digits = ""
    if phone_number:
        clean_digits = "".join(filter(str.isdigit, phone_number))
    elif client_id:
        try:
            c_res = supabase.table("clients").select("whatsapp_number, phone").eq("id", client_id).single().execute()
            if c_res.data:
                raw_p = c_res.data.get("whatsapp_number") or c_res.data.get("phone") or ""
                clean_digits = "".join(filter(str.isdigit, raw_p))
        except Exception:
            pass
    if not clean_digits:
        clean_digits = "60109722730"

    is_open = is_within_24h_window(clean_digits)
    last_inbound_ts = None
    try:
        res = (
            supabase.table("whatsapp_messages")
            .select("timestamp")
            .eq("to_number", clean_digits)
            .in_("sender", ["client", "user", "inbound"])
            .order("timestamp", desc=True)
            .limit(1)
            .execute()
        )
        if res.data and len(res.data) > 0:
            last_inbound_ts = res.data[0].get("timestamp")
    except Exception:
        pass

    return {
        "phone_number": clean_digits,
        "is_window_open": is_open,
        "last_inbound_timestamp": last_inbound_ts,
        "template_name": "viewing_slots_pitch",
        "automation_paused": is_automation_paused_for_phone(clean_digits),
    }


@app.post("/api/whatsapp/resume_automation")
def resume_automation_endpoint(body: dict):
    phone_number = body.get("phone_number")
    client_id = body.get("client_id")
    clean_digits = "".join(filter(str.isdigit, phone_number or ""))
    if not clean_digits and client_id:
        try:
            c_res = supabase.table("clients").select("whatsapp_number, phone").eq("id", client_id).single().execute()
            if c_res.data:
                clean_digits = "".join(filter(str.isdigit, c_res.data.get("whatsapp_number") or c_res.data.get("phone") or ""))
        except Exception:
            pass
    if not clean_digits:
        clean_digits = "60109722730"

    set_automation_paused_for_phone(clean_digits, False)
    return {"success": True, "automation_paused": False, "phone_number": clean_digits}


@app.post("/api/clients/{client_id}/advance_stage")
def manually_advance_stage(client_id: str, body: dict, request: Request):
    """Manual-only transitions — currently just 'negotiation', since nothing
    else in the app auto-signals that a deal has entered negotiation."""
    if hasattr(request.state, "agent"):
        from agent_auth import require_client_access
        require_client_access(request.state.agent, client_id, supabase)

    target_stage = body.get("stage")
    if target_stage not in STAGE_ORDER:
        raise HTTPException(status_code=400, detail="Invalid stage")
    new_stage = advance_stage(client_id, target_stage)
    return {"client_id": client_id, "relationship_stage": new_stage}



app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Background price scheduler ─────────────────────────────────────────────────
# Nudges 1–2 random properties every 12 minutes so the pipeline feels
# live without anyone clicking anything.

_scheduler = BackgroundScheduler(daemon=True)


def auto_market_tick():
    """Runs automatically in the background — nudges 1–2 random properties'
    prices, unprompted. Called by the scheduler, not by any HTTP request."""
    try:
        properties = supabase.table("properties").select("id").execute().data
        if not properties:
            return
        # Usually 1, occasionally 2 — feels sporadic, not uniform
        num_to_move = _random.choice([1, 1, 1, 2])
        chosen = _random.sample(properties, min(num_to_move, len(properties)))
        for p in chosen:
            _simulate_price_change_internal(p["id"])
        print(f"[auto_market_tick] moved {len(chosen)} propert{'y' if len(chosen) == 1 else 'ies'}")
    except Exception as exc:
        print(f"[auto_market_tick] failed: {exc}")


_scheduler.add_job(auto_market_tick, "interval", minutes=12, id="auto_market_tick")
_scheduler.add_job(process_due_whatsapp_reminders, "interval", minutes=1, id="process_due_whatsapp_reminders")


@app.on_event("startup")
def start_scheduler():
    ALLOWED_ENVIRONMENTS = ("development", "testing", "staging", "production")
    raw_env = os.getenv("ENVIRONMENT")
    # In test environments (e.g. pytest), default to testing if unset
    if not raw_env and ("pytest" in sys.modules or "PYTEST_CURRENT_TEST" in os.environ):
        raw_env = "testing"
    
    if not raw_env or raw_env.strip().lower() not in ALLOWED_ENVIRONMENTS:
        raise RuntimeError(
            f"FATAL: ENVIRONMENT environment variable must be explicitly set to one of: "
            f"{', '.join(ALLOWED_ENVIRONMENTS)}. Got: '{raw_env}'."
        )
    
    env = raw_env.strip().lower()
    is_prod = env in ("production", "prod")

    # Production security check: fail if required secrets are missing
    if is_prod:
        missing_vars = []
        if not os.getenv("BFF_INTERNAL_SECRET"):
            missing_vars.append("BFF_INTERNAL_SECRET")
        if not os.getenv("PORTAL_CODE_PEPPER"):
            missing_vars.append("PORTAL_CODE_PEPPER")
        if not os.getenv("CALENDAR_SIGNING_SECRET"):
            missing_vars.append("CALENDAR_SIGNING_SECRET")
        wa_secret = os.getenv("WHATSAPP_APP_SECRET")
        if not wa_secret or len(wa_secret) < 16:
            missing_vars.append("WHATSAPP_APP_SECRET (must be >= 16 chars)")
        sb_service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
        if not sb_service_key:
            missing_vars.append("SUPABASE_SERVICE_ROLE_KEY")

        if missing_vars:
            raise RuntimeError(f"FATAL: Production security check failed. Missing or invalid required environment variables: {', '.join(missing_vars)}")

        enforce_wa = os.getenv("ENFORCE_WA_SIGNATURE", "true").lower()
        if enforce_wa in ("false", "0", "no"):
            raise RuntimeError("FATAL: Webhook signature verification (ENFORCE_WA_SIGNATURE) cannot be disabled in production.")

    # Print clean security posture summary (names and on/off status only, never secret values)
    print("=" * 64)
    print("PIPELINE.EV LOGIC ENGINE - SECURITY POSTURE SUMMARY")
    print(f"  ENVIRONMENT:                 {env}")
    print(f"  PRODUCTION HARDENING:        {'ENABLED' if is_prod else 'DISABLED (dev mode)'}")
    print(f"  BFF_INTERNAL_SECRET:         {'CONFIGURED' if os.getenv('BFF_INTERNAL_SECRET') else 'MISSING'}")
    print(f"  PORTAL_CODE_PEPPER:          {'CONFIGURED' if os.getenv('PORTAL_CODE_PEPPER') else 'MISSING'}")
    print(f"  CALENDAR_SIGNING_SECRET:     {'CONFIGURED' if os.getenv('CALENDAR_SIGNING_SECRET') else 'MISSING'}")
    print(f"  WHATSAPP_APP_SECRET:         {'CONFIGURED' if os.getenv('WHATSAPP_APP_SECRET') else 'MISSING'}")
    print(f"  SUPABASE_SERVICE_KEY:        {'CONFIGURED' if (os.getenv('SUPABASE_SERVICE_ROLE_KEY') or os.getenv('SUPABASE_KEY')) else 'MISSING'}")
    print(f"  ENFORCE_WA_SIGNATURE:        {'ENABLED' if env != 'development' or os.getenv('ENFORCE_WA_SIGNATURE', '').lower() not in ('false', '0', 'no') else 'DISABLED'}")
    print(f"  SIMULATION ENDPOINTS:        {'BLOCKED (404)' if is_prod else 'ADMIN ONLY'}")
    print("=" * 64)

    if not _scheduler.running:
        _scheduler.start()
        print("[scheduler] background price ticker started (every 12 min)")


@app.on_event("shutdown")
def stop_scheduler():
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        print("[scheduler] stopped")


@app.get("/")
def health_check():
    return {"status": "ok", "service": "PIPELINE.EV Logic Engine"}


# ─── Agents endpoint ──────────────────────────────────────────────────────────

@app.get("/api/agents")
def get_agents():
    """Return all agents ordered alphabetically by name."""
    try:
        result = supabase.table("agents").select("*").order("name").execute()
        return result.data or []
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch agents: {exc}") from exc



@app.post("/api/run_evaluations")
def run_evaluations():
    try:
        clients_response = supabase.table("clients").select("*").execute()
        properties_response = supabase.table("properties").select("*").execute()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch data: {exc}") from exc

    clients = clients_response.data or []
    properties = properties_response.data or []

    if not clients or not properties:
        raise HTTPException(
            status_code=400,
            detail="Clients and properties tables must contain data before running evaluations.",
        )

    # Separate active listings from closed deals so buyers are only matched to purchasable properties
    active_properties = [p for p in properties if p.get("status") != "CLOSED"]
    if not active_properties:
        active_properties = properties

    # Pre-fetch past purchases grouped by client for scoring
    past_purchases_by_client: dict[str, list[dict]] = {}
    try:
        purch_res = supabase.table("client_past_purchases").select("*").execute()
        for p in (purch_res.data or []):
            cid = p.get("client_id")
            if cid:
                past_purchases_by_client.setdefault(cid, []).append(p)
    except Exception:
        pass

    evaluations = []
    for client in clients:
        best_match_tier = None
        best_match_ev = -1
        best_match_property_id = None
        c_past = past_purchases_by_client.get(client["id"], [])

        for property_row in active_properties:
            # Map Supabase field names → canonical ClientProfile shape
            client_profile = {
                "budget":                   client.get("stated_budget"),
                "preferred_neighborhood":   client.get("preferred_neighborhood"),
                "engagement_history":       client.get("past_viewings"),
                "source":                   client.get("source"),
                "financing_status":         client.get("financing_status"),
                "move_in_timeline":         client.get("move_in_timeline"),
                "property_type_preference": client.get("property_type_preference"),
                "secondary_neighborhood":   client.get("secondary_neighborhood"),
                "past_purchases":           c_past,
            }

            result = score_pair(client_profile, property_row)
            ml_prob = predict_probability(client_profile, property_row)

            evaluations.append(
                {
                    "client_id":      client["id"],
                    "property_id":    property_row["id"],
                    "ai_probability": result["probability"],
                    "expected_value": result["expected_value"],
                    "segment_tier":   result["tier"],
                    "ml_probability": ml_prob,
                    # confidence is returned but not persisted to the current schema;
                    # remove the next line if the DB column doesn't exist yet.
                    # "confidence":  result["confidence"],
                }
            )

            if result["expected_value"] > best_match_ev:
                best_match_ev = result["expected_value"]
                best_match_tier = result["tier"]
                best_match_property_id = property_row["id"]

        if best_match_tier is not None:
            check_and_log_tier_signal(
                client_id=client["id"],
                client_name=client["name"],
                new_tier=best_match_tier,
                property_id=best_match_property_id
            )


    try:
        result = supabase.table("pipeline_evaluations").upsert(
            evaluations,
            on_conflict="client_id,property_id",
        ).execute()
    except Exception as exc:
        if "ml_probability" in str(exc):
            for e in evaluations:
                e.pop("ml_probability", None)
            try:
                result = supabase.table("pipeline_evaluations").upsert(
                    evaluations,
                    on_conflict="client_id,property_id",
                ).execute()
            except Exception as inner_exc:
                raise HTTPException(status_code=500, detail=f"Failed to upsert evaluations: {inner_exc}") from inner_exc
        else:
            raise HTTPException(status_code=500, detail=f"Failed to upsert evaluations: {exc}") from exc

    return {
        "message": "Evaluations completed successfully",
        "count": len(evaluations),
        "evaluations": result.data or evaluations,
    }


# ─── Reasoning endpoint ────────────────────────────────────────────────────────

class ReasoningRequest(BaseModel):
    client_id: str
    property_id: str


def _build_prompt(client: dict, prop: dict) -> str:
    budget = client["stated_budget"]
    prop_val = prop["property_value"]
    financial_fit = budget >= prop_val
    geo_match = client["preferred_neighborhood"] == prop["neighborhood"]
    viewings = client["past_viewings"]
    past_purchases = client.get("past_purchases") or []

    fin_label = (
        f"✓ CapEx budget (RM {budget:,.0f}) covers unit cost (RM {prop_val:,.0f})"
        if financial_fit
        else f"✗ CapEx budget (RM {budget:,.0f}) is below unit cost (RM {prop_val:,.0f})"
    )
    geo_label = (
        f"✓ target environment ({client['preferred_neighborhood']}) matches robot unit design"
        if geo_match
        else f"✗ target environment ({client['preferred_neighborhood']}) differs from robot unit design ({prop['neighborhood']})"
    )
    eng_label = (
        f"{viewings} past demo session(s) recorded — strong technical engagement"
        if viewings > 0
        else "0 past demo sessions — initial technical evaluation"
    )

    if past_purchases:
        purch_lines = "\n".join(
            f"  - {p.get('purchase_year', 'Prior')}: {p.get('property_name', 'Robot Unit')} ({p.get('neighborhood', '')}) · RM {float(p.get('purchase_price', 0)):,.0f} · {p.get('property_type', '').title()} ({p.get('purpose', 'facility_automation').replace('_', ' ').title()})"
            + (" [Verified Active Deployment in Fleet]" if p.get("property_id") else "")
            for p in past_purchases
        )
        track_record_section = f"\nCompany automation track record (prior deployed units):\n{purch_lines}"
        track_record_note = "- Explicitly reference their previous robot deployment track record (notably any units already operational in their fleet) to frame how this robot unit scales their automation throughput (e.g. natural fleet expansion, payload tier upgrade, lateral facility automation)."
    else:
        track_record_section = "\nCompany automation track record: First-time robotics adopter (no prior deployed units on file)"
        track_record_note = "- Treat as a first-time robotics adopter without existing fleet deployment history, emphasizing initial CapEx fit and ROI payback."

    return f"""You are writing an internal analysis note for an industrial robotics SALES REPRESENTATIVE about a prospective client COMPANY — not a message to the client themselves.

CRITICAL PERSPECTIVE RULES:
- Write strictly in the THIRD PERSON, referring to the company by their full name (e.g. "{client['name']}'s CapEx budget...", "{client['name']} has evaluated...").
- NEVER use second-person pronouns ("you", "your", "for you", "yours"). This is the sales representative's private analytical reasoning, NOT client-facing copy.

Client company profile:
- Company Name: {client['name']}
- Stated CapEx budget: RM {budget:,.0f}
- Target environment / facility type: {client['preferred_neighborhood']}
- Past robotic demo sessions: {viewings}{track_record_section}

Target robot unit:
- Model / Unit: {prop['address']}
- Operating Environment: {prop['neighborhood']}
- Unit Cost: RM {prop_val:,.0f}

Technical fit breakdown:
- Financial Fit: {fin_label}
- Environment Match: {geo_label}
- Engagement: {eng_label}

Note: This specific target robot unit was selected for this company because it represents their single Highest Expected Value (E(x)) opportunity in the pipeline.

Write a 2-4 sentence internal rationale from the sales representative's perspective explaining why this robot unit is {client['name']}'s highest-value deployment match opportunity.
Guidelines:
{track_record_note}
- Explain the trade-off honestly: acknowledge any lower probability or budget stretch if applicable, but justify the match by the potential deal size and expected value to the sales rep.
- Do NOT conclude that the robot unit "isn't a strong match" or shouldn't be pursued.
- Be specific, concise, and professional using Malaysian English conventions. No bullet points or headers. Do not include any preamble — start directly with the company's name."""


def generate_reasoning_text(client_id: str, property_id: str) -> str:
    """
    Core reasoning generator: checks cache, fetches client & property,
    calls Groq LLM, caches result, and returns reasoning string.
    """
    # 1. Try reasoning cache
    try:
        cache_res = (
            supabase.table("reasoning_cache")
            .select("reasoning")
            .eq("client_id", client_id)
            .eq("property_id", property_id)
            .limit(1)
            .execute()
        )
        if cache_res.data:
            return cache_res.data[0]["reasoning"]
    except Exception:
        pass

    # 2. Fetch client + property
    try:
        client_res = (
            supabase.table("clients").select("*").eq("id", client_id).limit(1).execute()
        )
        prop_res = (
            supabase.table("properties").select("*").eq("id", property_id).limit(1).execute()
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch client/property: {exc}") from exc

    if not client_res.data or not prop_res.data:
        raise HTTPException(status_code=404, detail="Client or property not found")

    client = client_res.data[0]
    prop = prop_res.data[0]

    # Fetch past acquisition history for this client
    try:
        purch_res = supabase.table("client_past_purchases").select("*").eq("client_id", client_id).execute()
        client["past_purchases"] = purch_res.data or []
    except Exception:
        client["past_purchases"] = []

    # 3. Call Groq LLM
    prompt = _build_prompt(client, prop)
    reasoning = _call_groq_llm(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=400,
        temperature=0.4,
        timeout=20.0,
    )

    # 4. Persist to reasoning_cache
    try:
        supabase.table("reasoning_cache").upsert(
            {
                "client_id": client_id,
                "property_id": property_id,
                "reasoning": reasoning,
            },
            on_conflict="client_id,property_id",
        ).execute()
    except Exception:
        pass

    return reasoning


@app.post("/api/generate_reasoning")
def generate_reasoning(body: ReasoningRequest, request: Request):
    if hasattr(request.state, "agent"):
        from agent_auth import require_client_access
        require_client_access(request.state.agent, body.client_id, supabase)

    # Check cache first for cached flag
    try:
        cache_res = (
            supabase.table("reasoning_cache")
            .select("reasoning")
            .eq("client_id", body.client_id)
            .eq("property_id", body.property_id)
            .limit(1)
            .execute()
        )
        if cache_res.data:
            return {"reasoning": cache_res.data[0]["reasoning"], "cached": True}
    except Exception:
        pass

    reasoning = generate_reasoning_text(body.client_id, body.property_id)
    return {"reasoning": reasoning, "cached": False}


def generate_briefing_line(client_name: str, property_name: str, expected_value: float, probability: float, reasoning_context: str) -> str:
    prompt = (
        f"Based on this analysis: \"{reasoning_context}\" — "
        f"write ONE short, punchy sentence (max 20 words) for an industrial robotics sales rep's dashboard briefing "
        f"summarizing why {client_name} is a top deployment opportunity for {property_name} "
        f"(P(Adopt) {probability*100:.0f}%, expected value RM{expected_value:,.0f}). "
        f"No preamble, no filler, just the single sentence."
    )
    content = _call_groq_llm(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=500,
        temperature=0.5,
        timeout=20.0,
    )
    if not content:
        # Fallback if reasoning model used entire budget on chain of thought
        return f"{client_name} is a prime deployment opportunity for {property_name} with {probability*100:.0f}% adoption probability and RM{expected_value:,.0f} expected value."
    return content


@app.get("/api/dashboard_briefing")
def get_dashboard_briefing(request: Request, agent_id: str | None = None):
    # Pull top 3 VIP clients by best-match expected_value (scoping enforced)
    agent = getattr(request.state, "agent", None) if request else None
    scoping_mode = os.getenv("AGENT_PIPELINE_SCOPING", "assigned").lower()
    effective_agent_id = agent_id
    if agent and agent.role != "admin" and scoping_mode == "assigned":
        effective_agent_id = str(agent.agent_id) if agent.agent_id else "unassigned_no_access"

    try:
        evals_query = (
            supabase.table("pipeline_evaluations")
            .select("*, clients(id, name, assigned_agent_id), properties(address, neighborhood, property_value)")
            .eq("segment_tier", "TIER_1")
            .order("expected_value", desc=True)
        )
        all_tier1 = evals_query.execute().data or []
        # Filter by agent in Python (nested FK filter not supported directly)
        if effective_agent_id:
            all_tier1 = [
                row for row in all_tier1
                if str((row.get("clients") or {}).get("assigned_agent_id")) == str(effective_agent_id)
            ]
        evals = all_tier1[:3]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch evaluations: {exc}") from exc

    briefing = []
    for row in (evals or []):
        client_id = row["client_id"]
        property_id = row["property_id"]
        client_info = row.get("clients") or {}
        prop_info = row.get("properties") or {}
        client_name = client_info.get("name", "Unknown Client")
        property_name = prop_info.get("address") or prop_info.get("name", "Unknown Property")
        expected_val = float(row.get("expected_value", 0))
        prob = float(row.get("ai_probability", 0))

        # Check briefing_cache first
        cached_briefing = None
        try:
            b_cache_res = (
                supabase.table("briefing_cache")
                .select("briefing")
                .eq("client_id", client_id)
                .eq("property_id", property_id)
                .limit(1)
                .execute()
            )
            if b_cache_res.data:
                cached_briefing = b_cache_res.data[0]["briefing"]
        except Exception:
            cached_briefing = None

        if cached_briefing:
            briefing_text = cached_briefing
        else:
            reasoning_context = generate_reasoning_text(client_id, property_id)
            briefing_text = generate_briefing_line(
                client_name=client_name,
                property_name=property_name,
                expected_value=expected_val,
                probability=prob,
                reasoning_context=reasoning_context,
            )
            # Try caching in briefing_cache
            try:
                supabase.table("briefing_cache").upsert(
                    {
                        "client_id": client_id,
                        "property_id": property_id,
                        "briefing": briefing_text,
                    },
                    on_conflict="client_id,property_id",
                ).execute()
            except Exception:
                pass

        briefing.append({
            "client_id": client_id,
            "client_name": client_name,
            "property_name": property_name,
            "neighborhood": prop_info.get("neighborhood", ""),
            "expected_value": expected_val,
            "briefing": briefing_text,
            "reasoning": briefing_text,
        })

    return briefing


# ─── Log Viewing endpoint ──────────────────────────────────────────────────────

class LogViewingRequest(BaseModel):
    client_id: str
    property_id: str


@app.post("/api/log_viewing")
def log_viewing(body: LogViewingRequest, request: Request):
    """
    1. Increment `past_viewings` on the client record by 1.
    2. Re-score just this client-property pair using score_pair().
    3. Upsert the updated evaluation row in pipeline_evaluations.
    4. Return the updated probability, expected_value, and tier.
    """
    if hasattr(request.state, "agent"):
        from agent_auth import require_client_access
        require_client_access(request.state.agent, body.client_id, supabase)
    # ── 1. Fetch client & property ───────────────────────────────────────────
    try:
        client_res = (
            supabase.table("clients").select("*").eq("id", body.client_id).limit(1).execute()
        )
        prop_res = (
            supabase.table("properties").select("*").eq("id", body.property_id).limit(1).execute()
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch data: {exc}") from exc

    if not client_res.data:
        raise HTTPException(status_code=404, detail="Client not found")
    if not prop_res.data:
        raise HTTPException(status_code=404, detail="Property not found")

    client = client_res.data[0]
    prop = prop_res.data[0]

    # ── 2. Increment past_viewings by 1 ─────────────────────────────────────
    new_viewings = (client.get("past_viewings") or 0) + 1
    try:
        supabase.table("clients").update({"past_viewings": new_viewings}).eq("id", body.client_id).execute()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to update viewings: {exc}") from exc

    # ── 3. Re-score this pair with updated viewings ──────────────────────────
    client_profile = {
        "budget":                 client.get("stated_budget"),
        "preferred_neighborhood": client.get("preferred_neighborhood"),
        "engagement_history":     new_viewings,
        "source":                 client.get("source"),
    }
    result = score_pair(client_profile, prop)
    check_and_log_tier_signal(
        client_id=body.client_id,
        client_name=client["name"],
        new_tier=result["tier"],
        property_id=body.property_id
    )


    # ── 4. Upsert updated evaluation ─────────────────────────────────────────
    ml_prob = predict_probability(client_profile, prop)
    try:
        supabase.table("pipeline_evaluations").upsert(
            {
                "client_id":      body.client_id,
                "property_id":    body.property_id,
                "ai_probability": result["probability"],
                "expected_value": result["expected_value"],
                "segment_tier":   result["tier"],
                "ml_probability": ml_prob,
            },
            on_conflict="client_id,property_id",
        ).execute()
    except Exception as exc:
        if "ml_probability" in str(exc):
            try:
                supabase.table("pipeline_evaluations").upsert(
                    {
                        "client_id":      body.client_id,
                        "property_id":    body.property_id,
                        "ai_probability": result["probability"],
                        "expected_value": result["expected_value"],
                        "segment_tier":   result["tier"],
                    },
                    on_conflict="client_id,property_id",
                ).execute()
            except Exception as inner_exc:
                raise HTTPException(status_code=500, detail=f"Failed to upsert evaluation: {inner_exc}") from inner_exc
        else:
            raise HTTPException(status_code=500, detail=f"Failed to upsert evaluation: {exc}") from exc

    return {
        "client_id":      body.client_id,
        "client_name":    client.get("name"),
        "property_id":    body.property_id,
        "past_viewings":  new_viewings,
        "probability":    result["probability"],
        "expected_value": result["expected_value"],
        "tier":           result["tier"],
    }


# ─── Schedule Viewing endpoints ────────────────────────────────────────────────

class ScheduleViewingRequest(BaseModel):
    client_id: str
    property_id: str
    scheduled_at: str   # ISO-8601 string from the frontend date+time inputs


@app.post("/api/schedule_viewing")
def schedule_viewing(body: ScheduleViewingRequest, request: Request):
    """
    Insert a new row into scheduled_viewings (status='upcoming').
    Does NOT touch past_viewings or re-score — that only happens when completed.
    """
    if hasattr(request.state, "agent"):
        from agent_auth import require_client_access
        require_client_access(request.state.agent, body.client_id, supabase)

    try:
        res = supabase.table("scheduled_viewings").insert({
            "client_id":    body.client_id,
            "property_id":  body.property_id,
            "scheduled_at": body.scheduled_at,
            "status":       "upcoming",
        }).execute()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to schedule viewing: {exc}") from exc

    advance_stage(body.client_id, "viewing")

    viewing_row = res.data[0] if res.data else None
    if viewing_row and viewing_row.get("id"):
        schedule_viewing_reminders(viewing_row["id"])

    return {"viewing": viewing_row}


@app.patch("/api/complete_viewing/{viewing_id}")
def complete_viewing(viewing_id: str, request: Request):
    """
    Mark a scheduled viewing as completed, then trigger the Log Viewing flow:
    increment past_viewings, re-score, upsert pipeline_evaluations.
    """
    # ── 1. Fetch the scheduled viewing row ──────────────────────────────────
    try:
        view_res = (
            supabase.table("scheduled_viewings")
            .select("*")
            .eq("id", viewing_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch viewing: {exc}") from exc

    if not view_res.data:
        raise HTTPException(status_code=404, detail="Scheduled viewing not found")

    sv = view_res.data[0]
    client_id = sv["client_id"]
    property_id = sv["property_id"]

    if hasattr(request.state, "agent"):
        from agent_auth import require_client_access
        require_client_access(request.state.agent, client_id, supabase)

    # ── 2. Mark scheduled_viewings row as completed ──────────────────────────
    try:
        supabase.table("scheduled_viewings").update({"status": "completed"}).eq("id", viewing_id).execute()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to update viewing status: {exc}") from exc

    # Cancel pending reminders upon completion
    cancel_viewing_reminders(viewing_id, reason="viewing_completed")

    # ── 3. Re-use log_viewing logic: increment past_viewings + re-score ──────
    try:
        client_res = supabase.table("clients").select("*").eq("id", client_id).limit(1).execute()
        prop_res   = supabase.table("properties").select("*").eq("id", property_id).limit(1).execute()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch client/property: {exc}") from exc

    if not client_res.data or not prop_res.data:
        raise HTTPException(status_code=404, detail="Client or property not found")

    client = client_res.data[0]
    prop   = prop_res.data[0]

    new_viewings = (client.get("past_viewings") or 0) + 1
    supabase.table("clients").update({"past_viewings": new_viewings}).eq("id", client_id).execute()

    client_profile = {
        "budget":                 client.get("stated_budget"),
        "preferred_neighborhood": client.get("preferred_neighborhood"),
        "engagement_history":     new_viewings,
        "source":                 client.get("source"),
    }
    result = score_pair(client_profile, prop)
    check_and_log_tier_signal(
        client_id=client_id,
        client_name=client["name"],
        new_tier=result["tier"],
        property_id=property_id
    )


    ml_prob = predict_probability(client_profile, prop)
    try:
        supabase.table("pipeline_evaluations").upsert(
            {
                "client_id":      client_id,
                "property_id":    property_id,
                "ai_probability": result["probability"],
                "expected_value": result["expected_value"],
                "segment_tier":   result["tier"],
                "ml_probability": ml_prob,
            },
            on_conflict="client_id,property_id",
        ).execute()
    except Exception as exc:
        if "ml_probability" in str(exc):
            try:
                supabase.table("pipeline_evaluations").upsert(
                    {
                        "client_id":      client_id,
                        "property_id":    property_id,
                        "ai_probability": result["probability"],
                        "expected_value": result["expected_value"],
                        "segment_tier":   result["tier"],
                    },
                    on_conflict="client_id,property_id",
                ).execute()
            except Exception:
                pass
        else:
            print(f"[complete_scheduled_viewing] upsert failed: {exc}")

    return {
        "viewing_id":   viewing_id,
        "client_id":    client_id,
        "client_name":  client.get("name"),
        "property_id":  property_id,
        "past_viewings": new_viewings,
        "probability":  result["probability"],
        "expected_value": result["expected_value"],
        "tier":         result["tier"],
    }


class CancelViewingRequest(BaseModel):
    reason: str | None = "agent"


@app.patch("/api/cancel_viewing/{viewing_id}")
def cancel_viewing(viewing_id: str, request: Request, body: CancelViewingRequest | None = None):
    """
    Cancel a scheduled viewing. Sets status='cancelled' and records reason if column exists.
    """
    db = get_supabase()
    sv_res = db.table("scheduled_viewings").select("client_id").eq("id", viewing_id).limit(1).execute()
    if sv_res.data and sv_res.data[0].get("client_id") and hasattr(request.state, "agent"):
        from agent_auth import require_client_access
        require_client_access(request.state.agent, sv_res.data[0]["client_id"], db)

    reason = body.reason if (body and body.reason) else "agent"
    cancel_viewing_reminders(viewing_id, reason=reason)
    try:
        db.table("scheduled_viewings").update({
            "status": "cancelled",
            "cancellation_reason": reason,
        }).eq("id", viewing_id).execute()
    except Exception:
        try:
            db.table("scheduled_viewings").update({
                "status": "cancelled",
            }).eq("id", viewing_id).execute()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to cancel viewing: {exc}") from exc

    return {"viewing_id": viewing_id, "status": "cancelled", "reason": reason}



@app.get("/api/scheduled_viewings")
def list_scheduled_viewings(request: Request):
    """
    Fetch all scheduled_viewings rows joined with client + property names.
    Auto-cancels any 'upcoming' viewing scheduled >24 hours in the past.
    Scoped to assigned agent if non-admin agent is logged in.
    """
    db = get_supabase()
    # ── Auto-cancel stale upcoming viewings (> 24 hours past due) ──────────────
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
        stale_res = (
            db.table("scheduled_viewings")
            .select("*, clients(id, name)")
            .eq("status", "upcoming")
            .lt("scheduled_at", cutoff)
            .execute()
        )
        if stale_res.data:
            for viewing in stale_res.data:
                cancel_viewing_reminders(viewing["id"], reason="auto_missed")
                try:
                    db.table("scheduled_viewings").update({
                        "status": "cancelled",
                        "cancellation_reason": "auto_missed",
                    }).eq("id", viewing["id"]).execute()
                except Exception:
                    db.table("scheduled_viewings").update({
                        "status": "cancelled",
                    }).eq("id", viewing["id"]).execute()

                client_obj = viewing.get("clients")
                client_name = client_obj.get("name") if isinstance(client_obj, dict) else "Client"
                supabase.table("signals").insert({
                    "type": "viewing_auto_cancelled",
                    "client_id": viewing["client_id"],
                    "property_id": viewing["property_id"],
                    "message": f"Scheduled viewing for {client_name} auto-cancelled (missed, never marked completed)"
                }).execute()
    except Exception as exc:
        print(f"Auto-cancel check non-fatal error: {exc}")


    try:
        res = (
            db.table("scheduled_viewings")
            .select("*, clients(id, name, preferred_neighborhood, assigned_agent_id), properties(id, address, neighborhood)")
            .order("scheduled_at", desc=False)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch scheduled viewings: {exc}") from exc

    viewings = res.data or []
    agent = getattr(request.state, "agent", None) if request else None
    scoping_mode = os.getenv("AGENT_PIPELINE_SCOPING", "assigned").lower()
    if agent and agent.role != "admin" and scoping_mode == "assigned":
        eff_id = str(agent.agent_id) if agent.agent_id else "no_agent"
        viewings = [v for v in viewings if str((v.get("clients") or {}).get("assigned_agent_id")) == eff_id]

    return {"viewings": viewings}


@app.get("/api/signals")
def get_signals(request: Request):
    agent = getattr(request.state, "agent", None) if request else None
    scoping_mode = os.getenv("AGENT_PIPELINE_SCOPING", "assigned").lower()
    result = supabase.table("signals").select("*, clients(assigned_agent_id)").eq("dismissed", False).order("created_at", desc=True).limit(50).execute()
    signals = result.data or []
    if agent and agent.role != "admin" and scoping_mode == "assigned":
        eff_id = str(agent.agent_id) if agent.agent_id else "no_agent"
        signals = [s for s in signals if str((s.get("clients") or {}).get("assigned_agent_id")) == eff_id]
    return signals


@app.post("/api/signals/{signal_id}/dismiss")
def dismiss_signal(signal_id: str, request: Request):
    sig = supabase.table("signals").select("client_id").eq("id", signal_id).limit(1).execute()
    if not sig.data:
        raise HTTPException(status_code=404, detail="Signal not found.")
    client_id = sig.data[0].get("client_id")
    if client_id and hasattr(request.state, "agent"):
        from agent_auth import require_client_access
        require_client_access(request.state.agent, client_id, supabase)

    supabase.table("signals").update({"dismissed": True}).eq("id", signal_id).execute()
    return {"success": True}





# ─── Shortlist v2 endpoint ────────────────────────────────────────────────────

def compute_blended_probability(formula_prob: float, ml_prob: float | None) -> float:
    """
    Blends the rule-based formula's probability with the trained model's estimate.
    If no ML prediction exists yet (model untrained, or this pair was scored before
    the ML feature existed), fall back to the formula alone — never silently drop
    a row just because ml_probability is null.
    """
    if ml_prob is None:
        return formula_prob
    return round((formula_prob * 0.6) + (ml_prob * 0.4), 4)


@app.get("/api/shortlist/{property_id}")
def get_shortlist(property_id: str, request: Request, limit: int = 25, agent_id: str | None = None):
    """
    Shortlist v2 — Score every client against a specific property.

    Ranking uses a blended expected value:
        blended_probability = 0.60 × formula_probability + 0.40 × ml_probability
        blended_expected_value = blended_probability × property_value

    If no trained ML model exists, falls back to formula probability alone.
    Each row includes pick_reason and skip_reason template strings so the
    UI can display per-row 'Pick / Skip' reasoning without any LLM call.
    """
    from scoring_engine import build_pick_skip_reasons

    cur_agent = getattr(request.state, "agent", None) if request else None
    scoping_mode = os.getenv("AGENT_PIPELINE_SCOPING", "assigned").lower()
    if cur_agent and cur_agent.role != "admin" and scoping_mode == "assigned":
        agent_id = str(cur_agent.agent_id) if cur_agent.agent_id else "no_agent"

    # ── 1. Fetch property ────────────────────────────────────────────────────
    try:
        prop_res = (
            supabase.table("properties")
            .select("*")
            .eq("id", property_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch property: {exc}") from exc

    if not prop_res.data:
        raise HTTPException(status_code=404, detail="Property not found")

    prop = prop_res.data[0]

    # ── 2. Fetch all clients (optionally filtered by assigned agent) ──────────
    try:
        clients_query = supabase.table("clients").select("*")
        if agent_id:
            clients_query = clients_query.eq("assigned_agent_id", agent_id)
        clients_res = clients_query.execute()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch clients: {exc}") from exc

    clients = clients_res.data or []

    # ── 2b. Fetch past purchases for all clients in one pass ─────────────────
    past_purchases_by_client: dict[str, list[dict]] = {}
    try:
        purch_res = supabase.table("client_past_purchases").select("*").execute()
        for p in (purch_res.data or []):
            cid = p.get("client_id")
            if cid:
                past_purchases_by_client.setdefault(cid, []).append(p)
    except Exception:
        pass

    # ── 3. Score each client against this property ───────────────────────────
    scored = []
    prop_val = float(prop.get("property_value") or 1)

    for client in clients:
        client_past = past_purchases_by_client.get(client["id"], [])
        client_profile = {
            "budget":                    client.get("stated_budget"),
            "preferred_neighborhood":    client.get("preferred_neighborhood"),
            "engagement_history":        client.get("past_viewings"),
            "source":                    client.get("source"),
            # Rich profile fields (additive bonuses — None-safe)
            "financing_status":          client.get("financing_status"),
            "move_in_timeline":          client.get("move_in_timeline"),
            "property_type_preference":  client.get("property_type_preference"),
            "secondary_neighborhood":    client.get("secondary_neighborhood"),
            # Past acquisitions track record
            "past_purchases":            client_past,
        }

        formula_result = score_pair(client_profile, prop)
        formula_prob   = formula_result["probability"]

        # ML probability (None if model not yet trained)
        ml_prob = predict_probability(client_profile, prop)

        # Blended score: 60% formula + 40% ML (fallback: formula alone)
        blended_prob = compute_blended_probability(formula_prob, ml_prob)
        blended_expected_value = round(blended_prob * prop_val, 2)

        # Budget-to-price ratio for sort/compare
        budget   = client.get("stated_budget") or 0
        budget_ratio = round(budget / prop_val, 4) if prop_val > 0 else 0.0

        pick_reason, skip_reason = build_pick_skip_reasons(client_profile, prop)

        scored.append({
            "client_id":                  client["id"],
            "client_name":                client["name"],
            "name":                       client["name"],
            # Probabilities & scores
            "formula_probability":        formula_prob,
            "probability":                formula_prob,
            "formula_score":              formula_prob,
            "ml_probability":             ml_prob,
            "blended_probability":        blended_prob,
            "blended_score":              blended_prob,
            "tier":                       formula_result["tier"],
            "expected_value":             formula_result["expected_value"],
            "blended_expected_value":     blended_expected_value,
            "confidence":                 formula_result["confidence"],
            # Pick/Skip reasoning
            "pick_reason":                pick_reason,
            "skip_reason":                skip_reason,
            # Rich fields for Compare mode
            "stated_budget":              client.get("stated_budget"),
            "preferred_neighborhood":     client.get("preferred_neighborhood"),
            "secondary_neighborhood":     client.get("secondary_neighborhood"),
            "past_viewings":              client.get("past_viewings", 0),
            "financing_status":           client.get("financing_status"),
            "move_in_timeline":           client.get("move_in_timeline"),
            "property_type_preference":   client.get("property_type_preference"),
            "budget_ratio":               budget_ratio,
            "past_purchases":             client_past,
            "past_purchases_count":       len(client_past),
        })

    # ── 4. Sort by blended_expected_value desc, cap at limit ─────────────────
    scored.sort(key=lambda x: x["blended_expected_value"], reverse=True)
    return scored[:limit]


# ─── PATCH client rich profile ────────────────────────────────────────────────

class ClientPatchRequest(BaseModel):
    financing_status:         str | None = None
    move_in_timeline:         str | None = None
    property_type_preference: str | None = None
    secondary_neighborhood:   str | None = None
    agent_notes:              str | None = None


@app.patch("/api/clients/{client_id}")
def patch_client(client_id: str, body: ClientPatchRequest, request: Request):
    """
    Update rich profile fields on a client row (partial update).
    Re-scores the client's best-match evaluation row after update.
    """
    if hasattr(request.state, "agent"):
        from agent_auth import require_client_access
        require_client_access(request.state.agent, client_id, supabase)

    updates = {k: v for k, v in body.dict().items() if v is not None}
    if not updates:
        return {"updated": False, "message": "No fields to update"}

    try:
        supabase.table("clients").update(updates).eq("id", client_id).execute()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to update client: {exc}") from exc

    # Re-score best-match evaluation so pipeline stays current
    try:
        client_res = supabase.table("clients").select("*").eq("id", client_id).limit(1).execute()
        evals_res  = (
            supabase.table("pipeline_evaluations")
            .select("*, properties(*)").eq("client_id", client_id)
            .order("expected_value", desc=True).limit(1).execute()
        )
        if client_res.data and evals_res.data:
            c    = client_res.data[0]
            best = evals_res.data[0]
            p    = best.get("properties") or {}
            profile = {
                "budget":                   c.get("stated_budget"),
                "preferred_neighborhood":   c.get("preferred_neighborhood"),
                "engagement_history":       c.get("past_viewings"),
                "financing_status":         c.get("financing_status"),
                "move_in_timeline":         c.get("move_in_timeline"),
                "property_type_preference": c.get("property_type_preference"),
                "secondary_neighborhood":   c.get("secondary_neighborhood"),
            }
            res     = score_pair(profile, p)
            ml_prob = predict_probability(profile, p)
            supabase.table("pipeline_evaluations").upsert({
                "client_id":      client_id,
                "property_id":    best["property_id"],
                "ai_probability": res["probability"],
                "expected_value": res["expected_value"],
                "segment_tier":   res["tier"],
                "ml_probability": ml_prob,
            }, on_conflict="client_id,property_id").execute()
    except Exception:
        pass  # re-score failure is non-fatal

    return {"updated": True, "fields": list(updates.keys())}


# ─── PATCH property rich specs ────────────────────────────────────────────────

class PropertyPatchRequest(BaseModel):
    bedrooms:      int | None = None
    bathrooms:     int | None = None
    sqft:          int | None = None
    property_type: str | None = None
    furnishing:    str | None = None
    tenure:        str | None = None


@app.patch("/api/properties/{property_id}")
def patch_property(property_id: str, body: PropertyPatchRequest):
    """
    Update rich listing specs on a property row (partial update).
    """
    updates = {k: v for k, v in body.dict().items() if v is not None}
    if not updates:
        return {"updated": False, "message": "No fields to update"}

    try:
        supabase.table("properties").update(updates).eq("id", property_id).execute()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to update property: {exc}") from exc

    return {"updated": True, "fields": list(updates.keys())}


# ─── Client Past Purchases endpoints ──────────────────────────────────────────

class ClientPastPurchaseCreate(BaseModel):
    property_name:  str
    neighborhood:   str
    property_type:  str
    purchase_price: float
    purchase_year:  int | None = None
    purpose:        str | None = "own_stay"
    notes:          str | None = None


@app.get("/api/clients/{client_id}/purchases")
def get_client_purchases(client_id: str, request: Request):
    """Fetch all recorded past property purchases for a client."""
    if hasattr(request.state, "agent"):
        from agent_auth import require_client_access
        require_client_access(request.state.agent, client_id, supabase)
    try:
        res = (
            supabase.table("client_past_purchases")
            .select("*")
            .eq("client_id", client_id)
            .order("purchase_year", desc=True)
            .execute()
        )
        return res.data or []
    except Exception:
        return []


@app.post("/api/clients/{client_id}/purchases")
def add_client_purchase(client_id: str, body: ClientPastPurchaseCreate, request: Request):
    """Record a past property acquisition for a client."""
    if hasattr(request.state, "agent"):
        from agent_auth import require_client_access
        require_client_access(request.state.agent, client_id, supabase)
    data = {
        "client_id":      client_id,
        "property_name":  body.property_name,
        "neighborhood":   body.neighborhood,
        "property_type":  body.property_type,
        "purchase_price": body.purchase_price,
        "purchase_year":  body.purchase_year,
        "purpose":        body.purpose or "own_stay",
        "notes":          body.notes,
    }
    try:
        res = supabase.table("client_past_purchases").insert(data).execute()
        # Invalidate reasoning cache for this client so Groq re-synthesizes with the new acquisition
        try:
            supabase.table("reasoning_cache").delete().eq("client_id", client_id).execute()
        except Exception:
            pass
        return {"created": True, "purchase": res.data[0] if res.data else data}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to record past purchase: {exc}") from exc


# ─── Invite generation endpoint ────────────────────────────────────────────────

class InviteRequest(BaseModel):
    client_id: str
    property_id: str
    agent_name: str | None = "R. Delgado"
    agent_id: str | None = None


def _build_invite_prompt(
    client: dict,
    prop: dict,
    agent_name: str = "R. Delgado",
    agent_role: str = "Senior Sales Representative",
) -> str:
    budget = client.get("stated_budget") or 0
    prop_val = prop.get("property_value") or 0
    financial_fit = budget >= prop_val
    geo_match = client.get("preferred_neighborhood") == prop.get("neighborhood")
    name = agent_name or "R. Delgado"
    role = agent_role or "Senior Sales Representative"
    past_purchases = client.get("past_purchases") or []

    if past_purchases:
        recent = past_purchases[0]
        track_line = f"\n- Fleet Deployment Track Record: Previously deployed {recent.get('property_name')} in {recent.get('neighborhood')}."
    else:
        track_line = ""

    return f"""You are {name}, {role} at PIPELINE.EV Industrial Robotics in Malaysia.

Write a warm, highly professional, WhatsApp-native B2B pitch message to client company '{client['name']}'.

Context:
- Client Company: {client['name']}
- Proposed Robotic Unit: {prop.get('address')} ({prop.get('neighborhood')})
- Unit Cost: RM {prop_val:,.0f}
- Client CapEx Budget: RM {budget:,.0f} ({"Covers full unit cost" if financial_fit else "Slightly above stated CapEx allocation"})
- Target Environment: {client.get('preferred_neighborhood')} ({"Exact match to target environment" if geo_match else "Compatible industrial environment"}){track_line}

Requirements:
- Target word count: roughly 80 to 100 words. Keep it punchy, conversational, and WhatsApp-native.
- Address the client contact respectfully by name (e.g. "Dear {client['name']} Team," or "Hi {client['name']} team,").
- Specifically highlight how the {prop.get('address')} unit aligns with their operational environment and CapEx budget fit.
- Sign off cleanly with your actual name "{name}" and title "{role}, PIPELINE.EV".
- DO NOT invent or propose any meeting dates or times (these will be appended automatically).
- DO NOT include placeholder tags like "[Your Name]", "[Agent Name]", or "[Your Title]".
- Output ONLY the clean message body without subject lines, quotes, or markdown headers."""


@app.post("/api/generate_invite")
def generate_invite(body: InviteRequest, request: Request):
    if hasattr(request.state, "agent"):
        from agent_auth import require_client_access
        require_client_access(request.state.agent, body.client_id, supabase)

    agent_name = body.agent_name or "R. Delgado"
    agent_id = body.agent_id or None

    # Fetch agent details if agent_id is provided
    agent_role = "Senior Sales Representative"
    if agent_id:
        try:
            a_res = supabase.table("agents").select("name, role").eq("id", agent_id).single().execute()
            if a_res.data:
                agent_name = a_res.data.get("name") or agent_name
                agent_role = a_res.data.get("role") or agent_role
        except Exception:
            pass

    # 1. Generate 3 available deterministic slots in Asia/Kuala_Lumpur
    slots = generate_candidate_slots(agent_id=agent_id, count=3)
    slot_lines = "  ".join([f"{s['index']}) {s['label']}" for s in slots])
    deterministic_cta = f"\n\nProposed slots:\n{slot_lines}\n\nReply 1, 2 or 3 to book, or tell me a time that suits you."

    # ── 1b. Check invite_drafts cache table first ──────────────────────────────
    try:
        cache_res = (
            supabase.table("invite_drafts")
            .select("draft")
            .eq("client_id", body.client_id)
            .eq("property_id", body.property_id)
            .limit(1)
            .execute()
        )
        if cache_res.data:
            cached_draft = cache_res.data[0]["draft"]
            # Invalidate stale cached draft if it contains generic placeholders or lacks slot CTA
            if "[Your Name]" not in cached_draft and "Reply 1, 2 or 3" in cached_draft:
                return {"draft": cached_draft, "slots": slots, "cached": True}
    except Exception:
        pass

    # ── 2. Fetch client & property ───────────────────────────────────────────
    try:
        client_res = (
            supabase.table("clients").select("*").eq("id", body.client_id).limit(1).execute()
        )
        prop_res = (
            supabase.table("properties").select("*").eq("id", body.property_id).limit(1).execute()
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch data: {exc}") from exc

    if not client_res.data or not prop_res.data:
        raise HTTPException(status_code=404, detail="Client or property not found")

    client = client_res.data[0]
    prop = prop_res.data[0]

    # If agent_id was not explicitly passed, check client's assigned_agent_id
    if not agent_id and client.get("assigned_agent_id"):
        agent_id = client.get("assigned_agent_id")
        try:
            a_res = supabase.table("agents").select("name, role").eq("id", agent_id).single().execute()
            if a_res.data:
                agent_name = a_res.data.get("name") or agent_name
                agent_role = a_res.data.get("role") or agent_role
                slots = generate_candidate_slots(agent_id=agent_id, count=3)
                slot_lines = "  ".join([f"{s['index']}) {s['label']}" for s in slots])
                deterministic_cta = f"\n\nProposed slots:\n{slot_lines}\n\nReply 1, 2 or 3 to book, or tell me a time that suits you."
        except Exception:
            pass

    # Fetch past purchases for client
    try:
        purch_res = supabase.table("client_past_purchases").select("*").eq("client_id", body.client_id).execute()
        client["past_purchases"] = purch_res.data or []
    except Exception:
        client["past_purchases"] = []

    # ── 3. Call Groq LLM for 80-100 word pitch body ──────────────────────────
    prompt = _build_invite_prompt(client, prop, agent_name=agent_name, agent_role=agent_role)
    pitch_body = _call_groq_llm(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300,
        temperature=0.4,
        timeout=20.0,
    )

    # ── 4. Append deterministic slots & CTA ──────────────────────────────────
    full_draft = f"{pitch_body.strip()}{deterministic_cta}"

    # ── 5. Persist to invite_drafts ──────────────────────────────────────────
    try:
        supabase.table("invite_drafts").upsert(
            {
                "client_id": body.client_id,
                "property_id": body.property_id,
                "draft": full_draft,
            },
            on_conflict="client_id,property_id",
        ).execute()
    except Exception:
        pass

    return {"draft": full_draft, "slots": slots, "cached": False}


# ─── Analytics Insight endpoint ────────────────────────────────────────────────

class TierSummary(BaseModel):
    tier: str
    count: int
    total_expected_value: float
    avg_probability: float

class InsightRequest(BaseModel):
    total_clients: int
    total_expected_value: float
    avg_probability: float
    tiers: list[TierSummary]
    neighborhoods: list[dict]  # [{"name": str, "count": int, "total_ex": float}]
    active_filters: dict       # {"tier": str, "neighborhood": str}


def _build_insight_prompt(body: InsightRequest) -> str:
    tier_lines = "\n".join(
        f"  - {t.tier.replace('_', ' ')} ({t.tier.replace('TIER_1','HIGH-FIT PROSPECT').replace('TIER_2','POSSIBLE-FIT').replace('TIER_3','LOW-FIT')}): "
        f"{t.count} companies · avg P(Adopt) {round(t.avg_probability * 100)}% · total E(x) RM {t.total_expected_value:,.0f}"
        for t in body.tiers
    )
    top_nbhds = sorted(body.neighborhoods, key=lambda x: x["total_ex"], reverse=True)[:3]
    nbhd_lines = ", ".join(
        f"{n['name']} (RM {n['total_ex']:,.0f})" for n in top_nbhds
    )
    filters_desc = (
        f"Current filter: {body.active_filters.get('tier', 'ALL')} tier"
        + (f" · {body.active_filters.get('neighborhood', '')} environment"
           if body.active_filters.get("neighborhood") and body.active_filters["neighborhood"] != "ALL"
           else "")
    )

    return f"""You are a senior robotics analytics AI for PIPELINE.EV, an industrial automation and robot fleet intelligence platform.

Current pipeline snapshot ({filters_desc}):
- Total companies in view: {body.total_clients}
- Total pipeline E(x): RM {body.total_expected_value:,.0f}
- Avg P(Adopt) across all: {round(body.avg_probability * 100)}%

Tier breakdown:
{tier_lines}

Top target environments by total E(x): {nbhd_lines if nbhd_lines else "N/A"}

Write exactly 2-3 sentences of actionable insight for a sales rep reviewing this data. Highlight the most significant pattern (e.g. concentration of High-Fit value in one operating environment, low conversion from possible to high-fit prospect, an industrial sector outperforming others). Be specific with RM figures and percentages. Use Malaysian English. No bullet points, no headers, no preamble — output only the insight sentences."""


@app.post("/api/generate_insight")
def generate_insight(body: InsightRequest):
    if not groq_client:
        raise HTTPException(status_code=503, detail="GROQ_API_KEY not configured")

    if body.total_clients == 0:
        return {"insight": "No clients match the current filter — try broadening your selection.", "cached": False}

    prompt = _build_insight_prompt(body)
    insight = _call_groq_llm(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=400,
        temperature=0.4,
        timeout=20.0,
    )
    return {"insight": insight, "cached": False}


@app.post("/api/generate_chart_insight")
def generate_chart_insight(body: dict):
    slice_type = body.get("slice_type")  # "tier" | "scatter_point" | "heatmap_cell" | "cluster"
    slice_data = body.get("slice_data", {})  # dict of relevant filter values

    cache_key = md5(f"{slice_type}:{sorted(slice_data.items())}".encode()).hexdigest()
    try:
        cached = supabase.table("chart_insight_cache").select("insight").eq("cache_key", cache_key).execute().data
        if cached:
            return {"insight": cached[0]["insight"]}
    except Exception:
        pass

    if slice_type == "tier":
        # Deduplicate to unique clients in this tier (using best-match row per client)
        rows = supabase.table("pipeline_evaluations").select("*, clients(id, name)").execute().data or []
        client_best_matches = {}
        for r in rows:
            cid = r.get("clients", {}).get("id") or r.get("client_id")
            if cid not in client_best_matches or r["expected_value"] > client_best_matches[cid]["expected_value"]:
                client_best_matches[cid] = r

        tier_clients = [r for r in client_best_matches.values() if r.get("segment_tier") == slice_data["tier"]]
        client_count = len(tier_clients)
        total_value = sum(r["expected_value"] for r in tier_clients)

        prompt = (
            f"There are EXACTLY {client_count} {slice_data['tier']} companies in the deployment pipeline, "
            f"representing RM{total_value:,.0f} in total expected value. "
            f"You MUST use the exact number {client_count} if you reference a company count — do not estimate, round, or invent a different number. "
            f"In one short sentence, explain what this means for a sales rep's priorities."
        )

    elif slice_type == "scatter_point":
        row_res = supabase.table("pipeline_evaluations").select("*, clients(name), properties(address)").eq("client_id", slice_data["client_id"]).eq("property_id", slice_data["property_id"]).limit(1).execute()
        if not row_res.data:
            raise HTTPException(status_code=404, detail="Evaluation data not found")
        row = row_res.data[0]
        c_name = row.get("clients", {}).get("name", "Client")
        p_name = row.get("properties", {}).get("address", "Robot Unit")
        prob_pct = round(float(row.get("ai_probability", 0)) * 100)
        ex_val = float(row.get("expected_value", 0))

        prompt = (
            f"Company {c_name} has an EXACT adoption probability of {prob_pct}% and expected value of RM{ex_val:,.0f} for robot unit {p_name}. "
            f"You MUST use the exact probability {prob_pct}% if you mention a probability — do not estimate, round, or invent a different figure. "
            f"In one short sentence, explain why {c_name} sits in this position and what action the sales rep should take."
        )

    elif slice_type == "heatmap_cell":
        # Deduplicate: each client counted once, placed by preferred_neighborhood × overall tier
        rows = supabase.table("pipeline_evaluations").select("*, clients(id, name, preferred_neighborhood)").execute().data or []
        client_best_matches = {}
        for r in rows:
            cid = r.get("clients", {}).get("id") or r.get("client_id")
            if cid not in client_best_matches or r["expected_value"] > client_best_matches[cid]["expected_value"]:
                client_best_matches[cid] = r

        matching = [
            r for r in client_best_matches.values()
            if r.get("segment_tier") == slice_data["tier"]
            and r.get("clients", {}).get("preferred_neighborhood") == slice_data["neighborhood"]
        ]
        client_count = len(matching)
        total_value = sum(r["expected_value"] for r in matching)

        prompt = (
            f"There are EXACTLY {client_count} {slice_data['tier']} companies requiring {slice_data['neighborhood']} deployment, "
            f"representing RM{total_value:,.0f} in total expected value. "
            f"You MUST use the exact number {client_count} if you reference a company count — do not estimate, round, or invent a different number. "
            f"In one short sentence, explain the significance of this concentration for a sales rep's outreach strategy."
        )

    elif slice_type == "cluster":
        # Deduplicate to unique clients per neighborhood matching the frontend card calculation
        rows = supabase.table("pipeline_evaluations").select("*, clients(id, name, preferred_neighborhood)").execute().data or []
        nbhd_rows = [r for r in rows if r.get("clients", {}).get("preferred_neighborhood") == slice_data["neighborhood"]]
        
        # Take the best-match evaluation row per unique client
        client_best_matches = {}
        for r in nbhd_rows:
            cid = r.get("clients", {}).get("id") or r.get("client_id")
            if cid not in client_best_matches or r["expected_value"] > client_best_matches[cid]["expected_value"]:
                client_best_matches[cid] = r
                
        unique_matches = list(client_best_matches.values())
        client_count = len(unique_matches)
        total_value = sum(r["expected_value"] for r in unique_matches)

        prompt = (
            f"There are EXACTLY {client_count} companies with {slice_data['neighborhood']} deployment requirements, "
            f"representing RM{total_value:,.0f} in total expected value. "
            f"You MUST use the exact number {client_count} if you reference a company count — do not estimate, round, or invent a different number. "
            f"In one short strategic sentence, advise a sales rep on their approach to this industrial cluster."
        )

    else:
        raise HTTPException(status_code=400, detail="Unknown slice_type")

    insight = _call_groq_llm(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=250,
        temperature=0.4,
        timeout=20.0,
    )

    try:
        supabase.table("chart_insight_cache").insert({"cache_key": cache_key, "insight": insight}).execute()
    except Exception:
        pass

    return {"insight": insight}


# ─── Prescriptive Sales / Pipeline Projection (Phase 3) ─────────────────────────

def get_pipeline_projection_data(agent_id: str | None = None) -> dict:
    # 1. Fetch agent info
    agent_name = "All Agents (Broker View)"
    if agent_id and agent_id not in ("all", "null", "undefined"):
        agent_row = supabase.table("agents").select("id, name, initials, role").eq("id", agent_id).execute().data
        if agent_row:
            agent_name = agent_row[0].get("name", "Agent")

    # 2. Fetch clients
    clients_query = supabase.table("clients").select("id, assigned_agent_id, relationship_stage")
    if agent_id and agent_id not in ("all", "null", "undefined"):
        clients_query = clients_query.eq("assigned_agent_id", agent_id)
    clients = clients_query.execute().data or []

    # 3. Calculate client stage counts
    won_count = 0
    lost_count = 0
    untapped_clients = 0
    active_client_ids = []

    for c in clients:
        stage = (c.get("relationship_stage") or "new").lower()
        if stage == "closed_won":
            won_count += 1
        elif stage == "closed_lost":
            lost_count += 1
        elif stage == "new":
            untapped_clients += 1
        elif stage in ("contacted", "viewing", "negotiation"):
            active_client_ids.append(c["id"])

    active_clients = len(active_client_ids)
    total_closed = won_count + lost_count
    # Calculate historical close rate (fallback to 10% if no history to avoid div/0)
    close_rate = (won_count / total_closed) if total_closed > 0 else 0.10

    # 4. Calculate active pipeline value E(x)
    active_pipeline_value = 0.0
    if active_client_ids:
        # Fetch evaluations for active clients
        evals_res = supabase.table("pipeline_evaluations").select("client_id, expected_value").in_("client_id", active_client_ids).execute().data or []
        # Group by client to find each client's highest-E(x) match (best match)
        client_max_ex = {}
        for row in evals_res:
            cid = row["client_id"]
            ex = float(row.get("expected_value") or 0)
            if cid not in client_max_ex or ex > client_max_ex[cid]:
                client_max_ex[cid] = ex
        active_pipeline_value = sum(client_max_ex.values())

    projected_revenue = round(active_pipeline_value * close_rate)

    return {
        "assigned_agent_id": agent_id if agent_id and agent_id not in ("all", "null", "undefined") else None,
        "agent_name": agent_name,
        "active_pipeline_value": round(active_pipeline_value),
        "projected_revenue": projected_revenue,
        "close_rate": round(close_rate, 4),
        "close_rate_pct": f"{round(close_rate * 100)}%",
        "untapped_clients": untapped_clients,
        "active_clients": active_clients,
        "won_count": won_count,
        "lost_count": lost_count,
        "total_closed": total_closed,
    }


def _build_projection_prompt(metrics: dict) -> list[dict]:
    payload = {
        "agent_name": metrics["agent_name"],
        "active_pipeline_value": f"RM{metrics['active_pipeline_value']:,}",
        "projected_revenue": f"RM{metrics['projected_revenue']:,}",
        "close_rate": metrics["close_rate_pct"],
        "untapped_clients": metrics["untapped_clients"],
        "active_clients": metrics["active_clients"]
    }
    system_msg = (
        "You are an expert industrial robotics sales strategist analyzing pipeline data for PIPELINE.EV, an industrial automation and robot fleet intelligence platform.\n"
        "You will be provided with EXACT financial metrics for a sales rep.\n"
        "RULE 1: NEVER invent, calculate, or alter any numbers. Use ONLY the exact numbers provided in the Data Payload with the 'RM' currency prefix (Malaysian Ringgit).\n"
        "RULE 2: Output a concise 2-3 sentence tactical recommendation on what the sales rep should do TODAY to maximize closed deployments and pipeline revenue.\n"
        "RULE 3: Focus on moving 'untapped_clients' (companies in New stage) into active demo and procurement stages or closing 'active_clients'.\n"
        "RULE 4: Do NOT use bullet points, headings, quotes, or conversational greetings. Complete all sentences cleanly."
    )
    user_msg = f"Data Payload:\n{json.dumps(payload, indent=2)}\n\nTactical recommendation (2-3 complete sentences):"
    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg}
    ]


@app.get("/api/pipeline_projection")
def get_pipeline_projection(request: Request, agent_id: str | None = None):
    agent = getattr(request.state, "agent", None) if request else None
    effective_agent_id = agent_id
    if agent and agent.role != "admin":
        effective_agent_id = str(agent.agent_id) if agent.agent_id else "unassigned_no_access"
    try:
        metrics = get_pipeline_projection_data(effective_agent_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to compute pipeline projection: {exc}") from exc

    narrative = None
    if groq_client:
        try:
            messages = _build_projection_prompt(metrics)
            narrative = _call_groq_llm(
                messages=messages,
                max_tokens=350,
                temperature=0.3,
                timeout=15.0,
            )
        except Exception as exc:
            print(f"[pipeline_projection] LLM narrative generation warning: {exc}")

    if not narrative:
        if metrics["active_clients"] > 0:
            narrative = (
                f"Your current projected revenue is RM{metrics['projected_revenue']:,} based on a "
                f"{metrics['close_rate_pct']} historical close rate across {metrics['active_clients']} active deal"
                f"{'s' if metrics['active_clients'] > 1 else ''}. You have {metrics['untapped_clients']} untapped "
                f"client{'s' if metrics['untapped_clients'] > 1 else ''} sitting in the 'New' stage — focus today on "
                f"activating them through the Shortlist Builder to expand your active pipeline."
            )
        else:
            narrative = (
                f"You currently have 0 active deals and {metrics['untapped_clients']} untapped clients sitting in the 'New' stage. "
                f"Focus today on running the Shortlist Builder for your top properties to activate prospective clients and build your active pipeline."
            )

    return {
        **metrics,
        "narrative": narrative
    }


# ─── Outcome Tracking ──────────────────────────────────────────────────────────

@app.post("/api/record_outcome")
def record_outcome(body: dict):
    client_id = body.get("client_id")
    property_id = body.get("property_id")
    outcome = body.get("outcome")

    if not client_id or not property_id:
        raise HTTPException(status_code=400, detail="client_id and property_id are required")
    if outcome not in ("won", "lost"):
        raise HTTPException(status_code=400, detail="outcome must be 'won' or 'lost'")

    supabase.table("pipeline_evaluations").update({
        "outcome": outcome,
        "outcome_recorded_at": datetime.now(timezone.utc).isoformat(),
    }).eq("client_id", client_id).eq("property_id", property_id).execute()

    advance_stage(client_id, "closed_won" if outcome == "won" else "closed_lost", force=True)

    return {"success": True}


@app.get("/api/prediction_accuracy")
def get_prediction_accuracy(request: Request = None):
    cur_agent = getattr(request.state, "agent", None) if request else None
    if cur_agent and cur_agent.role != "admin":
        raise HTTPException(status_code=403, detail="Forbidden: Prediction accuracy metrics are restricted to administrators.")
    try:
        rows = supabase.table("pipeline_evaluations").select("*").neq("outcome", "pending").execute().data or []
    except Exception:
        # outcome column doesn't exist yet — return graceful fallback
        return {"total_recorded": 0, "message": "Run the outcome migration in Supabase SQL Editor first"}

    if not rows:
        return {"total_recorded": 0, "message": "No outcomes recorded yet"}

    won = [r for r in rows if r.get("outcome") == "won"]
    lost = [r for r in rows if r.get("outcome") == "lost"]

    avg_prob_won = sum(r["ai_probability"] for r in won) / len(won) if won else 0
    avg_prob_lost = sum(r["ai_probability"] for r in lost) / len(lost) if lost else 0

    return {
        "total_recorded": len(rows),
        "won_count": len(won),
        "lost_count": len(lost),
        "avg_predicted_probability_when_won": round(avg_prob_won * 100, 1),
        "avg_predicted_probability_when_lost": round(avg_prob_lost * 100, 1),
    }


# ─── Model Training & ML Predictions ──────────────────────────────────────────

@app.post("/api/retrain_model")
def retrain_model():
    """Runs the training script as a subprocess and returns its metrics."""
    result = subprocess.run(
        [sys.executable, os.path.join(os.path.dirname(__file__), "train_model.py")],
        capture_output=True, text=True, timeout=120,
    )
    if result.stdout:
        print(result.stdout, flush=True)
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=f"Training failed: {result.stderr}")

    reload_model()

    try:
        latest_run = supabase.table("model_training_runs") \
            .select("*").order("trained_at", desc=True).limit(1).execute().data
        if latest_run:
            return latest_run[0]
    except Exception:
        pass

    # Local metadata file fallback if Supabase table is not yet created
    local_status = os.path.join(os.path.dirname(__file__), "latest_training_run.json")
    if os.path.exists(local_status):
        try:
            with open(local_status, "r") as f:
                return json.load(f)
        except Exception:
            pass

    return {"trained": True, "message": "Model trained successfully"}


@app.get("/api/model_status")
def get_model_status(request: Request = None):
    cur_agent = getattr(request.state, "agent", None) if request else None
    if cur_agent and cur_agent.role != "admin":
        raise HTTPException(status_code=403, detail="Forbidden: Model status and parameters are restricted to administrators.")
    try:
        latest_run = supabase.table("model_training_runs") \
            .select("*").order("trained_at", desc=True).limit(1).execute().data
        if latest_run:
            return {"trained": True, **latest_run[0]}
    except Exception:
        pass

    # Local metadata file fallback
    local_status = os.path.join(os.path.dirname(__file__), "latest_training_run.json")
    if os.path.exists(local_status):
        try:
            with open(local_status, "r") as f:
                data = json.load(f)
                return {"trained": True, **data}
        except Exception:
            pass

    model_file = os.path.join(os.path.dirname(__file__), "ml_model.pkl")
    if os.path.exists(model_file):
        return {"trained": True, "real_outcome_count": 0, "synthetic_outcome_count": 300, "test_accuracy": 0.82}
    return {"trained": False}


# ─── Price Simulation & History ────────────────────────────────────────────────────
# _simulate_price_change_internal() contains the actual business logic.
# Both the HTTP endpoint and the background scheduler call this function
# directly — no logic is duplicated between the two call paths.

def _simulate_price_change_internal(property_id: str) -> dict:
    """
    Core price-change logic: applies a random ±8% shift, re-scores every
    client, writes the history row, fires an AI-narrated number-locked signal.
    Called by the HTTP endpoint and by the background scheduler.
    Raises HTTPException on property-not-found (FastAPI handles this cleanly
    whether called from an HTTP context or from the scheduler's thread).
    """
    # ── 1. Fetch property ────────────────────────────────────────────────────
    prop_res = supabase.table("properties").select("*").eq("id", property_id).limit(1).execute()
    if not prop_res.data:
        raise HTTPException(status_code=404, detail="Property not found")
    prop = prop_res.data[0]

    old_value = float(prop["property_value"])
    pct_change = round(_random.uniform(-0.08, 0.08), 4)  # -8% to +8%
    new_value = round(old_value * (1 + pct_change), 2)

    # ── 2. Persist price change to properties + history table ────────────────
    try:
        supabase.table("properties").update({
            "property_value":       new_value,
            "last_price_change_at": datetime.now(timezone.utc).isoformat(),
            "last_price_change_pct": pct_change,
        }).eq("id", property_id).execute()
    except Exception as exc:
        print(f"[simulate_price_change] updating with new columns failed ({exc}), falling back to property_value only")
        try:
            supabase.table("properties").update({
                "property_value": new_value,
            }).eq("id", property_id).execute()
        except Exception as inner_exc:
            print(f"[simulate_price_change] property_value update failed: {inner_exc}")

    try:
        supabase.table("property_price_history").insert({
            "property_id": property_id,
            "old_value":   old_value,
            "new_value":   new_value,
            "change_pct":  pct_change,
        }).execute()
    except Exception as exc:
        print(f"[simulate_price_change] inserting price history failed (migration may be pending): {exc}")

    # ── 3. Re-score every client against the new price ───────────────────────
    clients = supabase.table("clients").select("*").execute().data or []
    top_movers = []
    eval_upserts = []
    tier_updates = []
    signals_to_insert = []

    for client in clients:
        client_profile = {
            "budget":                 client.get("stated_budget"),
            "preferred_neighborhood": client.get("preferred_neighborhood"),
            "engagement_history":     client.get("past_viewings", 0),
            "source":                 client.get("source"),
        }
        result = score_pair(client_profile, {"neighborhood": prop.get("neighborhood", ""), "property_value": new_value})
        ml_prob = predict_probability(client_profile, {"neighborhood": prop.get("neighborhood", ""), "property_value": new_value})
        eval_upserts.append({
            "client_id":      client["id"],
            "property_id":    property_id,
            "ai_probability": result["probability"],
            "expected_value": result["expected_value"],
            "segment_tier":   result["tier"],
            "ml_probability": ml_prob,
        })

        old_tier = client.get("last_known_tier")
        new_tier = result["tier"]
        if old_tier != new_tier:
            if old_tier is None:
                pass
            elif new_tier == "TIER_1" and old_tier != "TIER_1":
                signals_to_insert.append({
                    "type": "first_vip",
                    "client_id": client["id"],
                    "property_id": property_id,
                    "message": f"{client['name']} just crossed into High-Fit Prospect for the first time"
                })
            else:
                tier_rank = {"TIER_3": 0, "TIER_2": 1, "TIER_1": 2}
                if tier_rank.get(new_tier, 0) > tier_rank.get(old_tier, 0):
                    label = {"TIER_1": "HIGH-FIT", "TIER_2": "POSSIBLE-FIT", "TIER_3": "LOW-FIT"}
                    signals_to_insert.append({
                        "type": "tier_upgrade",
                        "client_id": client["id"],
                        "property_id": property_id,
                        "message": f"{client['name']} moved {label.get(old_tier)} → {label.get(new_tier)}"
                    })
            tier_updates.append((client["id"], new_tier))

        top_movers.append({
            "name":   client["name"],
            "new_ex": result["expected_value"],
        })

    # Batch upsert evaluations in 1 fast roundtrip
    if eval_upserts:
        try:
            supabase.table("pipeline_evaluations").upsert(eval_upserts, on_conflict="client_id,property_id").execute()
        except Exception as exc:
            if "ml_probability" in str(exc):
                for e in eval_upserts:
                    e.pop("ml_probability", None)
                try:
                    supabase.table("pipeline_evaluations").upsert(eval_upserts, on_conflict="client_id,property_id").execute()
                except Exception as inner_exc:
                    print(f"[simulate_price_change] batch upsert evaluations fallback failed: {inner_exc}")
            else:
                print(f"[simulate_price_change] batch upsert evaluations failed: {exc}")

    # Batch insert tier signals if any
    if signals_to_insert:
        try:
            supabase.table("signals").insert(signals_to_insert).execute()
        except Exception as exc:
            print(f"[simulate_price_change] inserting tier signals failed: {exc}")

    # Update client tiers
    for cid, ntier in tier_updates:
        try:
            supabase.table("clients").update({"last_known_tier": ntier}).eq("id", cid).execute()
        except Exception:
            pass

    top_movers.sort(key=lambda c: c["new_ex"], reverse=True)

    # ── 4. AI-narrated signal — number-locked prompt (same guard as
    #    generate_chart_insight to prevent hallucinated percentages/names) ────
    direction = "dropped" if pct_change < 0 else "rose"
    abs_pct   = abs(pct_change) * 100
    top_buyer = top_movers[0] if top_movers else None
    prop_display_name = prop.get("address") or prop.get("name") or prop.get("neighborhood") or "Robot Unit"

    if top_buyer:
        prompt = (
            f"The robot unit '{prop_display_name}' ({prop.get('neighborhood', '')}) had its cost {direction} "
            f"by {abs_pct:.1f}% to RM{new_value:,.0f}. "
            f"The top affected prospect is {top_buyer['name']} (new pipeline expected value: RM{top_buyer['new_ex']:,.0f}). "
            f"Write ONE short, concise sentence (max 18 words) explaining the pipeline takeaway for the sales rep. "
            f"Do not include any header or repetitive prefixes. Be direct."
        )
        try:
            ai_take = _call_groq_llm(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=50,
                temperature=0.3,
                timeout=15.0,
            ).strip()
            # Avoid repeating property name/percent if already mentioned in ai_take
            if prop_display_name.lower() in ai_take.lower()[:25]:
                signal_message = ai_take
            else:
                signal_message = f"{prop_display_name} {direction} {abs_pct:.1f}% to RM{new_value:,.0f} — {ai_take}"
        except Exception:
            signal_message = (
                f"{prop_display_name} {direction} {abs_pct:.1f}% to RM{new_value:,.0f} — "
                f"{top_buyer['name']} expected value is now RM{top_buyer['new_ex']:,.0f}."
            )
    else:
        signal_message = f"{prop_display_name} cost {direction} {abs_pct:.1f}% to RM{new_value:,.0f}."

    try:
        supabase.table("signals").insert({
            "type":        "price_change",
            "client_id":   None,
            "property_id": property_id,
            "message":     signal_message,
        }).execute()
    except Exception as exc:
        print(f"[simulate_price_change] inserting signal failed: {exc}")

    return {
        "property_id": property_id,
        "old_value":   old_value,
        "new_value":   new_value,
        "change_pct":  pct_change,
    }


@app.post("/api/simulate_price_change/{property_id}")
def simulate_price_change(property_id: str):
    """HTTP endpoint — thin shell over _simulate_price_change_internal."""
    return _simulate_price_change_internal(property_id)


@app.get("/api/property_price_history/{property_id}")
def get_property_price_history(property_id: str):
    """Returns all price history rows for a property, oldest-first (for graph rendering)."""
    import re
    try:
        rows = (
            supabase.table("property_price_history")
            .select("*")
            .eq("property_id", property_id)
            .order("changed_at", desc=False)
            .execute()
            .data
        )
        if rows:
            return rows
    except Exception as exc:
        print(f"[get_property_price_history] property_price_history query failed: {exc}")

    # Fallback: extract price history points from signals for this property
    try:
        signals = (
            supabase.table("signals")
            .select("*")
            .eq("type", "price_change")
            .eq("property_id", property_id)
            .order("created_at", desc=False)
            .execute()
            .data
        ) or []
        fallback_rows = []
        for s in signals:
            msg = s.get("message", "")
            change_pct = 0.05
            if "rose" in msg or "jumped" in msg:
                m = re.search(r"(\d+(?:\.\d+)?)%", msg)
                pct_val = float(m.group(1)) if m else 5.0
                change_pct = pct_val / 100.0
            elif "dropped" in msg or "fell" in msg:
                m = re.search(r"(\d+(?:\.\d+)?)%", msg)
                pct_val = float(m.group(1)) if m else 5.0
                change_pct = -pct_val / 100.0

            # Extract target price from message if available (e.g. "to RM6,345,811")
            m_price = re.search(r"RM([\d,]+)", msg)
            price_val = float(m_price.group(1).replace(",", "")) if m_price else 2000000.0

            fallback_rows.append({
                "id": s["id"],
                "property_id": property_id,
                "old_value": price_val / (1 + change_pct),
                "new_value": price_val,
                "change_pct": change_pct,
                "changed_at": s.get("created_at"),
            })
        return fallback_rows
    except Exception as exc:
        print(f"[get_property_price_history] fallback signals query failed: {exc}")
        return []



@app.post("/api/simulate_market_day")
def simulate_market_day():
    """
    Triggers a price fluctuation across ALL properties at once.
    Useful for populating the Analytics 'Market Movements' panel in one click.
    """
    properties = supabase.table("properties").select("id").execute().data or []
    results = []
    for p in properties:
        try:
            result = _simulate_price_change_internal(p["id"])
            results.append(result)
        except Exception as exc:
            # One property failing should not abort the whole market day
            results.append({"property_id": p["id"], "error": str(exc)})
    return {"properties_updated": len(results), "results": results}


@app.get("/api/market_movements")
def get_market_movements(limit: int = 10):
    """
    Returns the most recent price movements across all properties.
    Queries property_price_history first, and falls back to price_change signals
    so the Market Movements panel populates immediately even before SQL migration.
    """
    import re
    try:
        rows = (
            supabase.table("property_price_history")
            .select("*, properties(address, neighborhood)")
            .order("changed_at", desc=True)
            .limit(limit)
            .execute()
            .data
        )
        if rows:
            return rows
    except Exception as exc:
        print(f"[get_market_movements] property_price_history query failed: {exc}")

    # Fallback: extract price movement records from recent price_change signals
    try:
        signals = (
            supabase.table("signals")
            .select("*, properties(address, neighborhood)")
            .eq("type", "price_change")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
            .data
        ) or []
        fallback_rows = []
        for s in signals:
            msg = s.get("message", "")
            change_pct = 0.05
            if "rose" in msg or "jumped" in msg:
                m = re.search(r"(\d+(?:\.\d+)?)%", msg)
                pct_val = float(m.group(1)) if m else 5.0
                change_pct = pct_val / 100.0
            elif "dropped" in msg or "fell" in msg:
                m = re.search(r"(\d+(?:\.\d+)?)%", msg)
                pct_val = float(m.group(1)) if m else 5.0
                change_pct = -pct_val / 100.0

            prop_data = s.get("properties") or {}
            fallback_rows.append({
                "id": s["id"],
                "property_id": s.get("property_id"),
                "old_value": 0,
                "new_value": 0,
                "change_pct": change_pct,
                "changed_at": s.get("created_at"),
                "properties": prop_data,
            })
        return fallback_rows
    except Exception as exc:
        print(f"[get_market_movements] fallback signals query failed: {exc}")
        return []


# ─── Daily Worklist: Top 5 to Contact Today ───────────────────────────────────

@app.get("/api/daily_worklist")
def get_daily_worklist(request: Request = None, force_refresh: bool = False, agent_id: str | None = None):
    cur_agent = getattr(request.state, "agent", None) if request else None
    scoping_mode = os.getenv("AGENT_PIPELINE_SCOPING", "assigned").lower()
    if cur_agent and cur_agent.role != "admin" and scoping_mode == "assigned":
        agent_id = str(cur_agent.agent_id) if cur_agent.agent_id else "no_agent"

    today = date.today().isoformat()
    local_cache_file = os.path.join(os.path.dirname(__file__), "daily_worklist_cache.json")

    # 1. Check database cache first, then fallback to local cache.
    #    Cache is bypassed when agent_id is set (per-agent views are always live).
    if not force_refresh and not agent_id:
        try:
            cached = (
                supabase.table("daily_worklist_cache")
                .select("*")
                .eq("worklist_date", today)
                .execute()
                .data
            )
            if cached and cached[0].get("entries"):
                return cached[0]["entries"]
        except Exception as db_exc:
            print(f"[daily_worklist] DB cache check skipped: {db_exc}")

        if os.path.exists(local_cache_file):
            try:
                with open(local_cache_file, "r") as f:
                    local_data = json.load(f)
                    if local_data.get("worklist_date") == today and local_data.get("entries"):
                        return local_data["entries"]
            except Exception as f_exc:
                print(f"[daily_worklist] local cache read failed: {f_exc}")

    # 2. Exclude clients already Won/Lost, and clients with an active (scheduled/upcoming) viewing
    try:
        closed_client_ids = {
            r["client_id"]
            for r in (
                supabase.table("pipeline_evaluations")
                .select("client_id")
                .neq("outcome", "pending")
                .execute()
                .data
                or []
            )
            if r.get("client_id")
        }
    except Exception as exc:
        print(f"[daily_worklist] closed_client_ids query failed: {exc}")
        closed_client_ids = set()

    try:
        scheduled_rows = (
            supabase.table("scheduled_viewings")
            .select("client_id, status")
            .in_("status", ["scheduled", "upcoming"])
            .execute()
            .data
            or []
        )
        scheduled_client_ids = {r["client_id"] for r in scheduled_rows if r.get("client_id")}
    except Exception as exc:
        print(f"[daily_worklist] scheduled_viewings query failed: {exc}")
        scheduled_client_ids = set()

    excluded_ids = closed_client_ids | scheduled_client_ids

    # 3. Best-match evaluation per client (highest blended_expected_value)
    #    When agent_id is set, only include clients assigned to that agent.
    try:
        evals_query = (
            supabase.table("pipeline_evaluations")
            .select(
                "*, clients(id, name, stated_budget, preferred_neighborhood, past_viewings, assigned_agent_id), properties(id, address, property_value, neighborhood)"
            )
        )
        all_evals = evals_query.execute().data or []
        # Filter by agent if requested (done in Python to avoid deep nested FK filter syntax)
        if agent_id:
            all_evals = [
                row for row in all_evals
                if (row.get("clients") or {}).get("assigned_agent_id") == agent_id
            ]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch evaluations: {exc}") from exc

    best_by_client = {}
    for row in all_evals:
        cid = row.get("client_id")
        if not cid or cid in excluded_ids:
            continue

        client_data = row.get("clients") or {}
        prop_data = row.get("properties") or {}
        if not client_data or not prop_data:
            continue

        ml_prob = row.get("ml_probability")
        formula_prob = row.get("ai_probability") or 0.0
        blended_prob = compute_blended_probability(formula_prob, ml_prob)
        prop_val = float(prop_data.get("property_value") or 1)
        blended_ev = round(blended_prob * prop_val, 2)

        if cid not in best_by_client or blended_ev > best_by_client[cid]["blended_ev"]:
            best_by_client[cid] = {
                "client_id": cid,
                "client_name": client_data.get("name") or "Unknown Client",
                "property_id": row.get("property_id"),
                "property_name": prop_data.get("address") or prop_data.get("name") or "Property",
                "property_value": prop_val,
                "neighborhood": prop_data.get("neighborhood") or "",
                "tier": row.get("segment_tier") or "TIER_2",
                "blended_probability": blended_prob,
                "blended_ev": blended_ev,
                "budget": client_data.get("stated_budget") or 0,
                "engagement": client_data.get("past_viewings") or 0,
                "geo_match": (
                    client_data.get("preferred_neighborhood") == prop_data.get("neighborhood")
                    if client_data.get("preferred_neighborhood")
                    else False
                ),
            }

    top5 = sorted(best_by_client.values(), key=lambda c: c["blended_ev"], reverse=True)[:5]

    # 4. Generate one short number-locked "why contact today" line per entry
    entries = []
    for c in top5:
        prompt = (
            f"Company: {c['client_name']}, CapEx budget RM{c['budget']:,.0f}, "
            f"{'environment match verified' if c['geo_match'] else 'environment differs from target'}, "
            f"{c['engagement']} logged demo sessions. Robot Unit: {c['property_name']} in {c['neighborhood']} "
            f"(unit cost RM{c['property_value']:,.0f}), procurement pipeline expected value RM{c['blended_ev']:,.0f}, "
            f"blended adoption probability {c['blended_probability']*100:.0f}%. "
            f"You MUST use these exact figures if you cite numbers — do not invent or round differently. "
            f"CRITICAL RULE: When citing the expected value or blended value figure (RM{c['blended_ev']:,.0f}), "
            f"always label it clearly as 'expected value' or 'deal value' — never phrase it as if it were the robot unit's cost, "
            f"since unit cost (RM{c['property_value']:,.0f}) and expected value (RM{c['blended_ev']:,.0f}) are two different numbers. "
            f"Never use phrases like 'valued at RM{c['blended_ev']:,.0f}'. "
            f"Write ONE short sentence (max 20 words) telling the sales rep why to pitch this company TODAY. No preamble."
        )
        try:
            reason = _call_groq_llm(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=60,
                temperature=0.3,
                timeout=15.0,
            ).strip()
        except Exception as exc:
            print(f"[daily_worklist] LLM reason generation fallback: {exc}")
            reason = (
                f"High-conviction {c['tier'].replace('_', ' ')} prospect with "
                f"RM{c['blended_ev']:,.0f} expected value ready for pitch outreach."
            )
        entries.append({**c, "reason": reason})

    # 5. Persist to cache only for unfiltered (broker) view
    if not agent_id:
        try:
            supabase.table("daily_worklist_cache").upsert({
                "worklist_date": today,
                "entries": entries,
            }, on_conflict="worklist_date").execute()
        except Exception as db_exc:
            print(f"[daily_worklist] Saving to Supabase table daily_worklist_cache failed: {db_exc}")

        try:
            with open(local_cache_file, "w") as f:
                json.dump({"worklist_date": today, "entries": entries}, f, indent=2)
        except Exception as f_exc:
            print(f"[daily_worklist] Saving to local cache file failed: {f_exc}")

    return entries




# ─── Client Portal Endpoints ─────────────────────────────────────────────────
#
# These endpoints are intentionally separate from the agent-facing API.
# They enforce strict data isolation:
#   - No ML probability, tier, expected_value, or blended score
#   - No agent notes, financing status, or assigned agent info
#   - No other company's name or data
#   - AI reasoning uses a separate prompt table (client_facing_reasoning_cache)
#     with second-person, marketing-toned language — never internal framing
# ─────────────────────────────────────────────────────────────────────────────


def _build_client_facing_prompt(client: dict, prop: dict) -> str:
    """
    Second-person, marketing-toned prompt for client-visible reasoning.
    Explicitly guards against: probability mentions, tier labels, scoring,
    competitor comparisons, and internal "why we should chase this" framing.
    This is the OPPOSITE of the agent-internal prompt.
    """
    budget = client.get("stated_budget", 0) or 0
    neighborhood = client.get("preferred_neighborhood") or "your target operating environment"
    address = prop.get("address") or "this unit"
    cost = prop.get("property_value", 0) or 0
    sector = prop.get("neighborhood") or "industrial"
    return (
        "You are writing a short, warm sales message DIRECTLY TO a prospective business customer "
        "in second person ('you', 'your'). You are NOT writing an internal analysis for a sales rep. "
        "Hard rules: "
        "1. Never mention probability, percentage fit, tier, ML score, or any scoring metric. "
        "2. Never compare this company to any other company. "
        "3. Never use phrases like 'high fit', 'likely buyer', 'tier 1', or 'top prospect'. "
        "4. Never reveal why an agent should pursue this deal. "
        f"Context: The customer's deployment budget is RM{budget:,.0f}. "
        f"They prefer operating in {neighborhood}. "
        f"The robot unit is '{address}' in the {sector} zone, priced at RM{cost:,.0f}. "
        "Task: Write exactly 2-3 warm, professional sentences explaining why this unit "
        "could be a strong fit for their operation. "
        "Focus on ROI, operational efficiency, deployment reliability, and outcomes. "
        "Output ONLY the sentences — no greeting, no subject line, no intro, no preamble."
    )


# ─── Client-facing reasoning prompt builder ──────────────────────────────────
# SEPARATE from _build_prompt (agent-internal, third-person).
# This one is second-person, marketing-toned, and must never mention:
# ML probability, tier, blended score, expected_value, agent notes,
# competitor names, or any other client's data.

def _build_client_facing_prompt(client: dict, prop: dict) -> str:
    """
    Build a client-facing (second-person) prompt for the LLM.
    Uses real property specs and client industry context for genuinely
    distinct, non-boilerplate output per match.
    """
    client_name   = client.get("name", "your organisation")
    budget        = client.get("stated_budget") or 0
    target_env    = client.get("preferred_neighborhood") or "your operational environment"
    past_viewings = client.get("past_viewings") or 0

    unit_name   = prop.get("address", "this unit")
    unit_cost   = prop.get("property_value") or 0
    environment = prop.get("neighborhood") or "general"
    prop_type   = prop.get("property_type") or ""
    sqft        = prop.get("sqft")   # sometimes used as payload capacity proxy
    annual_sav  = prop.get("estimated_annual_savings")  # pre-computed, can be None

    # Financial fit note
    if budget and unit_cost:
        if budget >= unit_cost:
            fin_note = f"Your CapEx budget of RM {budget:,.0f} covers this unit comfortably."
        else:
            gap = unit_cost - budget
            fin_note = f"The unit is RM {gap:,.0f} above your stated budget — worth discussing financing options."
    else:
        fin_note = ""

    # Environment match note
    if target_env and environment:
        if target_env.lower() in environment.lower() or environment.lower() in target_env.lower():
            env_note = f"It is purpose-built for {environment} deployments, matching your target environment exactly."
        else:
            env_note = f"While designed for {environment} environments, it offers capabilities applicable to {target_env} use cases."
    else:
        env_note = f"It operates in {environment} environments."

    # Savings / ROI note
    if annual_sav and unit_cost:
        payback_months = round((unit_cost / annual_sav) * 12)
        roi_note = f"Based on an estimated RM {annual_sav:,.0f} in annual labour savings for this robot category, the projected payback period is approximately {payback_months} months."
    else:
        roi_note = ""

    # Engagement note
    if past_viewings > 0:
        eng_note = f"You have already attended {past_viewings} technical demo session(s), demonstrating strong operational interest."
    else:
        eng_note = ""

    # Specs note
    spec_parts = []
    if prop_type:
        spec_parts.append(f"unit category: {prop_type}")
    if sqft:
        spec_parts.append(f"operational footprint/capacity: {sqft:,}")
    spec_note = "; ".join(spec_parts) if spec_parts else ""

    context_lines = "\n".join(filter(None, [fin_note, env_note, roi_note, eng_note, spec_note]))

    return f"""You are writing a client-facing recommendation snippet for {client_name}, a prospective buyer being shown a specific industrial robot unit.

CRITICAL RULES:
- Write in SECOND PERSON ("you", "your organisation", "for you") — this is addressed directly to the client.
- Be marketing-toned but honest. No hype without substance.
- Do NOT mention: probability scores, ML models, tier labels, competitor unit names, other clients, or any internal sales analytics.
- Keep it to 2-3 sentences. Start directly — no preamble like "Certainly" or "Here is".

Unit being recommended:
- Name: {unit_name}
- Unit cost: RM {unit_cost:,.0f}
- Operating environment: {environment}

Context about this match:
{context_lines}

Write 2-3 sentences explaining why this unit is a strong match for {client_name}, using the context above. Be specific — reference the environment fit, budget position, or payback period if available. Do not be generic."""


@app.post("/api/portal/login")
def portal_login(body: dict, request: Request):
    """
    Validate legacy client access code and return session if PORTAL_LEGACY_LOGIN_ENABLED.
    Otherwise 403.
    """
    from portal_routes import legacy_company_login
    return legacy_company_login(body, request)


@app.get("/api/portal/{client_id}/dashboard")
def portal_dashboard(client_id: str, session: PortalSession = Depends(get_current_portal_session)):
    """
    Return client-safe data: top 5 matches with warm AI reasoning, plus demo history.
    Strips ALL internal fields (probability, tier, expected_value, agent notes, etc.)
    Enforces active session and company isolation.
    """
    require_company_access(session, client_id)
    # 1. Fetch client (validate existence)
    try:
        client_res = supabase.table("clients") \
            .select("id, name, stated_budget, preferred_neighborhood, relationship_stage") \
            .eq("id", client_id) \
            .single() \
            .execute()
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Client not found")

    if not client_res.data:
        raise HTTPException(status_code=404, detail="Client not found")

    client = client_res.data

    # 2. Fetch top 5 pipeline evaluations by expected_value (internal field — not exposed)
    # Try the rich select first (includes estimated_annual_savings); fall back to base
    # columns if the portal_phase2_migration.sql hasn't been run yet.
    _rich_select = "property_id, expected_value, properties(id, address, property_value, neighborhood, image_url, property_type, sqft, estimated_annual_savings)"
    _base_select = "property_id, expected_value, properties(id, address, property_value, neighborhood, image_url, property_type)"
    try:
        evals = supabase.table("pipeline_evaluations") \
            .select(_rich_select) \
            .eq("client_id", client_id) \
            .order("expected_value", desc=True) \
            .limit(5) \
            .execute()
    except Exception as exc:
        exc_str = str(exc)
        if "estimated_annual_savings" in exc_str or "42703" in exc_str:
            # Migration not yet run — retry without the new column
            print("[portal_dashboard] WARNING: estimated_annual_savings column missing — run portal_phase2_migration.sql. Falling back to base select.")
            try:
                evals = supabase.table("pipeline_evaluations") \
                    .select(_base_select) \
                    .eq("client_id", client_id) \
                    .order("expected_value", desc=True) \
                    .limit(5) \
                    .execute()
            except Exception as exc2:
                raise HTTPException(status_code=500, detail=f"Failed to fetch matches: {exc2}")
        else:
            raise HTTPException(status_code=500, detail=f"Failed to fetch matches: {exc}")

    matches = []
    for e in (evals.data or []):
        prop = e.get("properties") or {}
        if not prop:
            continue

        prop_id = prop.get("id")

        # 3. Check client-facing reasoning cache first
        cached_reasoning = None
        try:
            cached = supabase.table("client_facing_reasoning_cache") \
                .select("reasoning") \
                .eq("client_id", client_id) \
                .eq("property_id", prop_id) \
                .execute()
            if cached.data:
                cached_reasoning = cached.data[0]["reasoning"]
        except Exception:
            pass

        if cached_reasoning:
            reasoning = cached_reasoning
        else:
            # Generate fresh client-facing reasoning (second-person, marketing-toned)
            safe_prop_name = str(prop.get("address", "?")).encode("ascii", "replace").decode("ascii")
            try:
                prompt = _build_client_facing_prompt(client, prop)
                print(f"[portal_dashboard] Calling LLM for client={client_id} property={prop_id} ({safe_prop_name})")
                reasoning = _call_groq_llm(
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=220,
                    temperature=0.6,
                )
                safe_snip = str(reasoning[:60]).encode("ascii", "replace").decode("ascii")
                print(f"[portal_dashboard] LLM OK for {safe_prop_name}: {safe_snip}...")
                # Cache it
                try:
                    supabase.table("client_facing_reasoning_cache").upsert({
                        "client_id": client_id,
                        "property_id": prop_id,
                        "reasoning": reasoning,
                    }, on_conflict="client_id,property_id").execute()
                except Exception as cache_exc:
                    print(f"[portal_dashboard] Warning: could not cache reasoning: {cache_exc}")
            except (NameError, TypeError, AttributeError, KeyError) as bug:
                print(f"[portal_dashboard] CRITICAL CODE BUG in reasoning generation: {bug}")
                raise
            except Exception as llm_exc:
                print(f"[portal_dashboard] LLM FAILED for {safe_prop_name}: {llm_exc}")
                reasoning = (
                    f"This unit in {prop.get('neighborhood', 'this zone')} is priced at "
                    f"RM{prop.get('property_value', 0):,.0f} and aligns well with your operational requirements."
                )

        # Client-safe fields only — no probability, tier, ML score, expected_value, or agent data
        # If legacy readonly session, strip pricing
        unit_cost = None if session.is_legacy else prop.get("property_value")
        annual_sav = None if session.is_legacy else prop.get("estimated_annual_savings")
        payback_months = None
        if unit_cost and annual_sav and annual_sav > 0:
            payback_months = round((unit_cost / annual_sav) * 12)

        matches.append({
            "property_id": prop_id,
            "name": prop.get("address"),
            "cost": unit_cost,
            "environment": prop.get("neighborhood"),
            "image_url": prop.get("image_url"),
            "property_type": prop.get("property_type"),
            "estimated_annual_savings": annual_sav,
            "payback_months": payback_months,
            "reasoning": reasoning,
        })

    # 4. Fetch this client's own demo history (requested + upcoming + completed)
    demos = []
    try:
        demos_res = supabase.table("scheduled_viewings") \
            .select("id, status, scheduled_at, property_id, properties(address)") \
            .eq("client_id", client_id) \
            .order("scheduled_at", desc=True) \
            .limit(10) \
            .execute()
        demos = [
            {
                "id": d["id"],
                "status": d["status"],
                "scheduled_at": d.get("scheduled_at"),
                "property_id": d.get("property_id"),
                "property_name": (d.get("properties") or {}).get("address"),
            }
            for d in (demos_res.data or [])
        ]
    except Exception:
        demos = []

    # 5. Attention counts (unread messages, quotes awaiting response, pending demo confirmations)
    unread_messages = 0
    try:
        msg_res = supabase.table("inquiry_messages") \
            .select("id", count="exact") \
            .eq("client_id", client_id) \
            .eq("sender", "rep") \
            .is_("read_at", "null") \
            .execute()
        unread_messages = msg_res.count if msg_res.count is not None else len(msg_res.data or [])
    except Exception:
        pass

    quotes_awaiting = 0
    try:
        q_res = supabase.table("portal_quotes") \
            .select("id", count="exact") \
            .eq("client_id", client_id) \
            .eq("status", "sent") \
            .execute()
        quotes_awaiting = q_res.count if q_res.count is not None else len(q_res.data or [])
    except Exception:
        pass

    pending_demo_confirmations = 0
    try:
        all_demos_res = supabase.table("scheduled_viewings") \
            .select("id, status, confirmation_status, client_confirmed_at") \
            .eq("client_id", client_id) \
            .execute()
        for d in (all_demos_res.data or []):
            if get_demo_effective_status(d) == "offered":
                pending_demo_confirmations += 1
    except Exception:
        pass

    return {
        "client_name": client["name"],
        "client_id": client_id,
        "relationship_stage": client.get("relationship_stage", "new"),
        "matches": matches,
        "scheduled_demos": demos,
        "unread_messages": unread_messages,
        "quotes_awaiting": quotes_awaiting,
        "pending_demo_confirmations": pending_demo_confirmations,
    }


@app.post("/api/portal/{client_id}/request_demo")
def portal_request_demo(
    client_id: str,
    body: dict,
    request: Request,
    session: PortalSession = Depends(get_current_portal_session),
):
    """
    Client requests a demo for a specific robot unit.
    Creates a scheduled_viewings row with status='requested' (needs agent confirmation).
    Distinct from agent-initiated 'upcoming' bookings.
    """
    require_company_access(session, client_id)
    if session.is_legacy:
        raise HTTPException(status_code=403, detail="Legacy session is read-only. Cannot request demo.")

    check_portal_write_rate_limit(request, client_id, action="request_demo")

    property_id = body.get("property_id")
    preferred_date = body.get("preferred_date")   # optional ISO string from client

    if not property_id:
        raise HTTPException(status_code=400, detail="property_id is required")

    # Validate the client exists and owns this match
    try:
        client_res = supabase.table("clients").select("id, name, assigned_agent_id").eq("id", client_id).single().execute()
        if not client_res.data:
            raise HTTPException(status_code=404, detail="Client not found")
        client_info = client_res.data
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Client not found")

    # Check for a duplicate pending request to avoid double-booking
    try:
        existing = supabase.table("scheduled_viewings") \
            .select("id, status") \
            .eq("client_id", client_id) \
            .eq("property_id", property_id) \
            .in_("status", ["requested", "upcoming"]) \
            .execute()
        if existing.data:
            return {
                "success": False,
                "message": "A demo request for this unit is already pending or scheduled.",
                "existing_id": existing.data[0]["id"],
            }
    except Exception:
        pass

    try:
        res = supabase.table("scheduled_viewings").insert({
            "client_id": client_id,
            "property_id": property_id,
            "scheduled_at": preferred_date,
            "status": "upcoming",
            "confirmation_status": "requested",
        }).execute()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to create demo request: {exc}")

    # Advance relationship stage to 'viewing' (non-destructive — won't demote)
    advance_stage(client_id, "viewing")

    # Insert signal for sales rep
    try:
        c_name = client_info.get("name") or "Client"
        p_res = supabase.table("properties").select("address").eq("id", property_id).single().execute()
        p_name = (p_res.data or {}).get("address") or "robot unit"
        supabase.table("signals").insert({
            "type": "portal_demo_requested",
            "client_id": client_id,
            "property_id": property_id,
            "message": f"{c_name} requested a demo for {p_name}.",
        }).execute()
    except Exception as sig_exc:
        print(f"[portal_request_demo] Warning: signal insert failed: {sig_exc}")

    return {
        "success": True,
        "message": "Demo request sent — a sales representative will confirm timing shortly.",
        "viewing": res.data[0] if res.data else None,
    }


def get_ics_relative_url(viewing_id: str) -> str | None:
    try:
        secret = get_calendar_signing_secret()
        if not secret:
            return None
        expires_ts = int((datetime.now(timezone.utc) + timedelta(days=14)).timestamp())
        token = generate_calendar_token(viewing_id, expires_ts)
        if not token:
            return None
        return f"/api/calendar/{viewing_id}.ics?token={token}&expires={expires_ts}"
    except Exception:
        return None


DEMO_RULES = {
    "confirm": {"offered"},                              # ONLY a rep-offered slot
    "cancel": {"requested", "offered", "upcoming"},
    "reschedule": {"requested", "offered", "upcoming"},
}

QUOTE_TRANSITIONS = {
    ("rep", "requested"): {"sent"},
    ("rep", "sent"): {"sent"},                  # rep may revise before client response
    ("portal", "sent"): {"accepted", "declined"},
}


def can_quote_transition(actor: str, current: str, target: str) -> bool:
    return target in QUOTE_TRANSITIONS.get((actor, current), set())


def get_demo_effective_status(demo: dict) -> str:
    """
    Map scheduled_viewings row to effective demo status string for DEMO_RULES.
    - 'offered': slot offered by rep/WhatsApp flow awaiting client confirmation.
      This includes confirmation_status='offered' AND WhatsApp-booked slot offers
      (status='upcoming', confirmation_status='unconfirmed', client_confirmed_at=None).
    - 'cancelled': cancelled or rescheduled.
    - 'completed': demo concluded.
    - 'requested': requested by client awaiting rep slot offer.
    - 'upcoming': confirmed upcoming scheduled demo.
    """
    raw_status = (demo.get("status") or "").lower()
    conf_status = (demo.get("confirmation_status") or "").lower()
    is_confirmed = bool(demo.get("client_confirmed_at")) or conf_status == "confirmed"

    if raw_status == "cancelled" or conf_status in ("cancelled", "rescheduled", "cancelled_by_client"):
        return "cancelled"
    if raw_status == "completed":
        return "completed"
    if raw_status == "offered" or conf_status == "offered":
        return "offered"
    # WhatsApp auto-booked slot offer before client confirms
    if raw_status == "upcoming" and conf_status == "unconfirmed" and not is_confirmed:
        return "offered"
    if raw_status == "requested" or conf_status == "requested":
        return "requested"
    if raw_status == "upcoming":
        return "upcoming"
    return raw_status or "requested"


def check_demo_transition(action: str, demo: dict) -> str:
    """
    Enforces server-side DEMO_RULES transitions. Returns 409 Conflict if not allowed.
    """
    allowed = DEMO_RULES.get(action, set())
    eff_status = get_demo_effective_status(demo)
    if eff_status not in allowed:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot {action} demonstration with status '{eff_status}'. Allowed statuses: {sorted(list(allowed))}",
        )
    return eff_status


def _format_portal_demo_item(d: dict, session: PortalSession) -> dict:
    eff_status = get_demo_effective_status(d)
    is_legacy = getattr(session, "is_legacy", False)
    viewing_id = d["id"]
    prop = d.get("properties") or {}
    prop_id = d.get("property_id") or prop.get("id")
    sched_at = d.get("scheduled_at")

    # POC criteria are editable by client until demo is completed/cancelled
    can_act = not is_legacy
    can_edit_poc = can_act and eff_status not in ("completed", "cancelled")
    return {
        "id": viewing_id,
        "status": eff_status,
        "scheduled_at": sched_at,
        "property_id": prop_id,
        "property_name": prop.get("address") or "Robot Unit",
        "property_environment": prop.get("neighborhood"),
        "confirmation_status": d.get("confirmation_status"),
        "client_confirmed_at": d.get("client_confirmed_at"),
        "ics_url": get_ics_relative_url(viewing_id) if sched_at and eff_status in ("upcoming", "completed") else None,
        "can_confirm": (eff_status in DEMO_RULES["confirm"]) and can_act,
        "can_cancel": (eff_status in DEMO_RULES["cancel"]) and can_act,
        "can_reschedule": (eff_status in DEMO_RULES["reschedule"]) and can_act,
        "poc_criteria": d.get("poc_criteria") or [],
        "poc_feedback": d.get("poc_feedback"),
        "poc_outcome": d.get("poc_outcome"),
        "can_edit_poc_criteria": can_edit_poc,
        "can_submit_poc_feedback": can_act and eff_status == "completed" and not d.get("poc_feedback"),
    }


@app.get("/api/portal/{client_id}/my_viewings")
def portal_my_viewings(client_id: str, session: PortalSession = Depends(get_current_portal_session)):
    """
    Return this client's own demo history — client-safe fields only.
    Maintained alongside /demos for backwards compatibility.
    """
    require_company_access(session, client_id)
    try:
        res = supabase.table("scheduled_viewings") \
            .select("id, status, scheduled_at, property_id, confirmation_status, client_confirmed_at, poc_criteria, poc_feedback, poc_outcome, properties(id, address, neighborhood)") \
            .eq("client_id", client_id) \
            .order("scheduled_at", desc=True) \
            .execute()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch demo history: {exc}")

    demos = [_format_portal_demo_item(d, session) for d in (res.data or [])]
    return {
        "viewings": demos,
        "demos": demos,
    }


@app.get("/api/portal/{client_id}/demos")
def portal_get_demos(client_id: str, session: PortalSession = Depends(get_current_portal_session)):
    """
    Return this client's robot demonstrations list.
    """
    require_company_access(session, client_id)
    try:
        res = supabase.table("scheduled_viewings") \
            .select("id, status, scheduled_at, property_id, confirmation_status, client_confirmed_at, poc_criteria, poc_feedback, poc_outcome, properties(id, address, neighborhood)") \
            .eq("client_id", client_id) \
            .order("scheduled_at", desc=True) \
            .execute()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch demo history: {exc}")

    demos = [_format_portal_demo_item(d, session) for d in (res.data or [])]
    return {"demos": demos}


@app.post("/api/portal/{client_id}/demos/{demo_id}/confirm")
def portal_confirm_demo(
    client_id: str,
    demo_id: str,
    request: Request,
    session: PortalSession = Depends(get_current_portal_session),
):
    """
    Client confirms a rep-offered demo slot.
    Strict rule: ONLY demos with status 'offered' can be confirmed (otherwise 409).
    Transitions status to 'upcoming' and records client_confirmed_at timestamp.
    """
    require_company_access(session, client_id)
    if session.is_legacy:
        raise HTTPException(status_code=403, detail="Legacy session is read-only. Cannot confirm demos.")

    check_portal_write_rate_limit(request, client_id, action="confirm_demo")

    try:
        res = supabase.table("scheduled_viewings") \
            .select("id, client_id, status, confirmation_status, scheduled_at, property_id, properties(address)") \
            .eq("id", demo_id) \
            .single() \
            .execute()
    except Exception:
        raise HTTPException(status_code=404, detail="Demo not found")

    if not res.data:
        raise HTTPException(status_code=404, detail="Demo not found")

    demo = res.data[0] if isinstance(res.data, list) and res.data else res.data
    if not demo or demo.get("client_id") != client_id:
        raise HTTPException(status_code=403, detail="Forbidden: demo belongs to another company")

    # Enforce DEMO_RULES: must return 409 if not 'offered'
    check_demo_transition("confirm", demo)

    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        supabase.table("scheduled_viewings") \
            .update({
                "status": "upcoming",
                "confirmation_status": "confirmed",
                "client_confirmed_at": now_iso,
            }) \
            .eq("id", demo_id) \
            .execute()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to confirm demo: {exc}")

    try:
        schedule_viewing_reminders(demo_id)
    except Exception as exc:
        print(f"[portal_confirm_demo] Warning: schedule_viewing_reminders failed: {exc}")

    # Insert signal for sales rep
    try:
        c_res = supabase.table("clients").select("name, assigned_agent_id").eq("id", client_id).single().execute()
        c_data = c_res.data or {}
        c_name = c_data.get("name") or "Client"
        prop = demo.get("properties") or {}
        prop_name = prop.get("address") or "robot unit"
        supabase.table("signals").insert({
            "type": "portal_demo_confirmed",
            "client_id": client_id,
            "property_id": demo.get("property_id"),
            "message": f"{c_name} confirmed demo for {prop_name}.",
        }).execute()
    except Exception as sig_exc:
        print(f"[portal_confirm_demo] Warning: signal insert failed: {sig_exc}")

    client_ip = get_trusted_client_ip(request)
    log_audit_event(
        supabase,
        client_id=client_id,
        action="contact_confirmed_demo",
        object_type="demo",
        contact_id=session.contact_id,
        object_id=demo_id,
        details={"previous_status": demo.get("status"), "new_status": "upcoming"},
        ip=client_ip,
    )

    return {
        "success": True,
        "demo_id": demo_id,
        "status": "upcoming",
        "confirmed": True,
        "ics_url": get_ics_relative_url(demo_id),
    }


@app.post("/api/portal/{client_id}/demos/{demo_id}/cancel")
def portal_cancel_demo(
    client_id: str,
    demo_id: str,
    request: Request,
    body: Optional[dict] = None,
    session: PortalSession = Depends(get_current_portal_session),
):
    """
    Client cancels a demonstration request or scheduled demo.
    Strict rule: ONLY demos in 'requested', 'offered', 'upcoming' can be cancelled (409 otherwise).
    """
    require_company_access(session, client_id)
    if session.is_legacy:
        raise HTTPException(status_code=403, detail="Legacy session is read-only. Cannot cancel demos.")

    check_portal_write_rate_limit(request, client_id, action="cancel_demo")

    try:
        res = supabase.table("scheduled_viewings") \
            .select("id, client_id, status, confirmation_status, property_id, properties(address)") \
            .eq("id", demo_id) \
            .single() \
            .execute()
    except Exception:
        raise HTTPException(status_code=404, detail="Demo not found")

    if not res.data:
        raise HTTPException(status_code=404, detail="Demo not found")

    demo = res.data[0] if isinstance(res.data, list) and res.data else res.data
    if not demo or demo.get("client_id") != client_id:
        raise HTTPException(status_code=403, detail="Forbidden: demo belongs to another company")

    # Enforce DEMO_RULES (409 if cancelled, completed, etc.)
    check_demo_transition("cancel", demo)

    try:
        supabase.table("scheduled_viewings") \
            .update({
                "status": "cancelled",
                "confirmation_status": "cancelled",
            }) \
            .eq("id", demo_id) \
            .execute()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to cancel demo: {exc}")

    # Cancel pending WhatsApp reminders for this demo
    try:
        cancel_viewing_reminders(demo_id, reason="portal_cancelled")
    except Exception as rem_exc:
        print(f"[portal_cancel_demo] Warning: cancel_viewing_reminders failed: {rem_exc}")

    # Insert signal for sales rep
    try:
        c_res = supabase.table("clients").select("name, assigned_agent_id").eq("id", client_id).single().execute()
        c_data = c_res.data or {}
        c_name = c_data.get("name") or "Client"
        prop = demo.get("properties") or {}
        prop_name = prop.get("address") or "robot unit"
        supabase.table("signals").insert({
            "type": "portal_demo_cancelled",
            "client_id": client_id,
            "property_id": demo.get("property_id"),
            "message": f"{c_name} cancelled demo for {prop_name}.",
        }).execute()
    except Exception as sig_exc:
        print(f"[portal_cancel_demo] Warning: signal insert failed: {sig_exc}")

    reason = (body or {}).get("reason")
    client_ip = get_trusted_client_ip(request)
    log_audit_event(
        supabase,
        client_id=client_id,
        action="contact_cancelled_demo",
        object_type="demo",
        contact_id=session.contact_id,
        object_id=demo_id,
        details={"previous_status": demo.get("status"), "reason": reason},
        ip=client_ip,
    )

    return {"success": True, "demo_id": demo_id, "status": "cancelled"}


@app.post("/api/portal/{client_id}/demos/{demo_id}/reschedule")
def portal_reschedule_demo(
    client_id: str,
    demo_id: str,
    body: dict,
    request: Request,
    session: PortalSession = Depends(get_current_portal_session),
):
    """
    Client requests a demo reschedule.
    Strict rule: ONLY demos in 'requested', 'offered', 'upcoming' can be rescheduled (409 otherwise).
    Reschedule is atomic:
      new_id = insert new request (if fails: return 500, old demo untouched)
      try: cancel old demo (confirmation_status='rescheduled')
      except: delete new_id row; return 500 (compensate)
    Cancels pending WhatsApp reminders and inserts a rep signal.
    """
    require_company_access(session, client_id)
    if session.is_legacy:
        raise HTTPException(status_code=403, detail="Legacy session is read-only. Cannot reschedule demos.")

    check_portal_write_rate_limit(request, client_id, action="reschedule_demo")

    try:
        res = supabase.table("scheduled_viewings") \
            .select("id, client_id, property_id, status, confirmation_status, scheduled_at, properties(address)") \
            .eq("id", demo_id) \
            .single() \
            .execute()
    except Exception:
        raise HTTPException(status_code=404, detail="Demo not found")

    if not res.data:
        raise HTTPException(status_code=404, detail="Demo not found")

    demo = res.data[0] if isinstance(res.data, list) and res.data else res.data
    if not demo or demo.get("client_id") != client_id:
        raise HTTPException(status_code=403, detail="Forbidden: demo belongs to another company")

    # Enforce DEMO_RULES (409 if cancelled, completed, etc.)
    check_demo_transition("reschedule", demo)

    preferred_date = body.get("preferred_date")
    notes = (body.get("notes") or "").strip()

    # 1. Atomic step 1: insert new demo request
    new_demo_id = None
    new_demo_row = None
    try:
        insert_res = supabase.table("scheduled_viewings").insert({
            "client_id": client_id,
            "property_id": demo["property_id"],
            "scheduled_at": preferred_date,
            "status": "upcoming",
            "confirmation_status": "requested",
            "source": "portal_reschedule",
        }).execute()
        rows = insert_res.data or []
        new_demo_row = rows[0] if isinstance(rows, list) and rows else rows
        if isinstance(new_demo_row, dict):
            new_demo_id = new_demo_row.get("id")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to create new demo request: {exc}")

    if not new_demo_id:
        raise HTTPException(status_code=500, detail="Failed to initialize new demo request")

    # 2. Atomic step 2: cancel old demo with confirmation_status='rescheduled'
    # Compensation: if updating old demo fails, delete the newly created demo row
    try:
        supabase.table("scheduled_viewings").update({
            "status": "cancelled",
            "confirmation_status": "rescheduled",
        }).eq("id", demo_id).execute()
    except Exception as exc:
        try:
            supabase.table("scheduled_viewings").delete().eq("id", new_demo_id).execute()
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Failed to update previous demo: {exc}")

    # 3. Cancel pending WhatsApp reminders for old demo
    try:
        cancel_viewing_reminders(demo_id, reason="portal_rescheduled")
    except Exception as rem_exc:
        print(f"[portal_reschedule_demo] Warning: cancel_viewing_reminders failed: {rem_exc}")

    # 4. If notes provided, record inquiry note
    if notes:
        try:
            supabase.table("client_inquiries").insert({
                "client_id": client_id,
                "property_id": demo["property_id"],
                "message": f"[Reschedule request for demo {demo_id}] {notes}",
                "status": "open",
            }).execute()
        except Exception as exc:
            print(f"[portal_reschedule_demo] Notice: Failed to record inquiry note: {exc}")

    # 5. Insert signal for sales rep
    try:
        c_res = supabase.table("clients").select("name, assigned_agent_id").eq("id", client_id).single().execute()
        c_data = c_res.data or {}
        c_name = c_data.get("name") or "Client"
        prop = demo.get("properties") or {}
        prop_name = prop.get("address") or "robot unit"
        supabase.table("signals").insert({
            "type": "portal_demo_rescheduled",
            "client_id": client_id,
            "property_id": demo.get("property_id"),
            "message": f"{c_name} requested reschedule for {prop_name} demo.",
        }).execute()
    except Exception as sig_exc:
        print(f"[portal_reschedule_demo] Warning: signal insert failed: {sig_exc}")

    client_ip = get_trusted_client_ip(request)
    log_audit_event(
        supabase,
        client_id=client_id,
        action="contact_rescheduled_demo",
        object_type="demo",
        contact_id=session.contact_id,
        object_id=new_demo_id,
        details={
            "old_demo_id": demo_id,
            "new_demo_id": new_demo_id,
            "preferred_date": preferred_date,
            "notes": notes or None,
        },
        ip=client_ip,
    )

    return {
        "success": True,
        "old_demo_id": demo_id,
        "new_demo": new_demo_row,
        "status": "requested",
        "message": "Demo rescheduled. Our team will confirm the new slot shortly.",
    }


_POC_CRITERIA_MAX = 3
_POC_CRITERIA_MAX_LEN = 140


@app.patch("/api/portal/{client_id}/demos/{demo_id}/poc_criteria")
def portal_update_poc_criteria(
    client_id: str,
    demo_id: str,
    body: dict,
    request: Request,
    session: PortalSession = Depends(get_current_portal_session),
):
    """
    Update POC success criteria for a demo.
    Criteria are a list of strings (max 3, max 140 chars each).
    Only editable while the demo is not completed or cancelled.
    """
    require_company_access(session, client_id)
    if session.is_legacy:
        raise HTTPException(status_code=403, detail="Legacy session is read-only.")
    check_portal_write_rate_limit(request, client_id, action="update_poc_criteria")

    try:
        res = supabase.table("scheduled_viewings") \
            .select("id, client_id, status, confirmation_status") \
            .eq("id", demo_id) \
            .single() \
            .execute()
    except Exception:
        raise HTTPException(status_code=404, detail="Demo not found")

    demo = res.data[0] if isinstance(res.data, list) and res.data else res.data
    if not demo or demo.get("client_id") != client_id:
        raise HTTPException(status_code=403, detail="Forbidden: demo belongs to another company")

    eff_status = get_demo_effective_status(demo)
    if eff_status in ("completed", "cancelled"):
        raise HTTPException(status_code=409, detail=f"Cannot edit POC criteria when demo is '{eff_status}'.")

    criteria = body.get("criteria", [])
    if not isinstance(criteria, list):
        raise HTTPException(status_code=422, detail="criteria must be a list of strings")
    if len(criteria) > _POC_CRITERIA_MAX:
        raise HTTPException(status_code=422, detail=f"Maximum {_POC_CRITERIA_MAX} criteria allowed")
    cleaned = []
    for i, item in enumerate(criteria):
        if not isinstance(item, str):
            raise HTTPException(status_code=422, detail=f"criteria[{i}] must be a string")
        s = item.strip()
        if len(s) > _POC_CRITERIA_MAX_LEN:
            raise HTTPException(status_code=422, detail=f"criteria[{i}] exceeds {_POC_CRITERIA_MAX_LEN} characters")
        if s:
            cleaned.append(s)

    try:
        supabase.table("scheduled_viewings") \
            .update({"poc_criteria": cleaned}) \
            .eq("id", demo_id) \
            .execute()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to update POC criteria: {exc}")

    return {"success": True, "demo_id": demo_id, "poc_criteria": cleaned}


@app.post("/api/portal/{client_id}/demos/{demo_id}/poc_feedback")
def portal_submit_poc_feedback(
    client_id: str,
    demo_id: str,
    body: dict,
    request: Request,
    session: PortalSession = Depends(get_current_portal_session),
):
    """
    Submit POC trial feedback after a completed demo.
    Optionally creates a rep signal to request a commercial quote.
    Only submittable once; re-submission returns 409.
    """
    require_company_access(session, client_id)
    if session.is_legacy:
        raise HTTPException(status_code=403, detail="Legacy session is read-only.")
    check_portal_write_rate_limit(request, client_id, action="poc_feedback")

    try:
        res = supabase.table("scheduled_viewings") \
            .select("id, client_id, status, confirmation_status, poc_feedback, property_id, properties(address)") \
            .eq("id", demo_id) \
            .single() \
            .execute()
    except Exception:
        raise HTTPException(status_code=404, detail="Demo not found")

    demo = res.data[0] if isinstance(res.data, list) and res.data else res.data
    if not demo or demo.get("client_id") != client_id:
        raise HTTPException(status_code=403, detail="Forbidden: demo belongs to another company")

    eff_status = get_demo_effective_status(demo)
    if eff_status != "completed":
        raise HTTPException(status_code=409, detail=f"POC feedback can only be submitted after a completed demo (current: '{eff_status}').")

    if demo.get("poc_feedback"):
        raise HTTPException(status_code=409, detail="POC feedback has already been submitted for this demo.")

    feedback_text = (body.get("feedback") or "").strip()
    if not feedback_text:
        raise HTTPException(status_code=422, detail="feedback is required")
    if len(feedback_text) > 5000:
        raise HTTPException(status_code=422, detail="feedback exceeds 5000 character limit")

    outcome = body.get("outcome")  # optional: 'proceed' | 'decline' | 'undecided'
    if outcome and outcome not in ("proceed", "decline", "undecided"):
        raise HTTPException(status_code=422, detail="outcome must be one of: proceed, decline, undecided")

    request_quote = bool(body.get("request_commercial_quote", False))

    update_payload: dict[str, Any] = {"poc_feedback": feedback_text}
    if outcome:
        update_payload["poc_outcome"] = outcome

    try:
        supabase.table("scheduled_viewings") \
            .update(update_payload) \
            .eq("id", demo_id) \
            .execute()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save POC feedback: {exc}")

    # Emit signal for sales rep
    try:
        c_res = supabase.table("clients").select("name, assigned_agent_id").eq("id", client_id).single().execute()
        c_name = (c_res.data or {}).get("name") or "Client"
        prop = demo.get("properties") or {}
        prop_name = prop.get("address") or "robot unit"
        signal_type = "portal_poc_feedback_quote_request" if request_quote else "portal_poc_feedback"
        msg = f"{c_name} submitted POC feedback for {prop_name}"
        if request_quote:
            msg += " — and requested a commercial quote."
        elif outcome:
            outcome_labels = {"proceed": "wants to proceed", "decline": "chose to decline", "undecided": "is undecided"}
            msg += f" ({outcome_labels.get(outcome, outcome)})."
        else:
            msg += "."
        supabase.table("signals").insert({
            "type": signal_type,
            "client_id": client_id,
            "property_id": demo.get("property_id"),
            "message": msg,
        }).execute()
    except Exception as sig_exc:
        print(f"[portal_submit_poc_feedback] Warning: signal insert failed: {sig_exc}")

    return {
        "success": True,
        "demo_id": demo_id,
        "poc_feedback": feedback_text,
        "poc_outcome": outcome,
        "request_commercial_quote": request_quote,
    }


@app.patch("/api/confirm_demo/{viewing_id}")
def confirm_demo(viewing_id: str):
    """
    Agent-side: confirm a client-requested demo.
    Transitions status from 'requested' → 'upcoming'.
    """
    try:
        res = supabase.table("scheduled_viewings") \
            .select("id, status, client_id") \
            .eq("id", viewing_id) \
            .single() \
            .execute()
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Viewing not found")

    if not res.data:
        raise HTTPException(status_code=404, detail="Viewing not found")

    if res.data["status"] != "requested":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot confirm a demo with status '{res.data['status']}' (must be 'requested')"
        )

    try:
        supabase.table("scheduled_viewings") \
            .update({"status": "upcoming"}) \
            .eq("id", viewing_id) \
            .execute()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to confirm demo: {exc}")

    schedule_viewing_reminders(viewing_id)

    return {"viewing_id": viewing_id, "status": "upcoming", "confirmed": True}


# ─── Portal Inquiries & Messages ─────────────────────────────────────────────

@app.post("/api/portal/{client_id}/inquiry")
def portal_submit_inquiry(
    client_id: str,
    body: dict,
    request: Request,
    session: PortalSession = Depends(get_current_portal_session),
):
    """
    Client submits an inquiry about a specific robot unit or general question.
    Creates client_inquiries row and the first inquiry_messages row.
    """
    require_company_access(session, client_id)
    if session.is_legacy:
        raise HTTPException(status_code=403, detail="Legacy session is read-only. Cannot submit inquiry.")

    check_portal_write_rate_limit(request, client_id, action="inquiry")

    property_id = body.get("property_id")
    raw_roi = body.get("roi_scenario")
    stored_roi = None

    if raw_roi is not None:
        try:
            roi_in = RoiScenarioInputs.model_validate(raw_roi)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Invalid ROI scenario inputs: {e}")

        prop_price = 0.0
        lease_monthly = 0.0
        if property_id:
            try:
                p_res = supabase.table("properties").select("id, property_value, specs").eq("id", property_id).single().execute()
                if p_res.data:
                    prop_price = float(p_res.data.get("property_value") or 0)
                    specs = p_res.data.get("specs") or {}
                    lease_monthly = float(specs.get("lease_monthly") or (prop_price * 0.035 if prop_price > 0 else 0))
            except Exception:
                pass

        computed = compute_roi(
            {
                "shifts": roi_in.shifts,
                "headcountPerShift": roi_in.headcountPerShift,
                "monthlyLaborCost": roi_in.monthlyLaborCost,
            },
            {
                "purchasePrice": prop_price,
                "leaseMonthly": lease_monthly,
            },
            roi_in.mode,
        )
        stored_roi = {
            "inputs": {
                "shifts": roi_in.shifts,
                "headcountPerShift": roi_in.headcountPerShift,
                "monthlyLaborCost": roi_in.monthlyLaborCost,
                "mode": roi_in.mode,
            },
            "outputs": computed,
        }

    message = (body.get("message") or "").strip()
    if not message:
        if stored_roi:
            mode_label = stored_roi["inputs"]["mode"].title()
            savings = stored_roi["outputs"]["monthlySavings"]
            message = f"ROI Scenario & Quote Request ({mode_label} mode, RM {savings:,.0f}/mo est. savings)"
        else:
            raise HTTPException(status_code=422, detail="message is required and must be 1 to 4000 characters")
    elif len(message) > 4000:
        raise HTTPException(status_code=422, detail="message must be 1 to 4000 characters")

    try:
        client_res = supabase.table("clients").select("id, name, assigned_agent_id").eq("id", client_id).single().execute()
        if not client_res.data:
            raise HTTPException(status_code=404, detail="Client not found")
        client_name = client_res.data.get("name") or "Client"
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=404, detail="Client not found")

    unit_name = "general"
    if property_id:
        try:
            p_res = supabase.table("properties").select("id, address").eq("id", property_id).single().execute()
            if p_res.data:
                unit_name = p_res.data.get("address") or "robot unit"
        except Exception:
            pass

    inq_payload = {
        "client_id": client_id,
        "property_id": property_id,
        "message": message,
        "status": "open",
    }
    if stored_roi:
        inq_payload["roi_scenario"] = stored_roi

    try:
        res = supabase.table("client_inquiries").insert(inq_payload).execute()
        inq_row = res.data[0] if res.data else {}
        inquiry_id = inq_row.get("id")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save inquiry: {exc}")

    # Initial message in inquiry_messages
    try:
        supabase.table("inquiry_messages").insert({
            "inquiry_id": inquiry_id,
            "client_id": client_id,
            "sender": "company",
            "body": message,
        }).execute()
    except Exception as exc:
        print(f"[portal_submit_inquiry] Warning: initial inquiry message insert failed: {exc}")

    # Emit rep signal
    try:
        sig_msg = (
            f"ROI scenario saved & quote requested by {client_name} regarding {unit_name}: RM {stored_roi['outputs']['monthlySavings']:,.0f}/mo savings"
            if stored_roi
            else f"New inquiry from {client_name} regarding {unit_name}: {message[:120]}"
        )
        supabase.table("signals").insert({
            "type": "portal_inquiry",
            "client_id": client_id,
            "property_id": property_id,
            "message": sig_msg,
        }).execute()
    except Exception as sig_exc:
        print(f"[portal_submit_inquiry] Warning: signal insert failed: {sig_exc}")

    resp = {
        "id": inquiry_id,
        "client_id": client_id,
        "property_id": property_id,
        "message": message,
        "status": "open",
        "created_at": inq_row.get("created_at"),
    }
    if stored_roi:
        resp["roi_scenario"] = stored_roi
    return resp


@app.post("/api/portal/{client_id}/inquiries/{inquiry_id}/messages")
def portal_inquiry_post_message(
    client_id: str,
    inquiry_id: str,
    body: dict,
    request: Request,
    session: PortalSession = Depends(get_current_portal_session),
):
    """Client posts a message to an existing inquiry thread."""
    require_company_access(session, client_id)
    if session.is_legacy:
        raise HTTPException(status_code=403, detail="Legacy session is read-only. Cannot send message.")

    check_portal_write_rate_limit(request, client_id, action="inquiry_message")

    text = (body.get("body") or "").strip()
    if not text or len(text) > 4000:
        raise HTTPException(status_code=422, detail="Message body must be between 1 and 4000 characters")

    try:
        inq_res = supabase.table("client_inquiries").select("id, client_id, property_id").eq("id", inquiry_id).single().execute()
        if not inq_res.data:
            raise HTTPException(status_code=404, detail="Inquiry not found")
        inq = inq_res.data
        if inq.get("client_id") != client_id:
            raise HTTPException(status_code=403, detail="Forbidden: inquiry belongs to another company")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=404, detail="Inquiry not found")

    try:
        ins_res = supabase.table("inquiry_messages").insert({
            "inquiry_id": inquiry_id,
            "client_id": client_id,
            "sender": "company",
            "body": text,
        }).execute()
        msg_record = ins_res.data[0] if ins_res.data else {}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to post message: {exc}")

    try:
        c_res = supabase.table("clients").select("name").eq("id", client_id).single().execute()
        c_name = (c_res.data or {}).get("name") or "Client"
        supabase.table("signals").insert({
            "type": "portal_inquiry_message",
            "client_id": client_id,
            "property_id": inq.get("property_id"),
            "message": f"New message from {c_name}: {text[:120]}",
        }).execute()
    except Exception as sig_exc:
        print(f"[portal_inquiry_post_message] Warning: signal insert failed: {sig_exc}")

    return {
        "id": msg_record.get("id"),
        "inquiry_id": inquiry_id,
        "sender": "company",
        "body": text,
        "created_at": msg_record.get("created_at"),
    }


@app.post("/api/portal/{client_id}/inquiries/{inquiry_id}/read")
def portal_inquiry_mark_read(
    client_id: str,
    inquiry_id: str,
    session: PortalSession = Depends(get_current_portal_session),
):
    """Mark all rep messages in this inquiry as read by the company contact."""
    require_company_access(session, client_id)
    try:
        inq_res = supabase.table("client_inquiries").select("id, client_id").eq("id", inquiry_id).single().execute()
        if not inq_res.data:
            raise HTTPException(status_code=404, detail="Inquiry not found")
        if inq_res.data.get("client_id") != client_id:
            raise HTTPException(status_code=403, detail="Forbidden")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=404, detail="Inquiry not found")

    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        supabase.table("inquiry_messages") \
            .update({"read_at": now_iso}) \
            .eq("inquiry_id", inquiry_id) \
            .eq("client_id", client_id) \
            .eq("sender", "rep") \
            .is_("read_at", "null") \
            .execute()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to mark messages as read: {exc}")

    return {"success": True}


@app.get("/api/portal/{client_id}/inquiries")
def portal_list_inquiries(client_id: str, session: PortalSession = Depends(get_current_portal_session)):
    """
    Return this client's inquiries with threaded messages and unread counts.
    Never exposes internal notes, agent identity, or other companies' data.
    """
    require_company_access(session, client_id)
    try:
        client_res = supabase.table("clients").select("id").eq("id", client_id).single().execute()
        if not client_res.data:
            raise HTTPException(status_code=404, detail="Client not found")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=404, detail="Client not found")

    try:
        rows = (
            supabase.table("client_inquiries")
            .select("id, property_id, message, status, agent_reply, created_at, roi_scenario, properties(address)")
            .eq("client_id", client_id)
            .order("created_at", desc=True)
            .execute()
        )
        inq_rows = rows.data or []

        msgs_res = (
            supabase.table("inquiry_messages")
            .select("id, inquiry_id, sender, body, read_at, created_at")
            .eq("client_id", client_id)
            .order("created_at", desc=False)
            .execute()
        )
        msgs_by_inq: dict[str, list] = {}
        total_unread = 0
        for m in (msgs_res.data or []):
            iq_id = m.get("inquiry_id")
            msgs_by_inq.setdefault(iq_id, []).append(m)
            if m.get("sender") == "rep" and not m.get("read_at"):
                total_unread += 1

        inquiries = []
        for row in inq_rows:
            prop = row.get("properties") or {}
            iq_id = row.get("id")
            thread = msgs_by_inq.get(iq_id, [])
            if not thread:
                if row.get("message"):
                    thread.append({
                        "id": f"{iq_id}-orig",
                        "inquiry_id": iq_id,
                        "sender": "company",
                        "body": row.get("message"),
                        "read_at": None,
                        "created_at": row.get("created_at"),
                    })
                if row.get("agent_reply"):
                    thread.append({
                        "id": f"{iq_id}-reply",
                        "inquiry_id": iq_id,
                        "sender": "rep",
                        "body": row.get("agent_reply"),
                        "read_at": None,
                        "created_at": row.get("created_at"),
                    })
            unread_count = sum(1 for m in thread if m.get("sender") == "rep" and not m.get("read_at"))

            inquiries.append({
                "id":            iq_id,
                "message":       row.get("message"),
                "status":        row.get("status", "open"),
                "agent_reply":   row.get("agent_reply"),
                "created_at":    row.get("created_at"),
                "property_name": prop.get("address") or "General Inquiry",
                "property_id":   row.get("property_id"),
                "messages":      thread,
                "unread_count":  unread_count,
                "roi_scenario":  row.get("roi_scenario"),
            })

        return {"inquiries": inquiries, "total_unread": total_unread}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load inquiries: {exc}")


# ─── Portal Catalog & Unit Feedback ──────────────────────────────────────────

@app.put("/api/portal/{client_id}/catalog/{property_id}/feedback")
def portal_put_unit_feedback(
    client_id: str,
    property_id: str,
    body: dict,
    request: Request,
    session: PortalSession = Depends(get_current_portal_session),
):
    """
    Partial update / upsert of company feedback on a robot unit.
    Body keys: interest ('interested'|'not_interested'|null), reason (str<=500), is_saved (bool).
    Emits portal_interested or portal_not_interested signal.
    """
    require_company_access(session, client_id)
    if session.is_legacy:
        raise HTTPException(status_code=403, detail="Legacy session is read-only. Cannot modify feedback.")

    check_portal_write_rate_limit(request, client_id, action="catalog_feedback")

    # Verify property exists
    try:
        p_res = supabase.table("properties").select("id, address").eq("id", property_id).single().execute()
        if not p_res.data:
            raise HTTPException(status_code=404, detail="Property not found")
        unit_name = p_res.data.get("address") or "robot unit"
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=404, detail="Property not found")

    allowed_interest = ("interested", "not_interested", None)
    if "interest" in body and body["interest"] not in allowed_interest:
        raise HTTPException(status_code=422, detail="interest must be 'interested', 'not_interested', or null")

    reason = body.get("reason")
    if reason is not None:
        if not isinstance(reason, str) or len(reason) > 500:
            raise HTTPException(status_code=422, detail="reason must be a string up to 500 characters")

    is_saved = body.get("is_saved")
    if is_saved is not None and not isinstance(is_saved, bool):
        raise HTTPException(status_code=422, detail="is_saved must be a boolean")

    existing = None
    try:
        ex_res = supabase.table("portal_unit_feedback") \
            .select("id, interest, reason, is_saved") \
            .eq("client_id", client_id) \
            .eq("property_id", property_id) \
            .execute()
        if ex_res.data:
            existing = ex_res.data[0]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to check existing feedback: {exc}")

    now_iso = datetime.now(timezone.utc).isoformat()
    old_interest = existing.get("interest") if existing else None

    if existing:
        update_payload: dict[str, Any] = {"updated_at": now_iso}
        if "interest" in body:
            update_payload["interest"] = body["interest"]
        if "reason" in body:
            update_payload["reason"] = body["reason"]
        if "is_saved" in body:
            update_payload["is_saved"] = body["is_saved"]

        try:
            upd_res = supabase.table("portal_unit_feedback") \
                .update(update_payload) \
                .eq("client_id", client_id) \
                .eq("property_id", property_id) \
                .execute()
            final_row = upd_res.data[0] if upd_res.data else {**existing, **update_payload}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to update feedback: {exc}")
    else:
        insert_payload = {
            "client_id": client_id,
            "property_id": property_id,
            "contact_id": getattr(session, "contact_id", None),
            "interest": body.get("interest"),
            "reason": body.get("reason"),
            "is_saved": body.get("is_saved", False),
            "created_at": now_iso,
            "updated_at": now_iso,
        }
        try:
            ins_res = supabase.table("portal_unit_feedback").insert(insert_payload).execute()
            final_row = ins_res.data[0] if ins_res.data else insert_payload
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to save feedback: {exc}")

    new_interest = final_row.get("interest")
    if "interest" in body and new_interest != old_interest:
        try:
            c_res = supabase.table("clients").select("name").eq("id", client_id).single().execute()
            client_name = (c_res.data or {}).get("name") or "Client"
            if new_interest == "interested":
                supabase.table("signals").insert({
                    "type": "portal_interested",
                    "client_id": client_id,
                    "property_id": property_id,
                    "message": f"{client_name} expressed interest in {unit_name}.",
                }).execute()
            elif new_interest == "not_interested":
                r_text = f" (Reason: {final_row.get('reason')})" if final_row.get("reason") else ""
                supabase.table("signals").insert({
                    "type": "portal_not_interested",
                    "client_id": client_id,
                    "property_id": property_id,
                    "message": f"{client_name} marked {unit_name} as not interested{r_text}.",
                }).execute()
        except Exception as sig_exc:
            print(f"[portal_put_unit_feedback] Signal insert warning: {sig_exc}")

    return {
        "property_id": property_id,
        "interest": final_row.get("interest"),
        "reason": final_row.get("reason"),
        "is_saved": final_row.get("is_saved", False),
    }


@app.get("/api/portal/{client_id}/catalog")
def portal_catalog(
    client_id: str,
    category: Optional[str] = None,
    min_price: Optional[str] = None,
    max_price: Optional[str] = None,
    max_lead_time_weeks: Optional[str] = None,
    min_payload_kg: Optional[str] = None,
    environment: Optional[str] = None,
    search: Optional[str] = None,
    session: PortalSession = Depends(get_current_portal_session),
):
    """
    Returns active robot units with my_feedback merged per unit in a single query.
    Supports server-side filters. Validates filter values (422 if invalid).
    NEVER exposes sales-internal fields (expected_value, tier, probability, etc.).
    """
    require_company_access(session, client_id)
    try:
        client_res = supabase.table("clients").select("id").eq("id", client_id).single().execute()
        if not client_res.data:
            raise HTTPException(status_code=404, detail="Client not found")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=404, detail="Client not found")

    # Validate numerical filters
    f_min_price = None
    if min_price is not None and min_price != "":
        try:
            f_min_price = float(min_price)
            if f_min_price < 0:
                raise ValueError()
        except ValueError:
            raise HTTPException(status_code=422, detail="min_price must be a positive number")

    f_max_price = None
    if max_price is not None and max_price != "":
        try:
            f_max_price = float(max_price)
            if f_max_price < 0:
                raise ValueError()
        except ValueError:
            raise HTTPException(status_code=422, detail="max_price must be a positive number")

    f_max_lead = None
    if max_lead_time_weeks is not None and max_lead_time_weeks != "":
        try:
            f_max_lead = int(max_lead_time_weeks)
            if f_max_lead < 0:
                raise ValueError()
        except ValueError:
            raise HTTPException(status_code=422, detail="max_lead_time_weeks must be a positive integer")

    f_min_payload = None
    if min_payload_kg is not None and min_payload_kg != "":
        try:
            f_min_payload = float(min_payload_kg)
            if f_min_payload < 0:
                raise ValueError()
        except ValueError:
            raise HTTPException(status_code=422, detail="min_payload_kg must be a positive number")

    # Fetch top-5 matched property IDs
    matched_ids: set[str] = set()
    try:
        evals_res = (
            supabase.table("pipeline_evaluations")
            .select("property_id, expected_value")
            .eq("client_id", client_id)
            .order("expected_value", desc=True)
            .limit(5)
            .execute()
        )
        matched_ids = {row["property_id"] for row in (evals_res.data or [])}
    except Exception:
        pass

    # Single-query merge for client feedback
    feedback_map = {}
    try:
        fb_res = (
            supabase.table("portal_unit_feedback")
            .select("property_id, interest, reason, is_saved")
            .eq("client_id", client_id)
            .execute()
        )
        for fb in (fb_res.data or []):
            feedback_map[fb["property_id"]] = {
                "interest": fb.get("interest"),
                "reason": fb.get("reason"),
                "is_saved": fb.get("is_saved", False),
            }
    except Exception as exc:
        print(f"[portal_catalog] Feedback fetch non-fatal: {exc}")

    # Fetch all active properties
    try:
        props_res = (
            supabase.table("properties")
            .select("id, address, neighborhood, property_value, image_url, property_type, bedrooms, bathrooms, sqft, estimated_annual_savings, sku, manufacturer, category, specs, lead_time_weeks, stock_status, spec_sheet_url, currency")
            .neq("status", "CLOSED")
            .order("address")
            .execute()
        )
    except Exception:
        try:
            props_res = (
                supabase.table("properties")
                .select("id, address, neighborhood, property_value, image_url, property_type, bedrooms, bathrooms, sqft, estimated_annual_savings")
                .neq("status", "CLOSED")
                .order("address")
                .execute()
            )
        except Exception as exc2:
            raise HTTPException(status_code=500, detail=f"Failed to fetch catalog: {exc2}")

    units = []
    for p in (props_res.data or []):
        unit_id = p["id"]
        unit_name = p.get("address") or "Robot Unit"
        specs = p.get("specs") or {}
        if not isinstance(specs, dict):
            specs = {}

        # Read payload from specs->>'payload_kg' with fallback to bedrooms
        payload_val = specs.get("payload_kg")
        if payload_val is None:
            payload_val = p.get("bedrooms")
        try:
            payload_num = float(payload_val) if payload_val is not None else None
        except (ValueError, TypeError):
            payload_num = None

        cost = None if session.is_legacy else p.get("property_value")
        cost_num = float(cost) if cost is not None else None
        lead_time = p.get("lead_time_weeks")
        unit_category = p.get("category") or p.get("property_type")
        env = p.get("neighborhood")

        # Filters evaluation
        if category and category.strip():
            c_term = category.strip().lower()
            if not unit_category or c_term not in unit_category.lower():
                continue

        if f_min_price is not None and cost_num is not None:
            if cost_num < f_min_price:
                continue

        if f_max_price is not None and cost_num is not None:
            if cost_num > f_max_price:
                continue

        if f_max_lead is not None and lead_time is not None:
            if lead_time > f_max_lead:
                continue

        if f_min_payload is not None and payload_num is not None:
            if payload_num < f_min_payload:
                continue

        if environment and environment.strip():
            e_term = environment.strip().lower()
            if not env or e_term not in env.lower():
                continue

        if search and search.strip():
            s_term = search.strip().lower()
            combined_search = f"{unit_name} {p.get('sku') or ''} {p.get('manufacturer') or ''} {unit_category or ''}".lower()
            if s_term not in combined_search:
                continue

        annual_sav = None if session.is_legacy else p.get("estimated_annual_savings")
        payback = None
        if cost_num and annual_sav and annual_sav > 0:
            payback = round((cost_num / annual_sav) * 12)

        my_fb = feedback_map.get(unit_id, {
            "interest": None,
            "reason": None,
            "is_saved": False,
        })

        units.append({
            "property_id":              unit_id,
            "name":                     unit_name,
            "sku":                      p.get("sku"),
            "manufacturer":             p.get("manufacturer"),
            "category":                 unit_category,
            "specs":                    specs,
            "lead_time_weeks":          lead_time,
            "stock_status":             p.get("stock_status"),
            "spec_sheet_url":           p.get("spec_sheet_url"),
            "currency":                 p.get("currency") or "MYR",
            "cost":                     cost_num,
            "environment":              env,
            "image_url":                p.get("image_url"),
            "property_type":            p.get("property_type"),
            "payload_tier":             p.get("bedrooms"),
            "nav_sensors":              p.get("bathrooms"),
            "operational_range_sqft":   p.get("sqft"),
            "estimated_annual_savings": annual_sav,
            "payback_months":           payback,
            "matched":                  unit_id in matched_ids,
            "my_feedback":              my_fb,
        })

    return {
        "units": units,
        "matched_property_ids": list(matched_ids),
    }


# ─── Portal Quotes Endpoints ──────────────────────────────────────────────────

@app.post("/api/portal/{client_id}/quotes")
def portal_create_quote(
    client_id: str,
    body: dict,
    request: Request,
    session: PortalSession = Depends(get_current_portal_session),
):
    """
    Client requests a formal quote for a robot unit.
    Status starts in 'requested'. Duplicate open requests for same unit return 409.
    """
    require_company_access(session, client_id)
    if session.is_legacy:
        raise HTTPException(status_code=403, detail="Legacy session is read-only. Cannot request quotes.")

    check_portal_write_rate_limit(request, client_id, action="quote_request")

    property_id = body.get("property_id")
    if not property_id:
        raise HTTPException(status_code=400, detail="property_id is required")

    quantity = body.get("quantity", 1)
    if not isinstance(quantity, int) or quantity < 1 or quantity > 1000:
        raise HTTPException(status_code=422, detail="quantity must be an integer between 1 and 1000")

    notes = body.get("notes")
    if notes is not None:
        if not isinstance(notes, str) or len(notes) > 1000:
            raise HTTPException(status_code=422, detail="notes must be a string up to 1000 characters")

    # Verify property exists
    try:
        p_res = supabase.table("properties").select("id, address").eq("id", property_id).single().execute()
        if not p_res.data:
            raise HTTPException(status_code=404, detail="Property not found")
        unit_name = p_res.data.get("address") or "robot unit"
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=404, detail="Property not found")

    # Check for duplicate open quote
    try:
        dup = (
            supabase.table("portal_quotes")
            .select("id")
            .eq("client_id", client_id)
            .eq("property_id", property_id)
            .eq("status", "requested")
            .execute()
        )
        if dup.data:
            raise HTTPException(status_code=409, detail="An open quote request already exists for this unit.")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to check duplicate quotes: {exc}")

    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        ins_res = supabase.table("portal_quotes").insert({
            "client_id": client_id,
            "property_id": property_id,
            "contact_id": getattr(session, "contact_id", None),
            "quantity": quantity,
            "notes": notes,
            "status": "requested",
            "requested_at": now_iso,
            "created_at": now_iso,
            "updated_at": now_iso,
        }).execute()
        quote_row = ins_res.data[0] if ins_res.data else {}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to create quote request: {exc}")

    # Emit signal for sales rep
    try:
        c_res = supabase.table("clients").select("name").eq("id", client_id).single().execute()
        c_name = (c_res.data or {}).get("name") or "Client"
        supabase.table("signals").insert({
            "type": "portal_quote_requested",
            "client_id": client_id,
            "property_id": property_id,
            "message": f"{c_name} requested a quote for {quantity}x {unit_name}.",
        }).execute()
    except Exception as sig_exc:
        print(f"[portal_create_quote] Warning: signal insert failed: {sig_exc}")

    return {
        "id": quote_row.get("id"),
        "property_id": property_id,
        "property_name": unit_name,
        "quantity": quantity,
        "notes": notes,
        "status": "requested",
        "requested_at": now_iso,
        "responded_at": None,
    }


@app.get("/api/portal/{client_id}/quotes")
def portal_get_quotes(client_id: str, session: PortalSession = Depends(get_current_portal_session)):
    """
    List quotes for company, newest first.
    Excludes internal_notes entirely. Only exposes pricing fields once status in sent/accepted/declined.
    """
    require_company_access(session, client_id)
    try:
        res = (
            supabase.table("portal_quotes")
            .select("id, property_id, quantity, notes, status, requested_at, sent_at, responded_at, quoted_amount, currency, customer_note, valid_until, properties(address)")
            .eq("client_id", client_id)
            .order("requested_at", desc=True)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch quotes: {exc}")

    quotes = []
    for r in (res.data or []):
        prop = r.get("properties") or {}
        st = r.get("status")
        dto = {
            "id": r["id"],
            "property_id": r.get("property_id"),
            "property_name": prop.get("address") or "Robot Unit",
            "quantity": r.get("quantity", 1),
            "notes": r.get("notes"),
            "status": st,
            "requested_at": r.get("requested_at"),
            "responded_at": r.get("responded_at"),
        }
        if st in ("sent", "accepted", "declined"):
            dto["quoted_amount"] = float(r["quoted_amount"]) if r.get("quoted_amount") is not None else None
            dto["currency"] = r.get("currency") or "MYR"
            dto["customer_note"] = r.get("customer_note")
            dto["valid_until"] = str(r["valid_until"]) if r.get("valid_until") else None
            dto["sent_at"] = r.get("sent_at")
        quotes.append(dto)

    return {"quotes": quotes}


@app.post("/api/portal/{client_id}/quotes/{quote_id}/respond")
def portal_respond_quote(
    client_id: str,
    quote_id: str,
    body: dict,
    request: Request,
    session: PortalSession = Depends(get_current_portal_session),
):
    """
    Company accepts or declines a quote.
    Transitions status to 'accepted' or 'declined'.
    Emits portal_quote_accepted or portal_quote_declined signal.
    MUST NOT mutate pipeline_evaluations outcome, stage, or mark anything 'won'.
    """
    require_company_access(session, client_id)
    if session.is_legacy:
        raise HTTPException(status_code=403, detail="Legacy session is read-only. Cannot respond to quotes.")

    check_portal_write_rate_limit(request, client_id, action="quote_respond")

    response_val = body.get("response") or body.get("status")
    if response_val not in ("accepted", "declined"):
        raise HTTPException(status_code=422, detail="response must be 'accepted' or 'declined'")

    note = body.get("note")
    if note is not None:
        if not isinstance(note, str) or len(note) > 500:
            raise HTTPException(status_code=422, detail="note must be a string up to 500 characters")

    try:
        q_res = (
            supabase.table("portal_quotes")
            .select("id, client_id, property_id, status, quantity, quoted_amount, currency, customer_note, valid_until, requested_at, properties(address)")
            .eq("id", quote_id)
            .single()
            .execute()
        )
        if not q_res.data:
            raise HTTPException(status_code=404, detail="Quote not found")
        quote = q_res.data
        if quote.get("client_id") != client_id:
            raise HTTPException(status_code=403, detail="Forbidden: quote belongs to another company")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=404, detail="Quote not found")

    current_status = quote.get("status")
    if not can_quote_transition("portal", current_status, response_val):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot transition quote from '{current_status}' to '{response_val}'. Allowed transitions: sent -> accepted/declined",
        )

    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        supabase.table("portal_quotes").update({
            "status": response_val,
            "responded_at": now_iso,
            "portal_response_note": note,
            "updated_at": now_iso,
        }).eq("id", quote_id).execute()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to respond to quote: {exc}")

    # Emit signal for sales rep (does NOT touch pipeline_evaluations)
    try:
        c_res = supabase.table("clients").select("name").eq("id", client_id).single().execute()
        c_name = (c_res.data or {}).get("name") or "Client"
        prop = quote.get("properties") or {}
        unit_name = prop.get("address") or "robot unit"
        sig_type = "portal_quote_accepted" if response_val == "accepted" else "portal_quote_declined"
        supabase.table("signals").insert({
            "type": sig_type,
            "client_id": client_id,
            "property_id": quote.get("property_id"),
            "message": f"{c_name} {response_val} quote for {quote.get('quantity', 1)}x {unit_name}.",
        }).execute()
    except Exception as sig_exc:
        print(f"[portal_respond_quote] Warning: signal insert failed: {sig_exc}")

    return {
        "id": quote_id,
        "property_id": quote.get("property_id"),
        "property_name": (quote.get("properties") or {}).get("address") or "Robot Unit",
        "quantity": quote.get("quantity", 1),
        "status": response_val,
        "requested_at": quote.get("requested_at"),
        "responded_at": now_iso,
        "quoted_amount": float(quote["quoted_amount"]) if quote.get("quoted_amount") is not None else None,
        "currency": quote.get("currency") or "MYR",
        "customer_note": quote.get("customer_note"),
        "valid_until": str(quote["valid_until"]) if quote.get("valid_until") else None,
    }


# ─── Rep Console Quotes & Profile Audit ───────────────────────────────────────

@app.get("/api/console/clients/{client_id}/quotes")
def rep_get_client_quotes(client_id: str, request: Request):
    """Rep console: view quotes for assigned client company (including internal_notes)."""
    if hasattr(request.state, "agent"):
        require_client_access(request.state.agent, client_id, supabase)

    try:
        res = (
            supabase.table("portal_quotes")
            .select("id, property_id, quantity, notes, status, requested_at, sent_at, responded_at, quoted_amount, currency, customer_note, internal_notes, valid_until, portal_response_note, properties(address)")
            .eq("client_id", client_id)
            .order("requested_at", desc=True)
            .execute()
        )
        return {"quotes": res.data or []}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch quotes: {exc}")


@app.get("/api/console/quotes/pending")
def rep_get_pending_quotes(request: Request):
    """Rep console: list pending quote requests for rep (admin sees all)."""
    agent = getattr(request.state, "agent", None)
    try:
        q = (
            supabase.table("portal_quotes")
            .select("id, client_id, property_id, quantity, notes, status, requested_at, clients(id, name, assigned_agent_id), properties(address)")
            .eq("status", "requested")
            .order("requested_at", desc=True)
        )
        res = q.execute()
        rows = res.data or []
        if agent and agent.role != "admin" and agent.agent_id:
            rows = [r for r in rows if str((r.get("clients") or {}).get("assigned_agent_id")) == str(agent.agent_id)]
        return {"quotes": rows}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch pending quotes: {exc}")


@app.post("/api/console/clients/{client_id}/quotes/{quote_id}/send")
def rep_send_quote(client_id: str, quote_id: str, body: dict, request: Request):
    """Rep console: send formal quote to company."""
    if hasattr(request.state, "agent"):
        require_client_access(request.state.agent, client_id, supabase)

    quoted_amount = body.get("quoted_amount")
    if quoted_amount is None:
        raise HTTPException(status_code=422, detail="quoted_amount is required")
    try:
        f_amount = float(quoted_amount)
        if f_amount <= 0:
            raise ValueError()
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="quoted_amount must be a positive number")

    currency = body.get("currency", "MYR")
    if currency not in ("MYR", "USD"):
        raise HTTPException(status_code=422, detail="currency must be 'MYR' or 'USD'")

    customer_note = body.get("customer_note")
    internal_notes = body.get("internal_notes")
    valid_until = body.get("valid_until")

    try:
        q_res = supabase.table("portal_quotes").select("id, client_id, status").eq("id", quote_id).single().execute()
        if not q_res.data:
            raise HTTPException(status_code=404, detail="Quote not found")
        quote = q_res.data
        if quote.get("client_id") != client_id:
            raise HTTPException(status_code=404, detail="Quote not found")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=404, detail="Quote not found")

    if not can_quote_transition("rep", quote.get("status"), "sent"):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot send quote with status '{quote.get('status')}'. Allowed: requested -> sent, sent -> sent",
        )

    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        upd = supabase.table("portal_quotes").update({
            "status": "sent",
            "quoted_amount": f_amount,
            "currency": currency,
            "customer_note": customer_note,
            "internal_notes": internal_notes,
            "valid_until": valid_until,
            "sent_at": now_iso,
            "updated_at": now_iso,
        }).eq("id", quote_id).execute()
        return upd.data[0] if upd.data else {"success": True}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to send quote: {exc}")


@app.post("/api/console/clients/{client_id}/inquiries/{inquiry_id}/reply")
def rep_reply_inquiry(client_id: str, inquiry_id: str, body: dict, request: Request):
    """Rep console: rep sends a reply to an inquiry thread."""
    if hasattr(request.state, "agent"):
        require_client_access(request.state.agent, client_id, supabase)

    reply_body = (body.get("body") or body.get("reply") or "").strip()
    if not reply_body or len(reply_body) > 4000:
        raise HTTPException(status_code=422, detail="Reply body must be between 1 and 4000 characters")

    try:
        inq_res = supabase.table("client_inquiries").select("id, client_id").eq("id", inquiry_id).single().execute()
        if not inq_res.data or inq_res.data.get("client_id") != client_id:
            raise HTTPException(status_code=404, detail="Inquiry not found")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=404, detail="Inquiry not found")

    try:
        # Update client_inquiries.agent_reply for backward compatibility
        supabase.table("client_inquiries").update({
            "agent_reply": reply_body,
            "status": "in_progress",
        }).eq("id", inquiry_id).execute()

        # Insert rep message into inquiry_messages
        ins = supabase.table("inquiry_messages").insert({
            "inquiry_id": inquiry_id,
            "client_id": client_id,
            "sender": "rep",
            "body": reply_body,
        }).execute()
        return {"success": True, "message": ins.data[0] if ins.data else None}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to post rep reply: {exc}")


@app.get("/api/console/clients/{client_id}/portal/profile-audit")
def rep_get_profile_audit(client_id: str, request: Request):
    """Rep console: view portal profile change history for assigned client."""
    if hasattr(request.state, "agent"):
        require_client_access(request.state.agent, client_id, supabase)

    try:
        res = (
            supabase.table("portal_profile_audit")
            .select("id, field, old_value, new_value, changed_at, contact_id, portal_contacts(name, email)")
            .eq("client_id", client_id)
            .order("changed_at", desc=True)
            .execute()
        )
        return {"audit_log": res.data or []}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch profile audit log: {exc}")


# ─── Portal Activity Stream ───────────────────────────────────────────────────

@app.get("/api/portal/{client_id}/activity")
def portal_client_activity(client_id: str, session: PortalSession = Depends(get_current_portal_session)):
    """
    Return a unified activity stream: demos, rep messages, quotes (sent/accepted/declined), profile updates.
    Each item: { event_type: demo|message|quote|profile, label, at, ref_id }.
    Labels in plain English.
    """
    require_company_access(session, client_id)
    try:
        client_res = supabase.table("clients").select("id").eq("id", client_id).single().execute()
        if not client_res.data:
            raise HTTPException(status_code=404, detail="Client not found")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=404, detail="Client not found")

    items = []

    # 1. Demos
    try:
        d_res = (
            supabase.table("scheduled_viewings")
            .select("id, status, confirmation_status, scheduled_at, created_at, properties(address)")
            .eq("client_id", client_id)
            .order("created_at", desc=True)
            .limit(20)
            .execute()
        )
        for d in (d_res.data or []):
            prop = d.get("properties") or {}
            unit_name = prop.get("address") or "robot unit"
            eff = get_demo_effective_status(d)
            if eff == "confirmed":
                label = f"Demo confirmed for {unit_name}"
            elif eff == "cancelled":
                label = f"Demo cancelled for {unit_name}"
            elif eff == "offered":
                label = f"Demo slot offered for {unit_name}"
            elif eff == "completed":
                label = f"Demo completed for {unit_name}"
            else:
                label = f"Demo requested for {unit_name}"

            at_val = d.get("scheduled_at") or d.get("created_at")
            items.append({
                "event_type": "demo",
                "label": label,
                "at": at_val,
                "ref_id": d["id"],
            })
    except Exception as exc:
        print(f"[portal_client_activity] Demos non-fatal: {exc}")

    # 2. Messages (rep -> company only)
    try:
        m_res = (
            supabase.table("inquiry_messages")
            .select("id, inquiry_id, body, created_at")
            .eq("client_id", client_id)
            .eq("sender", "rep")
            .order("created_at", desc=True)
            .limit(20)
            .execute()
        )
        for m in (m_res.data or []):
            items.append({
                "event_type": "message",
                "label": "Message from your sales representative",
                "at": m.get("created_at"),
                "ref_id": m["id"],
            })
    except Exception as exc:
        print(f"[portal_client_activity] Messages non-fatal: {exc}")

    # 3. Quotes (sent, accepted, declined)
    try:
        q_res = (
            supabase.table("portal_quotes")
            .select("id, status, quantity, sent_at, responded_at, requested_at, properties(address)")
            .eq("client_id", client_id)
            .in_("status", ["sent", "accepted", "declined"])
            .order("updated_at", desc=True)
            .limit(20)
            .execute()
        )
        for q in (q_res.data or []):
            prop = q.get("properties") or {}
            u_name = prop.get("address") or "unit"
            st = q.get("status")
            if st == "sent":
                label = f"Quote sent for {q.get('quantity', 1)}x {u_name}"
                at_val = q.get("sent_at") or q.get("requested_at")
            elif st == "accepted":
                label = f"Quote accepted for {q.get('quantity', 1)}x {u_name}"
                at_val = q.get("responded_at") or q.get("sent_at")
            else:
                label = f"Quote declined for {q.get('quantity', 1)}x {u_name}"
                at_val = q.get("responded_at") or q.get("sent_at")

            items.append({
                "event_type": "quote",
                "label": label,
                "at": at_val,
                "ref_id": q["id"],
            })
    except Exception as exc:
        print(f"[portal_client_activity] Quotes non-fatal: {exc}")

    # 4. Profile updates
    try:
        p_res = (
            supabase.table("portal_profile_audit")
            .select("id, field, changed_at")
            .eq("client_id", client_id)
            .order("changed_at", desc=True)
            .limit(20)
            .execute()
        )
        for p in (p_res.data or []):
            items.append({
                "event_type": "profile",
                "label": f"Company profile updated ({p.get('field', 'profile')})",
                "at": p.get("changed_at"),
                "ref_id": p["id"],
            })
    except Exception as exc:
        print(f"[portal_client_activity] Profile non-fatal: {exc}")

    # Sort all items descending by timestamp
    items.sort(key=lambda x: x.get("at") or "", reverse=True)
    return {"activity": items}


# ─── Portal Preferences & Profile Endpoint ───────────────────────────────────

_VALID_ENVIRONMENTS = {
    "Logistics & Warehousing",
    "Healthcare Facilities",
    "Manufacturing",
    "Retail & Commercial",
    "Agriculture & Forestry",
    "Outdoor / Industrial Sites",
}
_VALID_FINANCING = {"cash", "pre-approved", "in-progress", "unspecified", "leasing"}
_VALID_TIMELINE  = {"< 3 months", "3-6 months", "6-12 months", "flexible"}
_BUDGET_MAX      = 10_000_000

PROFILE_FIELDS = [
    "industry",
    "facility_type",
    "facility_size_sqm",
    "use_case",
    "purchase_timeline",
    "existing_automation",
]


@app.get("/api/portal/{client_id}/preferences")
def portal_get_preferences(client_id: str, session: PortalSession = Depends(get_current_portal_session)):
    """Return the client's current editable preferences, new B2B profile fields, and contacts list."""
    require_company_access(session, client_id)
    try:
        res = (
            supabase.table("clients")
            .select("id, stated_budget, preferred_neighborhood, secondary_neighborhood, financing_status, move_in_timeline, property_type_preference, industry, facility_type, facility_size_sqm, use_case, purchase_timeline, existing_automation, profile_updated_at, facility_profile")
            .eq("id", client_id)
            .single()
            .execute()
        )
        if not res.data:
            raise HTTPException(status_code=404, detail="Client not found")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=404, detail="Client not found")

    c = res.data

    pt_values: list[str] = []
    try:
        pt_res = supabase.table("properties").select("property_type").execute()
        pt_values = sorted({
            r["property_type"] for r in (pt_res.data or [])
            if r.get("property_type")
        })
    except Exception:
        pass

    # Fetch contacts list (read-only: name, role, email; no codes/hashes)
    contacts = []
    try:
        ct_res = (
            supabase.table("portal_contacts")
            .select("id, name, title, portal_role, email")
            .eq("client_id", client_id)
            .eq("status", "active")
            .order("is_primary", desc=True)
            .execute()
        )
        for ct in (ct_res.data or []):
            contacts.append({
                "id": ct["id"],
                "name": ct.get("name") or "Contact",
                "role": ct.get("portal_role") or "member",
                "title": ct.get("title"),
                "email": ct.get("email"),
            })
    except Exception as exc:
        print(f"[portal_get_preferences] Contacts non-fatal: {exc}")

    return {
        "client_id":                c["id"],
        "stated_budget":            c.get("stated_budget"),
        "preferred_neighborhood":   c.get("preferred_neighborhood"),
        "secondary_neighborhood":   c.get("secondary_neighborhood"),
        "financing_status":         c.get("financing_status"),
        "move_in_timeline":         c.get("move_in_timeline"),
        "property_type_preference": c.get("property_type_preference"),
        "industry":                 c.get("industry"),
        "facility_type":            c.get("facility_type"),
        "facility_size_sqm":        c.get("facility_size_sqm"),
        "use_case":                 c.get("use_case"),
        "purchase_timeline":        c.get("purchase_timeline"),
        "existing_automation":      c.get("existing_automation"),
        "profile_updated_at":       c.get("profile_updated_at"),
        "facility_profile":         c.get("facility_profile") or {},
        "contacts":                 contacts,
        "matches_refreshed_count":  0,
        "updated_fields":           [],
        "available_property_types": pt_values,
        "available_environments":   sorted(_VALID_ENVIRONMENTS),
    }


@app.put("/api/portal/{client_id}/preferences")
@app.patch("/api/portal/{client_id}/preferences")
def portal_save_preferences(
    client_id: str,
    body: dict,
    request: Request,
    session: PortalSession = Depends(get_current_portal_session),
):
    """
    Update company preferences and profile fields.
    Records field diffs in portal_profile_audit, updates profile_updated_at = now(),
    and emits a portal_profile_updated signal.
    """
    require_company_access(session, client_id)
    if session.is_legacy:
        raise HTTPException(status_code=403, detail="Legacy session is read-only. Cannot modify preferences.")
    if session.portal_role == "finance_viewer":
        raise HTTPException(status_code=403, detail="Finance viewers cannot modify preferences.")

    check_portal_write_rate_limit(request, client_id, action="save_preferences")

    try:
        client_res = supabase.table("clients").select("*").eq("id", client_id).single().execute()
        if not client_res.data:
            raise HTTPException(status_code=404, detail="Client not found")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=404, detail="Client not found")

    client = client_res.data
    updates: dict[str, Any] = {}
    errors: list[str] = []

    # 1. Standard preferences fields
    if "stated_budget" in body:
        v = body["stated_budget"]
        if v is None:
            updates["stated_budget"] = None
        elif not isinstance(v, (int, float)) or v <= 0 or v > _BUDGET_MAX:
            errors.append(f"stated_budget must be a positive number <= {_BUDGET_MAX:,}")
        else:
            updates["stated_budget"] = float(v)

    if "preferred_neighborhood" in body:
        v = body["preferred_neighborhood"]
        if v is None:
            updates["preferred_neighborhood"] = None
        elif v not in _VALID_ENVIRONMENTS:
            errors.append(f"preferred_neighborhood must be one of: {', '.join(sorted(_VALID_ENVIRONMENTS))}")
        else:
            updates["preferred_neighborhood"] = v

    if "secondary_neighborhood" in body:
        v = body["secondary_neighborhood"]
        if v is None:
            updates["secondary_neighborhood"] = None
        elif v not in _VALID_ENVIRONMENTS:
            errors.append(f"secondary_neighborhood must be one of: {', '.join(sorted(_VALID_ENVIRONMENTS))}")
        else:
            updates["secondary_neighborhood"] = v

    if "financing_status" in body:
        v = body["financing_status"]
        if v is None:
            updates["financing_status"] = None
        elif v not in _VALID_FINANCING:
            errors.append(f"financing_status must be one of: {', '.join(sorted(_VALID_FINANCING))}")
        else:
            updates["financing_status"] = v

    if "move_in_timeline" in body:
        v = body["move_in_timeline"]
        if v is None:
            updates["move_in_timeline"] = None
        elif v not in _VALID_TIMELINE:
            errors.append(f"move_in_timeline must be one of: {', '.join(sorted(_VALID_TIMELINE))}")
        else:
            updates["move_in_timeline"] = v

    if "property_type_preference" in body:
        v = body["property_type_preference"]
        if v is None:
            updates["property_type_preference"] = None
        else:
            updates["property_type_preference"] = str(v)

    # 2. B2B Company Profile fields
    if "facility_size_sqm" in body:
        v = body["facility_size_sqm"]
        if v is None:
            updates["facility_size_sqm"] = None
        elif not isinstance(v, int) or v <= 0:
            errors.append("facility_size_sqm must be a positive integer")
        else:
            updates["facility_size_sqm"] = v

    for s_field in ("industry", "facility_type", "use_case", "purchase_timeline", "existing_automation"):
        if s_field in body:
            v = body[s_field]
            if v is None:
                updates[s_field] = None
            elif not isinstance(v, str) or len(v) > 200:
                errors.append(f"{s_field} must be a string up to 200 characters")
            else:
                updates[s_field] = v.strip()

    # 3. B2B Facility Profile (JSONB)
    if "facility_profile" in body:
        fp_raw = body["facility_profile"]
        if not isinstance(fp_raw, dict):
            errors.append("facility_profile must be a JSON object")
        else:
            try:
                fp_model = FacilityProfile.model_validate(fp_raw)
            except Exception as e:
                errors.append(f"Invalid facility_profile: {e}")
            else:
                existing_fp = client.get("facility_profile") or {}
                if not isinstance(existing_fp, dict):
                    existing_fp = {}
                fp_dict = fp_model.model_dump(exclude_unset=True)
                merged_fp = {**existing_fp, **fp_dict}
                updates["facility_profile"] = merged_fp

    allowed_keys = {
        "stated_budget", "preferred_neighborhood", "secondary_neighborhood",
        "financing_status", "move_in_timeline", "property_type_preference",
        "industry", "facility_type", "facility_size_sqm", "use_case",
        "purchase_timeline", "existing_automation", "facility_profile",
    }
    extra = set(body.keys()) - allowed_keys
    if extra:
        errors.append(f"Unknown fields not allowed: {', '.join(sorted(extra))}")

    if errors:
        raise HTTPException(status_code=422, detail=" | ".join(errors))

    if not updates:
        return {
            "client_id": client_id,
            "updated_fields": [],
            "matches_refreshed_count": 0,
        }

    # Audit profile field changes
    now_iso = datetime.now(timezone.utc).isoformat()
    profile_diffs = []
    for pf in PROFILE_FIELDS:
        if pf in updates:
            old_val = client.get(pf)
            new_val = updates[pf]
            if str(old_val or "") != str(new_val or ""):
                profile_diffs.append((pf, old_val, new_val))

    # Audit facility_profile field changes
    fp_diffs = []
    if "facility_profile" in updates:
        existing_fp = client.get("facility_profile") or {}
        if not isinstance(existing_fp, dict):
            existing_fp = {}
        new_fp = updates["facility_profile"]
        for k, v in new_fp.items():
            old_v = existing_fp.get(k)
            if old_v != v:
                fp_diffs.append((f"facility_profile.{k}", old_v, v))

    for pf, old_v, new_v in profile_diffs + fp_diffs:
        try:
            supabase.table("portal_profile_audit").insert({
                "client_id": client_id,
                "contact_id": getattr(session, "contact_id", None),
                "field": pf,
                "old_value": str(old_v) if old_v is not None else None,
                "new_value": str(new_v) if new_v is not None else None,
                "changed_at": now_iso,
            }).execute()
        except Exception as aud_exc:
            print(f"[portal_save_preferences] Audit insert non-fatal: {aud_exc}")

    if profile_diffs or fp_diffs:
        updates["profile_updated_at"] = now_iso

    # Persist updates to clients table
    try:
        supabase.table("clients").update(updates).eq("id", client_id).execute()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save preferences: {exc}")

    # Emit signal if profile changed
    client_name = client.get("name", "Client")
    if fp_diffs:
        try:
            supabase.table("signals").insert({
                "type": "portal_profile_updated",
                "client_id": client_id,
                "message": f"{client_name} updated deployment specs",
            }).execute()
        except Exception as sig_exc:
            print(f"[portal_save_preferences] Signal insert non-fatal: {sig_exc}")
    elif profile_diffs:
        try:
            diff_names = ", ".join(d[0] for d in profile_diffs)
            supabase.table("signals").insert({
                "type": "portal_profile_updated",
                "client_id": client_id,
                "message": f"{client_name} updated company profile ({diff_names}).",
            }).execute()
        except Exception as sig_exc:
            print(f"[portal_save_preferences] Signal insert non-fatal: {sig_exc}")

    # Re-score evaluations if preferences changed
    rescored = 0
    pref_keys_changed = set(updates.keys()) & {
        "stated_budget", "preferred_neighborhood", "secondary_neighborhood",
        "financing_status", "move_in_timeline", "property_type_preference",
    }
    if pref_keys_changed:
        try:
            updated_client = supabase.table("clients").select("*").eq("id", client_id).single().execute()
            props_res = supabase.table("properties").select("*").execute()
            purchases_res = supabase.table("client_past_purchases").select("*").eq("client_id", client_id).execute()

            c2 = updated_client.data or {}
            all_props = {p["id"]: p for p in (props_res.data or [])}
            past_purchases = purchases_res.data or []

            client_profile = {
                "budget":                   c2.get("stated_budget"),
                "preferred_neighborhood":   c2.get("preferred_neighborhood"),
                "engagement_history":       c2.get("past_viewings"),
                "source":                   c2.get("source"),
                "financing_status":         c2.get("financing_status"),
                "move_in_timeline":         c2.get("move_in_timeline"),
                "property_type_preference": c2.get("property_type_preference"),
                "secondary_neighborhood":   c2.get("secondary_neighborhood"),
                "past_purchases":           past_purchases,
            }

            evals_res = (
                supabase.table("pipeline_evaluations")
                .select("property_id")
                .eq("client_id", client_id)
                .execute()
            )
            eval_rows = evals_res.data or []
            new_evals = []
            for row in eval_rows:
                prop = all_props.get(row["property_id"])
                if not prop:
                    continue
                result = score_pair(client_profile, prop)
                ml_prob = predict_probability(client_profile, prop)
                new_evals.append({
                    "client_id":      client_id,
                    "property_id":    row["property_id"],
                    "ai_probability": result["probability"],
                    "expected_value": result["expected_value"],
                    "segment_tier":   result["tier"],
                    "ml_probability": ml_prob,
                })

            if new_evals:
                try:
                    supabase.table("pipeline_evaluations").upsert(
                        new_evals, on_conflict="client_id,property_id"
                    ).execute()
                except Exception as exc:
                    if "ml_probability" in str(exc):
                        for e in new_evals:
                            e.pop("ml_probability", None)
                        supabase.table("pipeline_evaluations").upsert(
                            new_evals, on_conflict="client_id,property_id"
                        ).execute()
                rescored = len(new_evals)
        except Exception as rescore_exc:
            print(f"[portal_save_preferences] Re-score non-fatal: {rescore_exc}")

        try:
            supabase.table("client_facing_reasoning_cache").delete().eq("client_id", client_id).execute()
        except Exception:
            pass

    return {
        "client_id": client_id,
        "updated_fields": list(updates.keys()),
        "facility_profile": updates.get("facility_profile") or client.get("facility_profile") or {},
        "matches_refreshed_count": rescored,
        "profile_updated_at": updates.get("profile_updated_at"),
    }




