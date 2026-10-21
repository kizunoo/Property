"""GET /api/console/inquiry/{inquiry_id}. Agent-session only (RoutePolicy.ANY_AGENT).
Singular 'inquiry' on purpose: it can never collide with /api/console/inquiries/priority.
Scoping is enforced here: a non-admin rep only gets inquiries from their own clients (404 otherwise)."""
from __future__ import annotations

from copilot_routes import _is_admin  # the project's admin check (already adapted)
from copilot_tools import Identity
from fastapi import APIRouter, HTTPException, Request

import inquiry_detail
import triage_service

router = APIRouter()


@router.get("/api/console/inquiry/{inquiry_id}")
def inquiry_detail_route(inquiry_id: str, request: Request):
    agent = getattr(request.state, "agent", None)
    if agent is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    db = triage_service.get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Inquiry view unavailable")
    identity = Identity(agent_id=str(agent.agent_id), is_admin=_is_admin(agent))
    result = inquiry_detail.get_inquiry_detail(db, identity, inquiry_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Inquiry not found")
    return result
