"""GET /api/console/inquiries/priority. Agent-session only (RoutePolicy.ANY_AGENT).
Non-admin reps only ever see inquiries from their own clients."""
from __future__ import annotations

from copilot_routes import _is_admin  # reuse the project's admin check (already adapted)
from copilot_tools import Identity
from fastapi import APIRouter, HTTPException, Request

import triage_service

router = APIRouter()


@router.get("/api/console/inquiries/priority")
def priority_inquiries(request: Request):
    agent = getattr(request.state, "agent", None)
    if agent is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    db = triage_service.get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Triage unavailable")
    identity = Identity(agent_id=str(agent.agent_id), is_admin=_is_admin(agent))
    return {"inquiries": triage_service.list_priority_inquiries(db, identity)}
