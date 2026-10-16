"""POST /api/console/copilot. Agent-session only (RoutePolicy.ANY_AGENT)."""
from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter()
log = logging.getLogger("copilot")
_hits: dict[str, deque] = defaultdict(deque)
RATE_LIMIT, WINDOW_S, TIMEOUT_S = 20, 3600, 45


class CopilotRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    conversation_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


def _is_admin(agent) -> bool:  # ADAPT-ME: use the project's existing admin check
    return getattr(agent, "role", None) == "admin"


def _rate_limited(agent_id: str) -> bool:
    now, q = time.time(), _hits[agent_id]
    while q and now - q[0] > WINDOW_S:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        return True
    q.append(now)
    return False


@router.post("/api/console/copilot")
async def copilot(body: CopilotRequest, request: Request):
    agent = getattr(request.state, "agent", None)
    if agent is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    agent_id = str(agent.agent_id)
    if _rate_limited(agent_id):
        raise HTTPException(status_code=429, detail="Copilot limit reached, try later")
    from copilot_agent import run_copilot  # lazy: app still boots if ADK is not installed
    try:
        reply = await asyncio.wait_for(
            run_copilot(agent_id, _is_admin(agent), body.conversation_id, body.message),
            timeout=TIMEOUT_S)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Copilot timed out")
    except Exception as e:  # noqa: BLE001
        log.error("copilot failed: %s", type(e).__name__)  # never log message content
        raise HTTPException(status_code=502, detail="Copilot unavailable")
    return {"reply": reply}
