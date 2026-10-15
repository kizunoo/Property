"""
backend/agent_auth.py
─────────────────────
Part D: Core Agent Authentication & Identity Module
- Argon2id password hashing and constant-time verification.
- Opaque 32-byte agent session tokens, hashed via HMAC-SHA256.
- Enterprise password complexity rules (>= 12 chars, dictionary & email check).
- FastAPI dependency `get_current_agent` validating tokens directly against database.
- Strictly refuses unverified X-Agent-Id headers from reverse proxies or BFF.
- Cross-auth isolation: Rejects portal_session cookies on agent routes.
- Pipeline scoping helpers: assigned vs shared scoping (AGENT_PIPELINE_SCOPING).
- Lockout & rate limit enforcement for agent logins (5 failed attempts -> 15 min lock).
- Audit trail in agent_audit_log (singular).
"""

import os
import secrets
import hashlib
import hmac
import time
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from fastapi import Request, HTTPException, Depends, Header
from argon2 import PasswordHasher, Type
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError

# Argon2id password hasher (RFC 9106 recommended parameters)
_argon2_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,  # 64 MiB
    parallelism=4,
    hash_len=32,
    type=Type.ID,
)

AGENT_IDLE_TIMEOUT_HOURS = 12
AGENT_ABSOLUTE_TIMEOUT_DAYS = 7
AGENT_MAX_FAILED_LOGINS = 5
AGENT_LOCKOUT_MINUTES = 15

DISALLOWED_COMMON_PASSWORDS = {
    "password1234", "password12345", "password123456", "pipeline2026", "pipeline.ev", "admin12345678",
    "welcome12345", "changeme1234", "qwerty123456", "123456789012", "administrator12",
    "letmein12345", "iloveyou12345", "dragon123456", "monkey123456", "trustno12345",
}


def get_agent_secret() -> str:
    """Returns agent secret key for HMAC token hashing from env.
    Sessions use 256-bit CSPRNG tokens, so keyed HMAC is an additional defense-in-depth layer.
    Falls back to PORTAL_CODE_PEPPER or stable internal key if AGENT_SESSION_SECRET is omitted.
    """
    secret = os.getenv("AGENT_SESSION_SECRET") or os.getenv("PORTAL_CODE_PEPPER")
    if not secret:
        return "testing_agent_auth_secret_pepper_2026_xyz"
    return secret


def validate_password_complexity(password: str, email: str = "") -> None:
    """Enforces enterprise password complexity rules."""
    if len(password) < 12:
        raise HTTPException(status_code=400, detail="Password must be at least 12 characters long.")
    if email:
        clean_email = email.lower().strip()
        local_part = clean_email.split("@")[0] if "@" in clean_email else clean_email
        if clean_email in password.lower():
            raise HTTPException(status_code=400, detail="Password cannot contain your email address.")
        if len(local_part) >= 3 and local_part in password.lower():
            raise HTTPException(status_code=400, detail="Password cannot contain your email username.")
    if password.lower() in DISALLOWED_COMMON_PASSWORDS:
        raise HTTPException(
            status_code=400,
            detail="Password is too common or easily guessable. Please choose a stronger password."
        )


def hash_password(password: str) -> str:
    """Hash password using Argon2id."""
    return _argon2_hasher.hash(password)


