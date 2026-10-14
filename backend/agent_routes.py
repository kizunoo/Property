"""
backend/agent_routes.py
───────────────────────
Part D: Agent Authentication API Router
- POST /api/agent/enroll: Redeem one-time enrollment code, set Argon2id password (enforcing password complexity).
- POST /api/agent/login: Authenticate email + password with persistent lockout; set 12h session cookie.
- POST /api/agent/logout: Revoke active session token.
- GET  /api/agent/me: Return validated session identity.
- POST /api/admin/agents/{agent_id}/issue-reset: Admin issues one-time password reset code.
- POST /api/admin/agents/{agent_id}/revoke-all-sessions: Admin revokes all sessions for an agent.
- POST /api/admin/agents/{agent_id}/unlock: Admin clears lockout for an agent.
- POST /api/agent/reset-password: Reset password using one-time reset code.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from fastapi import APIRouter, Request, Response, HTTPException, Depends

from agent_auth import (
    hash_password,
    verify_password,
    generate_agent_session_token,
    hash_agent_token,
    generate_enrollment_code,
    hash_enrollment_code,
    validate_password_complexity,
    get_current_agent,
    require_admin,
    log_agent_audit_event,
    AgentIdentity,
    AGENT_IDLE_TIMEOUT_HOURS,
    AGENT_ABSOLUTE_TIMEOUT_DAYS,
    AGENT_MAX_FAILED_LOGINS,
    AGENT_LOCKOUT_MINUTES,
)
from portal_auth import (
    get_trusted_client_ip,
    hash_rate_limit_key,
    rate_limit_store,
    is_sqlite_rate_limiting_enabled,
    execute_rpc_rate_limit,
)

router = APIRouter()


@router.post("/api/agent/enroll")
def agent_enroll(body: dict, request: Request, response: Response):
    """
    Complete account enrollment using a one-time enrollment code issued by CLI/Admin.
    Sets initial password (Argon2id) and activates the account.
    Enforces minimum 12 chars and dictionary/email checks.
    """
    import main
    supabase = main.supabase

    code = (body.get("enrollment_code") or "").strip().upper()
    password = body.get("password") or ""

    if not code or len(code) < 8:
        raise HTTPException(status_code=400, detail="Valid enrollment code required.")

    code_h = hash_enrollment_code(code)
    now = datetime.now(timezone.utc)

    try:
        res = (
            supabase.table("agent_accounts")
            .select("id, email, name, role, status, enrollment_code_expires_at")
            .eq("enrollment_code_hash", code_h)
            .limit(1)
            .execute()
        )
        accounts = res.data or []
        if not accounts:
            raise HTTPException(status_code=400, detail="Invalid or expired enrollment code.")

        acc = accounts[0]
        if acc.get("status") == "active":
            raise HTTPException(status_code=400, detail="Account is already enrolled. Please log in.")

        exp_str = acc.get("enrollment_code_expires_at")
        if exp_str:
            exp_dt = datetime.fromisoformat(exp_str.replace("Z", "+00:00"))
            if now > exp_dt:
                raise HTTPException(status_code=400, detail="Enrollment code has expired. Request a new one.")

        # Enforce password complexity rules (Item 9)
        validate_password_complexity(password, acc.get("email", ""))

        # Hash new password with Argon2id
        pwd_hash = hash_password(password)

        # Activate account and clear enrollment code
        supabase.table("agent_accounts").update({
            "password_hash": pwd_hash,
            "status": "active",
            "enrollment_code_hash": None,
            "enrollment_code_expires_at": None,
            "failed_login_attempts": 0,
            "locked_until": None,
            "updated_at": now.isoformat(),
        }).eq("id", acc["id"]).execute()

        log_agent_audit_event(
            supabase,
            agent_id=acc["id"],
            action="agent_enrolled",
            object_type="agent_account",
            object_id=acc["id"],
            details={"email": acc["email"]},
            ip_hash=hash_rate_limit_key("ip", get_trusted_client_ip(request)),
        )

        return {"success": True, "message": "Enrollment complete. You may now log in."}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Enrollment failed: {exc}")


@router.post("/api/agent/login")
def agent_login(body: dict, request: Request, response: Response):
    """
    Authenticate agent credentials with Argon2id.
    Enforces brute-force lockout (5 failed attempts -> 15 min lock).
    Issues 12-hour sliding session token and sets HttpOnly cookie.
    """
    import main
    supabase = main.supabase

    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""

    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password are required.")

    client_ip = get_trusted_client_ip(request)
    now = datetime.now(timezone.utc)

    # 1. Rate limit IP attempts (30 attempts / 15m) - DB-backed fail-closed (Item 6)
    ip_key = hash_rate_limit_key("agent_ip", client_ip)
    if not is_sqlite_rate_limiting_enabled():
        attempts, _ = execute_rpc_rate_limit(ip_key, 900)
        if attempts > 30:
            raise HTTPException(status_code=429, detail="Too many failed requests from this IP. Please wait 15 minutes.")
    else:
        allowed, _, _ = rate_limit_store.increment_and_check(
            key_hash=ip_key,
            bucket_type="agent_ip",
            window_seconds=900,
            max_attempts=30,
            lockout_seconds=900,
        )
        if not allowed:
            raise HTTPException(status_code=429, detail="Too many failed requests from this IP. Please wait 15 minutes.")

    # 2. Look up agent account
    try:
        res = (
            supabase.table("agent_accounts")
            .select("id, email, name, role, password_hash, status, failed_login_attempts, locked_until")
            .ilike("email", email)
            .limit(1)
            .execute()
        )
        accounts = res.data or []
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Database query error: {exc}")

    if not accounts:
        raise HTTPException(status_code=401, detail="Invalid credentials.")

    acc = accounts[0]

    # 3. Check account lockout (Item 6: per-account lockout with window and reset-on-expiry)
    if acc.get("locked_until"):
        locked_until = datetime.fromisoformat(acc["locked_until"].replace("Z", "+00:00"))
        if now < locked_until:
            raise HTTPException(
                status_code=403,
                detail=f"Account locked due to multiple failed attempts. Try again after {locked_until.strftime('%H:%M:%S UTC')}."
            )
        else:
            # Lockout expired; reset for new window
            supabase.table("agent_accounts").update({
                "failed_login_attempts": 0,
                "locked_until": None,
            }).eq("id", acc["id"]).execute()
            acc["failed_login_attempts"] = 0

    if acc.get("status") != "active":
        raise HTTPException(status_code=403, detail="Account is pending enrollment or suspended.")

    # 4. Verify Argon2id password
    pwd_valid = verify_password(acc["password_hash"], password)
    if not pwd_valid:
        # Increment failed attempts
        failed_count = (acc.get("failed_login_attempts") or 0) + 1
        new_lock = None
        if failed_count >= AGENT_MAX_FAILED_LOGINS:
            new_lock = now + timedelta(minutes=AGENT_LOCKOUT_MINUTES)

        supabase.table("agent_accounts").update({
            "failed_login_attempts": failed_count,
            "locked_until": new_lock.isoformat() if new_lock else None,
        }).eq("id", acc["id"]).execute()

        log_agent_audit_event(
            supabase,
            agent_id=acc["id"],
            action="login_failed",
            object_type="agent_account",
            details={"attempt": failed_count, "locked": bool(new_lock)},
            ip_hash=hash_rate_limit_key("ip", client_ip),
        )

        if new_lock:
            raise HTTPException(
                status_code=403,
                detail=f"Too many failed login attempts. Account locked for {AGENT_LOCKOUT_MINUTES} minutes."
            )
        raise HTTPException(status_code=401, detail="Invalid credentials.")

    # 5. Success! Clear lockout counters
    supabase.table("agent_accounts").update({
        "failed_login_attempts": 0,
        "locked_until": None,
        "last_login_at": now.isoformat(),
    }).eq("id", acc["id"]).execute()

    # 6. Issue opaque 32-byte session token
    raw_token = generate_agent_session_token()
    token_h = hash_agent_token(raw_token)

    idle_exp = now + timedelta(hours=AGENT_IDLE_TIMEOUT_HOURS)
    abs_exp = now + timedelta(days=AGENT_ABSOLUTE_TIMEOUT_DAYS)

    session_row = {
        "agent_id": acc["id"],
        "token_hash": token_h,
        "idle_expires_at": idle_exp.isoformat(),
        "absolute_expires_at": abs_exp.isoformat(),
        "last_active_at": now.isoformat(),
        "ip_hash": hash_rate_limit_key("ip", client_ip),
        "user_agent": request.headers.get("user-agent", "")[:255],
    }

    sess_res = supabase.table("agent_sessions").insert(session_row).execute()
    session_id = sess_res.data[0]["id"] if sess_res.data else "new"

    # Set secure HTTP-only cookie
    is_prod = os.getenv("ENVIRONMENT", "").lower() in ("production", "prod")
    response.set_cookie(
        key="agent_session",
        value=raw_token,
        httponly=True,
        secure=is_prod,
        samesite="lax",
        max_age=AGENT_IDLE_TIMEOUT_HOURS * 3600,
        path="/",
    )

    log_agent_audit_event(
        supabase,
        agent_id=acc["id"],
        action="login_success",
        object_type="session",
        object_id=session_id,
        ip_hash=hash_rate_limit_key("ip", client_ip),
    )

    return {
        "success": True,
        "token": raw_token,
        "agent": {
            "id": acc["id"],
            "email": acc["email"],
            "name": acc["name"],
            "role": acc["role"],
        },
        "expires_at": idle_exp.isoformat(),
    }


@router.post("/api/agent/logout")
def agent_logout(response: Response, current_agent: AgentIdentity = Depends(get_current_agent)):
    """Revokes active agent session and clears cookie."""
    import main
    supabase = main.supabase

    now = datetime.now(timezone.utc)
    try:
        supabase.table("agent_sessions").update({
            "revoked_at": now.isoformat()
        }).eq("id", current_agent.session_id).execute()

        response.delete_cookie(key="agent_session", path="/")

        log_agent_audit_event(
            supabase,
            agent_id=current_agent.agent_id,
            action="logout",
            object_type="session",
            object_id=current_agent.session_id,
        )
        return {"success": True, "message": "Logged out successfully."}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Logout failed: {exc}")


@router.get("/api/agent/me")
def agent_me(current_agent: AgentIdentity = Depends(get_current_agent)):
    """Returns validated profile of currently authenticated agent."""
    return {
        "authenticated": True,
        "agent_id": current_agent.agent_id,
        "email": current_agent.email,
        "name": current_agent.name,
        "role": current_agent.role,
        "session_id": current_agent.session_id,
    }


@router.post("/api/admin/agents/{agent_id}/issue-reset")
def admin_issue_reset_code(
    agent_id: str,
    admin: AgentIdentity = Depends(require_admin),
):
    """Admin-only: Issue a single-use 24-hour password reset code for an agent."""
    import main
    supabase = main.supabase

    res = supabase.table("agent_accounts").select("id, email, name").eq("id", agent_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Agent account not found.")

    acc = res.data[0]
    reset_code = generate_enrollment_code()
    reset_h = hash_enrollment_code(reset_code)
    now = datetime.now(timezone.utc)
    exp = now + timedelta(hours=24)

    supabase.table("agent_accounts").update({
        "reset_code_hash": reset_h,
        "reset_code_expires_at": exp.isoformat(),
        "failed_login_attempts": 0,
        "locked_until": None,
    }).eq("id", agent_id).execute()

    log_agent_audit_event(
        supabase,
        agent_id=admin.agent_id,
        action="admin_issued_password_reset",
        object_type="agent_account",
        object_id=agent_id,
        details={"target_email": acc["email"]},
    )

    return {
        "success": True,
        "agent_id": agent_id,
        "agent_email": acc["email"],
        "reset_code": reset_code,
        "expires_at": exp.isoformat(),
        "message": f"One-time reset code generated for {acc['name']}. Provide it securely to the agent."
    }


@router.post("/api/admin/agents/{agent_id}/revoke-all-sessions")
def admin_revoke_all_sessions(
    agent_id: str,
    admin: AgentIdentity = Depends(require_admin),
):
    """Admin-only: Revoke all active sessions for an agent (Item 9)."""
    import main
    supabase = main.supabase

    now = datetime.now(timezone.utc)
    try:
        supabase.table("agent_sessions").update({
            "revoked_at": now.isoformat()
        }).eq("agent_id", agent_id).is_("revoked_at", None).execute()

        log_agent_audit_event(
            supabase,
            agent_id=admin.agent_id,
            action="admin_revoked_all_agent_sessions",
            object_type="agent_account",
            object_id=agent_id,
        )
        return {"success": True, "message": "All active sessions revoked for agent."}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to revoke sessions: {exc}")


@router.post("/api/admin/agents/{agent_id}/unlock")
def admin_unlock_agent(
    agent_id: str,
    admin: AgentIdentity = Depends(require_admin),
):
    """Admin-only: Unlock a locked agent account (Item 6)."""
    import main
    supabase = main.supabase

    try:
        supabase.table("agent_accounts").update({
            "failed_login_attempts": 0,
            "locked_until": None,
        }).eq("id", agent_id).execute()

        log_agent_audit_event(
            supabase,
            agent_id=admin.agent_id,
            action="admin_unlocked_agent",
            object_type="agent_account",
            object_id=agent_id,
        )
        return {"success": True, "message": "Agent account unlocked successfully."}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to unlock agent: {exc}")


@router.post("/api/admin/agents/{agent_id}/suspend")
def admin_suspend_agent(
    agent_id: str,
    admin: AgentIdentity = Depends(require_admin),
):
    """Admin-only: Suspend an agent account and revoke all active sessions (Item 7)."""
    import main
    supabase = main.supabase
    now = datetime.now(timezone.utc)

    try:
        supabase.table("agent_accounts").update({
            "status": "suspended",
            "updated_at": now.isoformat(),
        }).eq("id", agent_id).execute()

        # Revoke all active sessions
        supabase.table("agent_sessions").update({
            "revoked_at": now.isoformat()
        }).eq("agent_id", agent_id).is_("revoked_at", None).execute()

        log_agent_audit_event(
            supabase,
            agent_id=admin.agent_id,
            action="admin_suspended_agent",
            object_type="agent_account",
            object_id=agent_id,
        )
        return {"success": True, "message": "Agent account suspended and sessions revoked."}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to suspend agent: {exc}")


@router.post("/api/admin/agents/{agent_id}/reactivate")
def admin_reactivate_agent(
    agent_id: str,
    admin: AgentIdentity = Depends(require_admin),
):
    """Admin-only: Reactivate a suspended agent account (Item 7)."""
    import main
    supabase = main.supabase
    now = datetime.now(timezone.utc)

    try:
        supabase.table("agent_accounts").update({
            "status": "active",
            "failed_login_attempts": 0,
            "locked_until": None,
            "updated_at": now.isoformat(),
        }).eq("id", agent_id).execute()

        log_agent_audit_event(
            supabase,
            agent_id=admin.agent_id,
            action="admin_reactivated_agent",
            object_type="agent_account",
            object_id=agent_id,
        )
        return {"success": True, "message": "Agent account reactivated successfully."}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to reactivate agent: {exc}")


@router.post("/api/agent/reset-password")
def agent_reset_password(body: dict, request: Request = None):
    """Redeem one-time reset code and set new Argon2id password."""
    import main
    supabase = main.supabase

    code = (body.get("reset_code") or "").strip().upper()
    new_password = body.get("new_password") or ""

    if not code or len(code) < 8:
        raise HTTPException(status_code=400, detail="Valid reset code required.")

    code_h = hash_enrollment_code(code)
    now = datetime.now(timezone.utc)

    res = (
        supabase.table("agent_accounts")
        .select("id, email, reset_code_expires_at")
        .eq("reset_code_hash", code_h)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=400, detail="Invalid or expired reset code.")

    acc = res.data[0]
    exp_str = acc.get("reset_code_expires_at")
    if exp_str:
        exp_dt = datetime.fromisoformat(exp_str.replace("Z", "+00:00"))
        if now > exp_dt:
            raise HTTPException(status_code=400, detail="Reset code has expired. Request a new one from an admin.")

    # Enforce password complexity rules (Item 9)
    validate_password_complexity(new_password, acc.get("email", ""))

    pwd_hash = hash_password(new_password)

    # Invalidate all existing sessions for this agent
    supabase.table("agent_sessions").update({
        "revoked_at": now.isoformat()
    }).eq("agent_id", acc["id"]).execute()

    # Update password and clear reset code
    supabase.table("agent_accounts").update({
        "password_hash": pwd_hash,
        "reset_code_hash": None,
        "reset_code_expires_at": None,
        "failed_login_attempts": 0,
        "locked_until": None,
        "updated_at": now.isoformat(),
    }).eq("id", acc["id"]).execute()

    log_agent_audit_event(
        supabase,
        agent_id=acc["id"],
        action="password_reset_completed",
        object_type="agent_account",
        object_id=acc["id"],
    )

    return {"success": True, "message": "Password reset successfully. Please log in with your new password."}
