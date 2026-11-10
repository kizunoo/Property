"""quote_routes.py

Rep console routes for simulated supplier quote agent.
Protected by agent authentication and rep ownership scoping.
All quotes are simulated; nothing is sent to external manufacturers.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from copilot_routes import _is_admin
from copilot_tools import Identity, can_access
import triage_service
from quote_logic import (
    SIM_FOOTER,
    build_draft,
    due_requests,
    market_price_ok,
    mock_reply,
    parse_reply,
    quote_in_bounds,
    reply_delay_seconds,
)
from route_policies import RoutePolicy, RoutePolicyDecl, ROUTE_POLICY_DECLARATIONS
import re

# Register quote route security policies
ROUTE_POLICY_DECLARATIONS.extend([
    RoutePolicyDecl("GET", "/api/quotes", re.compile(r"^/api/quotes$"), RoutePolicy.ANY_AGENT, False, "List supplier quotes, requests and activity for rep"),
    RoutePolicyDecl("POST", "/api/quotes/request", re.compile(r"^/api/quotes/request$"), RoutePolicy.ANY_AGENT, False, "Create supplier quote request"),
    RoutePolicyDecl("POST", "/api/quotes/{request_id}/approve", re.compile(r"^/api/quotes/[^/]+/approve$"), RoutePolicy.ANY_AGENT, False, "Approve simulated quote request"),
    RoutePolicyDecl("POST", "/api/quotes/{request_id}/cancel", re.compile(r"^/api/quotes/[^/]+/cancel$"), RoutePolicy.ANY_AGENT, False, "Cancel quote request"),
    RoutePolicyDecl("POST", "/api/quotes/log", re.compile(r"^/api/quotes/log$"), RoutePolicy.ANY_AGENT, False, "Log quote activity"),
])

router = APIRouter()
log = logging.getLogger("quote_routes")


def _identity(request: Request) -> Identity:
    agent = getattr(request.state, "agent", None)
    if agent is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return Identity(agent_id=str(agent.agent_id), is_admin=_is_admin(agent))


def _db():
    db = triage_service.get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Service unavailable")
    return db


class RequestQuoteBody(BaseModel):
    client_id: str
    property_id: str
    market_price_myr: float
    kind: Literal["quote", "requote"] = "quote"


class ApproveBody(BaseModel):
    draft_body: Optional[str] = Field(default=None, max_length=4000)


class LogActivityBody(BaseModel):
    kind: Literal["expiry_followup_sent", "expiry_dismissed", "requote_dismissed"]
    ref_id: str
    summary: str = Field(default="", max_length=500)


def _deliver_due_quotes(db, identity: Identity, now: datetime) -> None:
    """Delivers due simulated supplier replies for this agent. Idempotent."""
    now_iso = now.isoformat()
    # Fetch requests sent and due
    rows = (
        db.table("supplier_quote_requests")
        .select("*")
        .eq("agent_id", identity.agent_id)
        .eq("status", "sent")
        .lte("reply_due_at", now_iso)
        .execute()
        .data
        or []
    )
    if not rows:
        return

    for req in rows:
        req_id = req["id"]
        prop_id = req["property_id"]
        client_id = req["client_id"]
        kind = req.get("kind", "quote")
        market_price = float(req.get("market_price_myr") or 0)

        # Load robot metadata
        robot_res = (
            db.table("properties")
            .select("id,address,manufacturer,indicative_price_myr")
            .eq("id", prop_id)
            .limit(1)
            .execute()
            .data
            or []
        )
        if not robot_res:
            continue
        robot = robot_res[0]
        robot_name = robot.get("address") or "the listed robot"
        indicative = robot.get("indicative_price_myr")

        previous_price = None
        if kind == "requote":
            prev_quotes = (
                db.table("supplier_quotes")
                .select("price_myr")
                .eq("client_id", client_id)
                .eq("property_id", prop_id)
                .is_("superseded_by", "null")
                .order("issued_at", desc=True)
                .limit(1)
                .execute()
                .data
                or []
            )
            if prev_quotes and prev_quotes[0].get("price_myr"):
                previous_price = int(prev_quotes[0]["price_myr"])

        reply = mock_reply(
            req_id,
            kind,
            robot_name,
            market_price,
            previous_price=previous_price,
        )
        parsed = parse_reply(reply)

        if parsed is None or not quote_in_bounds(parsed["price_myr"], indicative):
            # Mark request as failed and log activity
            db.table("supplier_quote_requests").update({"status": "failed"}).eq("id", req_id).execute()
            db.table("agent_activity").insert({
                "agent_id": identity.agent_id,
                "kind": "request_failed",
                "summary": f"Supplier quote generation failed for {robot_name}"[:200],
                "ref_id": req_id,
            }).execute()
            continue

        # Atomic claim: update status to quoted WHERE id = req_id AND status = 'sent'
        claim = (
            db.table("supplier_quote_requests")
            .update({"status": "quoted"})
            .eq("id", req_id)
            .eq("status", "sent")
            .execute()
        )
        # If no row was updated, another worker already claimed it
        if not claim.data or len(claim.data) != 1:
            continue

        issued_at = now
        expires_at = issued_at + timedelta(days=parsed["validity_days"])

        quote_insert = {
            "request_id": req_id,
            "agent_id": identity.agent_id,
            "client_id": client_id,
            "property_id": prop_id,
            "price_myr": parsed["price_myr"],
            "lead_time_weeks": parsed.get("lead_time_weeks"),
            "terms": parsed.get("terms"),
            "source_text": reply,
            "issued_at": issued_at.isoformat(),
            "expires_at": expires_at.isoformat(),
            "is_simulated": True,
        }
        ins_quote = db.table("supplier_quotes").insert(quote_insert).execute()
        new_quote_id = ins_quote.data[0]["id"] if ins_quote.data else None

        if new_quote_id:
            # Supersede older still-valid quotes for this client & property
            db.table("supplier_quotes").update({
                "superseded_by": new_quote_id
            }).eq("client_id", client_id).eq("property_id", prop_id).neq("id", new_quote_id).is_("superseded_by", "null").gt("expires_at", now_iso).execute()

            # Clean up any leftover draft quote requests for this pair
            try:
                db.table("supplier_quote_requests").update({
                    "status": "cancelled"
                }).eq("agent_id", identity.agent_id).eq("client_id", client_id).eq("property_id", prop_id).eq("status", "draft").eq("kind", "quote").execute()
            except Exception:
                pass

            summary = f"Simulated supplier quote received for {robot_name}: RM {parsed['price_myr']:,}"[:200]
            db.table("agent_activity").insert({
                "agent_id": identity.agent_id,
                "kind": "quote_received",
                "summary": summary,
                "ref_id": new_quote_id,
            }).execute()


@router.get("/api/quotes")
def get_quotes(request: Request):
    identity, db = _identity(request), _db()
    now = datetime.now(timezone.utc)
    _deliver_due_quotes(db, identity, now)

    requests = (
        db.table("supplier_quote_requests")
        .select("*")
        .eq("agent_id", identity.agent_id)
        .order("created_at", desc=True)
        .limit(200)
        .execute()
        .data
        or []
    )
    quotes = (
        db.table("supplier_quotes")
        .select("*")
        .eq("agent_id", identity.agent_id)
        .order("issued_at", desc=True)
        .limit(200)
        .execute()
        .data
        or []
    )

    now_iso = now.isoformat()
    # Cancel any leftover draft quote requests for pairs that already have a valid active quote
    valid_pairs = {
        (q["client_id"], q["property_id"])
        for q in quotes
        if q.get("superseded_by") is None and q.get("expires_at") and q["expires_at"] > now_iso
    }
    for r in requests:
        if r.get("status") == "draft" and r.get("kind") == "quote":
            if (r.get("client_id"), r.get("property_id")) in valid_pairs:
                r["status"] = "cancelled"
                try:
                    db.table("supplier_quote_requests").update({"status": "cancelled"}).eq("id", r["id"]).execute()
                except Exception:
                    pass
    activity = (
        db.table("agent_activity")
        .select("*")
        .eq("agent_id", identity.agent_id)
        .order("created_at", desc=True)
        .limit(50)
        .execute()
        .data
        or []
    )
    return {"requests": requests, "quotes": quotes, "activity": activity}


@router.post("/api/quotes/request")
def request_quote(body: RequestQuoteBody, request: Request):
    identity, db = _identity(request), _db()

    # Scoping: rep may only act on assigned clients (or admin)
    if not can_access(db, identity, body.client_id):
        raise HTTPException(status_code=404, detail="Client not found or not accessible")

    # Robot must exist and have indicative_price_myr
    robot_res = (
        db.table("properties")
        .select("id,address,manufacturer,indicative_price_myr")
        .eq("id", body.property_id)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not robot_res:
        raise HTTPException(status_code=422, detail="Robot not found")
    robot = robot_res[0]
    indicative = robot.get("indicative_price_myr")
    if indicative is None:
        raise HTTPException(status_code=422, detail="Robot has no indicative price")

    # market_price_ok check
    if not market_price_ok(body.market_price_myr, indicative):
        raise HTTPException(status_code=422, detail="Market price out of allowed bounds")

    # If an open request already exists for the same pair and kind, return it unchanged
    open_res = (
        db.table("supplier_quote_requests")
        .select("*")
        .eq("agent_id", identity.agent_id)
        .eq("client_id", body.client_id)
        .eq("property_id", body.property_id)
        .eq("kind", body.kind)
        .in_("status", ["draft", "sent"])
        .order("created_at", desc=True)
        .limit(1)
        .execute()
        .data
        or []
    )
    if open_res:
        return open_res[0]

    # Load client info for draft
    client_res = (
        db.table("clients")
        .select("id,name,facility_profile")
        .eq("id", body.client_id)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not client_res:
        raise HTTPException(status_code=404, detail="Client not found")
    client_row = client_res[0]

    company = {"name": client_row.get("name") or "prospective customer"}
    robot_info = {
        "name": robot.get("address") or "robot",
        "manufacturer": robot.get("manufacturer") or "the manufacturer",
    }

    # Extract facility profile fields (no email, no phone)
    fp = client_row.get("facility_profile") if isinstance(client_row.get("facility_profile"), dict) else {}
    facts = {}
    for key in ("facility_type", "floor_area_sqm", "environment_notes", "primary_use_case", "timeline", "budget_band"):
        val = fp.get(key)
        if val not in (None, ""):
            label = key.replace("_", " ").capitalize()
            facts[label] = str(val)

    previous_price = None
    if body.kind == "requote":
        prev_quotes = (
            db.table("supplier_quotes")
            .select("price_myr")
            .eq("client_id", body.client_id)
            .eq("property_id", body.property_id)
            .is_("superseded_by", "null")
            .order("issued_at", desc=True)
            .limit(1)
            .execute()
            .data
            or []
        )
        if prev_quotes and prev_quotes[0].get("price_myr"):
            previous_price = int(prev_quotes[0]["price_myr"])

    draft_subject, draft_body = build_draft(
        body.kind, company, robot_info, facts, previous_price=previous_price
    )

    insert_payload = {
        "agent_id": identity.agent_id,
        "client_id": body.client_id,
        "property_id": body.property_id,
        "kind": body.kind,
        "status": "draft",
        "draft_subject": draft_subject,
        "draft_body": draft_body,
        "market_price_myr": body.market_price_myr,
    }
    inserted = db.table("supplier_quote_requests").insert(insert_payload).execute()
    return inserted.data[0] if inserted.data else insert_payload


@router.post("/api/quotes/{request_id}/approve")
def approve_quote_request(request_id: str, body: Optional[ApproveBody], request: Request):
    identity, db = _identity(request), _db()

    rows = (
        db.table("supplier_quote_requests")
        .select("*")
        .eq("id", request_id)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Quote request not found")
    req = rows[0]

    if str(req.get("agent_id")) != identity.agent_id and not identity.is_admin:
        raise HTTPException(status_code=403, detail="Forbidden")

    if req.get("status") != "draft":
        raise HTTPException(status_code=409, detail="Only draft quote requests can be approved")

    body_text = req.get("draft_body") or ""
    if body and body.draft_body is not None:
        body_text = body.draft_body
        if SIM_FOOTER not in body_text:
            body_text = f"{body_text.rstrip()}\n\n{SIM_FOOTER}"

    now = datetime.now(timezone.utc)
    delay_s = reply_delay_seconds(request_id)
    reply_due = now + timedelta(seconds=delay_s)

    update_payload = {
        "status": "sent",
        "draft_body": body_text,
        "sent_at": now.isoformat(),
        "reply_due_at": reply_due.isoformat(),
    }
    upd = db.table("supplier_quote_requests").update(update_payload).eq("id", request_id).execute()

    # Log activity row
    db.table("agent_activity").insert({
        "agent_id": identity.agent_id,
        "kind": "request_sent",
        "summary": f"Sent quote request for {req.get('kind', 'quote')} (simulated supplier)"[:200],
        "ref_id": request_id,
    }).execute()

    return upd.data[0] if upd.data else update_payload


@router.post("/api/quotes/{request_id}/cancel")
def cancel_quote_request(request_id: str, request: Request):
    identity, db = _identity(request), _db()

    rows = (
        db.table("supplier_quote_requests")
        .select("*")
        .eq("id", request_id)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Quote request not found")
    req = rows[0]

    if str(req.get("agent_id")) != identity.agent_id and not identity.is_admin:
        raise HTTPException(status_code=403, detail="Forbidden")

    if req.get("status") not in ("draft", "sent"):
        raise HTTPException(status_code=409, detail="Only draft or sent quote requests can be cancelled")

    upd = db.table("supplier_quote_requests").update({"status": "cancelled"}).eq("id", request_id).execute()

    db.table("agent_activity").insert({
        "agent_id": identity.agent_id,
        "kind": "request_cancelled",
        "summary": f"Cancelled {req.get('kind', 'quote')} request"[:200],
        "ref_id": request_id,
    }).execute()

    return upd.data[0] if upd.data else {"status": "cancelled"}


@router.post("/api/quotes/log")
def log_quote_activity(body: LogActivityBody, request: Request):
    identity, db = _identity(request), _db()

    # ref_id must be a quote belonging to this agent
    quote_res = (
        db.table("supplier_quotes")
        .select("id,agent_id")
        .eq("id", body.ref_id)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not quote_res:
        raise HTTPException(status_code=404, detail="Quote not found")
    quote = quote_res[0]
    if str(quote.get("agent_id")) != identity.agent_id and not identity.is_admin:
        raise HTTPException(status_code=403, detail="Forbidden")

    summary = (body.summary or "")[:200]
    ins = db.table("agent_activity").insert({
        "agent_id": identity.agent_id,
        "kind": body.kind,
        "summary": summary,
        "ref_id": body.ref_id,
    }).execute()

    return {"ok": True, "activity": ins.data[0] if ins.data else None}