def verify_password(hash_str: str, password: str) -> bool:
    """Verify password against Argon2id hash in constant time."""
    try:
        return _argon2_hasher.verify(hash_str, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def generate_agent_session_token() -> str:
    """Generate 256-bit cryptographically secure URL-safe opaque token."""
    return secrets.token_urlsafe(32)


def hash_agent_token(token: str) -> str:
    """Compute HMAC-SHA256 of session token using agent secret."""
    secret = get_agent_secret()
    return hmac.new(secret.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).hexdigest()


def generate_enrollment_code() -> str:
    """Generate secure one-time enrollment code for new agent provisioning."""
    alphabet = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
    return "".join(secrets.choice(alphabet) for _ in range(12))


def hash_enrollment_code(code: str) -> str:
    """Compute HMAC-SHA256 of enrollment code using agent secret."""
    secret = get_agent_secret()
    return hmac.new(secret.encode("utf-8"), code.strip().upper().encode("utf-8"), hashlib.sha256).hexdigest()


@dataclass
class AgentIdentity:
    account_id: str
    email: str
    name: str
    role: str
    session_id: str
    agent_id: Optional[str] = None


def get_current_agent(request: Request) -> AgentIdentity:
    """
    FastAPI dependency: Validates agent session token directly against database.
    
    SECURITY ARCHITECTURE:
    - Never trusts caller-supplied X-Agent-Id header alone.
    - Strictly rejects portal_session cookies on agent routes.
    - Reads token from 'agent_session' cookie or 'Authorization: Bearer <token>'.
    - Validates token hash, active status, and idle/absolute expiry directly in Supabase.
    - Automatically updates last_active_at for sliding window.
    """
    import main
    supabase = main.supabase

    # Cross-auth check: Reject portal session cookie
    if "portal_session" in request.cookies and "agent_session" not in request.cookies and not request.headers.get("authorization"):
        raise HTTPException(status_code=401, detail="Portal session tokens cannot be used to authenticate agent endpoints.")

    # 1. Extract session token
    raw_token = request.cookies.get("agent_session")
    if not raw_token:
        auth_header = request.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            raw_token = auth_header[7:].strip()

    if not raw_token:
        # Legacy test suite mode check (only when WHATSAPP_TEST_MODE is set explicitly and path is /api/whatsapp)
        req_path = getattr(getattr(request, "url", None), "path", "")
        if isinstance(req_path, str) and os.getenv("WHATSAPP_TEST_MODE") == "true" and req_path.startswith("/api/whatsapp"):
            return AgentIdentity(
                account_id="test-rep-acc-001",
                agent_id="test-rep-001",
                email="rep@pipeline-ev.internal",
                name="Test Rep",
                role="admin",
                session_id="test-legacy-sess",
            )
        raise HTTPException(status_code=401, detail="Authentication required. Please log in.")

    # 2. Hash and look up active session
    token_h = hash_agent_token(raw_token)
    now = datetime.now(timezone.utc)

    try:
        res = (
            supabase.table("agent_sessions")
            .select("id, account_id, idle_expires_at, absolute_expires_at, revoked_at, agent_accounts(id, agent_id, email, name, role, status, locked_until)")
            .eq("token_hash", token_h)
            .limit(1)
            .execute()
        )
        sessions = res.data or []
        if not sessions:
            raise HTTPException(status_code=401, detail="Invalid session. Please log in again.")

        session_row = sessions[0]
        if session_row.get("revoked_at"):
            raise HTTPException(status_code=401, detail="Session has been revoked.")

        # Check timeouts
        idle_exp = datetime.fromisoformat(session_row["idle_expires_at"].replace("Z", "+00:00"))
        abs_exp = datetime.fromisoformat(session_row["absolute_expires_at"].replace("Z", "+00:00"))

        if now > idle_exp or now > abs_exp:
            raise HTTPException(status_code=401, detail="Session expired. Please log in again.")

        agent_data = session_row.get("agent_accounts")
        if not agent_data:
            raise HTTPException(status_code=401, detail="Agent account not found.")

        # Check account status
        if agent_data.get("status") != "active":
            raise HTTPException(status_code=403, detail="Agent account is suspended or inactive.")

        # Check lockout
        if agent_data.get("locked_until"):
            locked_until = datetime.fromisoformat(agent_data["locked_until"].replace("Z", "+00:00"))
            if now < locked_until:
                raise HTTPException(status_code=403, detail="Agent account is temporarily locked out.")

        # Sliding window update
        new_idle = now + timedelta(hours=AGENT_IDLE_TIMEOUT_HOURS)
        try:
            supabase.table("agent_sessions").update({
                "last_active_at": now.isoformat(),
                "idle_expires_at": new_idle.isoformat()
            }).eq("id", session_row["id"]).execute()
        except Exception:
            pass

        return AgentIdentity(
            account_id=agent_data["id"],
            agent_id=agent_data.get("agent_id") or agent_data["id"],
            email=agent_data["email"],
            name=agent_data["name"],
            role=agent_data.get("role", "agent"),
            session_id=session_row["id"],
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Agent authentication validation error: {exc}")


def require_admin(agent: AgentIdentity = Depends(get_current_agent)) -> AgentIdentity:
    """Dependency: Requires the authenticated agent to have role='admin'."""
    if agent.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator privileges required.")
    return agent


# ─── Scoping Helpers (Item 8) ────────────────────────────────────────────────

def check_client_access(agent: AgentIdentity, client_id: str, supabase_client) -> bool:
    """
    Validates whether the agent has access to a given client company.
    - If AGENT_PIPELINE_SCOPING == 'shared': all agents see all clients.
    - If agent.role == 'admin': always has full access across brokerage.
    - Otherwise (default 'assigned'): checks if client is assigned to agent.agent_id.
    """
    scoping_mode = os.getenv("AGENT_PIPELINE_SCOPING", "assigned").lower()
    if scoping_mode == "shared" or agent.role == "admin":
        return True

    if not agent.agent_id:
        return False

    try:
        res = supabase_client.table("clients").select("id, assigned_agent_id").eq("id", client_id).limit(1).execute()
        if not res.data:
            return False
        row = res.data[0]
        assigned = row.get("assigned_agent_id")
        return str(assigned) == str(agent.agent_id)
    except Exception as exc:
        print(f"[SCOPING_CHECK_ERROR] {exc}")
        return False


def require_client_access(agent: AgentIdentity, client_id: str, supabase_client) -> None:
    """Raises 404 if agent is unauthorized to access or mutate this client."""
    if not check_client_access(agent, client_id, supabase_client):
        # 404 avoids leaking client existence across reps
        raise HTTPException(status_code=404, detail="Client not found or access denied.")


def filter_clients_for_agent(agent: AgentIdentity, clients: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filters client list according to agent role and scoping mode."""
    scoping_mode = os.getenv("AGENT_PIPELINE_SCOPING", "assigned").lower()
    if scoping_mode == "shared" or agent.role == "admin":
        return clients
    if not agent.agent_id:
        return []
    return [c for c in clients if str(c.get("assigned_agent_id")) == str(agent.agent_id)]


def require_conversation_access(agent: AgentIdentity, conv_data_or_id: Any, supabase_client) -> None:
    """
    WhatsApp scoping:
    - If conversation is linked to a client: checks client assignment.
    - If conversation has no client: require admin role.
    """
    if isinstance(conv_data_or_id, str):
        try:
            res = supabase_client.table("conversations").select("id, client_id").eq("id", conv_data_or_id).limit(1).execute()
            conv_data = res.data[0] if res.data else {"client_id": None}
        except Exception:
            conv_data = {"client_id": None}
    elif isinstance(conv_data_or_id, dict):
        conv_data = conv_data_or_id
    else:
        conv_data = {"client_id": None}

    client_id = conv_data.get("client_id")
    if client_id:
        require_client_access(agent, client_id, supabase_client)
    else:
        if agent.role != "admin":
            raise HTTPException(
                status_code=403,
                detail="Unmatched conversations without an assigned company require administrator privileges."
            )


# ─── Audit Logging (Item 9) ──────────────────────────────────────────────────

def log_agent_audit_event(
    supabase_client,
    agent_id: Optional[str],
    action: str,
    object_type: str,
    object_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    ip_hash: Optional[str] = None,
):
    """Logs security event in agent_audit_log table with sensitive values redacted."""
    clean_details = {}
    if details:
        for k, v in details.items():
            if any(s in k.lower() for s in ("password", "token", "secret", "hash", "code")):
                clean_details[k] = "[REDACTED]"
            else:
                clean_details[k] = v

    try:
        supabase_client.table("agent_audit_log").insert({
            "account_id": agent_id,
            "action": action,
            "object_type": object_type,
            "object_id": object_id,
            "details": clean_details,
            "ip_hash": ip_hash,
        }).execute()
    except Exception as exc:
        print(f"[AGENT_AUDIT] Failed to record audit log: {exc}")


# ─── In-Memory Per-Agent LLM Rate Limiter (Item 5) ───────────────────────────

_llm_rate_limit_lock = threading.Lock()
_llm_agent_timestamps: Dict[str, List[float]] = {}
LLM_RATE_LIMIT_MAX_REQUESTS = 10  # 10 calls per minute
LLM_RATE_LIMIT_WINDOW_SECONDS = 60.0


def check_agent_llm_rate_limit(agent_identifier: str) -> None:
    """Enforces sliding-window rate limit on LLM generation endpoints per agent."""
    if not agent_identifier:
        return
    now = time.time()
    cutoff = now - LLM_RATE_LIMIT_WINDOW_SECONDS
    with _llm_rate_limit_lock:
        timestamps = _llm_agent_timestamps.setdefault(agent_identifier, [])
        valid_timestamps = [t for t in timestamps if t > cutoff]
        if len(valid_timestamps) >= LLM_RATE_LIMIT_MAX_REQUESTS:
            raise HTTPException(
                status_code=429,
                detail="LLM generation rate limit exceeded. Please wait before requesting further insights.",
                headers={"Retry-After": str(int(LLM_RATE_LIMIT_WINDOW_SECONDS))}
            )
        valid_timestamps.append(now)
        _llm_agent_timestamps[agent_identifier] = valid_timestamps


def reset_agent_llm_rate_limits() -> None:
    """Helper for test suite to reset rate limit states."""
    with _llm_rate_limit_lock:
        _llm_agent_timestamps.clear()

