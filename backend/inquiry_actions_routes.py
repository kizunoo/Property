"""
Rep-side inquiry actions. All agent-session only (RoutePolicy.ANY_AGENT); scoping is enforced inside the
service functions (a non-admin rep only reaches their own clients; everything else is a plain 404).

  POST /api/console/inquiry/{inquiry_id}/resolve        body: {"note": optional text <= 500}
  POST /api/console/inquiry/{inquiry_id}/reopen
  GET  /api/console/clients/{client_id}/inquiry-history
  POST /api/console/inquiry/{inquiry_id}/suggest-reply  (AI draft; never sends anything)
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from typing import Optional

from copilot_routes import _is_admin  # the project's admin check (already adapted)
from copilot_tools import Identity
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

import inquiry_resolution
import triage_service

router = APIRouter()
log = logging.getLogger("inquiry_actions")
_hits: dict = defaultdict(deque)
SUGGEST_LIMIT, SUGGEST_WINDOW_S = 30, 3600


class ResolveBody(BaseModel):
    note: Optional[str] = Field(default=None, max_length=500)


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


def _audit(db, identity: Identity, action: str, object_id: str) -> None:
    try:  # best effort: auditing must never block the action, and never records message text
        from agent_routes import log_agent_audit_event
        log_agent_audit_event(db, agent_id=identity.agent_id, action=action,
                              object_type="client_inquiry", object_id=object_id)
    except Exception as e:  # noqa: BLE001
        log.warning("audit failed: %s", type(e).__name__)


@router.post("/api/console/inquiry/{inquiry_id}/resolve")
def resolve(inquiry_id: str, body: ResolveBody, request: Request):
    identity, db = _identity(request), _db()
    result = inquiry_resolution.resolve_inquiry(db, identity, inquiry_id, body.note)
    if result == "not_found":
        raise HTTPException(status_code=404, detail="Inquiry not found")
    if result == "already_resolved":
        raise HTTPException(status_code=409, detail="Inquiry is already resolved")
    _audit(db, identity, "inquiry_resolved", inquiry_id)
    return {"ok": True}


@router.post("/api/console/inquiry/{inquiry_id}/reopen")
def reopen(inquiry_id: str, request: Request):
    identity, db = _identity(request), _db()
    result = inquiry_resolution.reopen_inquiry(db, identity, inquiry_id)
    if result == "not_found":
        raise HTTPException(status_code=404, detail="Inquiry not found")
    if result == "not_resolved":
        raise HTTPException(status_code=409, detail="Inquiry is not resolved")
    _audit(db, identity, "inquiry_reopened", inquiry_id)
    return {"ok": True}


@router.get("/api/console/clients/{client_id}/inquiry-history")
def history(client_id: str, request: Request):
    identity, db = _identity(request), _db()
    result = inquiry_resolution.list_company_history(db, identity, client_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return result


@router.post("/api/console/inquiry/{inquiry_id}/suggest-reply")
async def suggest(inquiry_id: str, request: Request):
    identity, db = _identity(request), _db()
    now, q = time.time(), _hits[identity.agent_id]
    while q and now - q[0] > SUGGEST_WINDOW_S:
        q.popleft()
    if len(q) >= SUGGEST_LIMIT:
        raise HTTPException(status_code=429, detail="Suggestion limit reached, try later")
    q.append(now)
    from inquiry_detail import get_inquiry_detail
    if get_inquiry_detail(db, identity, inquiry_id) is None:   # scoped existence check before any AI call
        raise HTTPException(status_code=404, detail="Inquiry not found")
    try:
        import reply_agent  # lazy: the app still boots if ADK is missing
        result = await reply_agent.suggest_reply(identity, inquiry_id)
    except Exception as e:  # noqa: BLE001
        log.error("suggest-reply failed: %s", type(e).__name__)  # never log message content
        raise HTTPException(status_code=502, detail="AI suggestion unavailable")
    if result is None:
        raise HTTPException(status_code=502, detail="AI suggestion unavailable")
    _audit(db, identity, "inquiry_reply_suggested", inquiry_id)
    return result
