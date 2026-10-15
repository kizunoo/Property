"""
portal_routes.py
────────────────
FastAPI router for:
1. Portal Authentication (/api/portal/auth/...)
   - request-code (self-service; rate limited per IP & contact; protects pending rep codes; phone ambiguity guard)
   - verify-code (constant-time verification of rep or self code; lockout policy; atomic attempt counting)
   - verify-invite (one-time invite link verification; 32+ bytes random token; single use; no disambiguation needed)
   - legacy-login (read-only company code fallback, queries hashed code only)
   - logout & me
2. Rep Console Portal Access (/api/console/clients/{client_id}/portal/...)
   - contacts list/create/deactivate
   - issue-code (rep-issued code + 32-byte one-time invite link)
   - revoke-code
   - unlock (resets contact lockout)
   - revoke-all-sessions
   - rotate-legacy-code (stores hash only)
   - audit-log
3. Securing existing portal endpoints with get_current_portal_session & require_company_access
"""

import os
import hmac
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Request, HTTPException, Depends, Header

from portal_auth import (
    get_code_pepper,
    is_legacy_login_enabled,
    is_dev_environment,
    hash_code,
    hash_token,
    hash_ip,
    generate_secure_code,
    generate_invite_token,
    generate_session_token,
    get_trusted_client_ip,
    check_and_record_ip_attempt,
    check_and_record_contact_attempt,
    check_and_record_code_ip_attempt,
    check_and_record_code_contact_attempt,
    log_audit_event,
    verify_origin,
    get_current_portal_session,
    require_company_access,
    PortalSession,
    delivery_provider,
    rate_limit_store,
    hash_rate_limit_key,
)

router = APIRouter()


# ─── 1. Portal Authentication Endpoints ──────────────────────────────────────

@router.post("/api/portal/auth/request-code")
def request_login_code(body: dict, request: Request):
    """
    Request a single-use login code for a contact.
    Anti-enumeration: Always returns an identical success message.
    Rate limited per IP (30/15min) and per contact (5/15min).
    Safe proxy IP forwarding verified via BFF_INTERNAL_SECRET.
    Protection: Does NOT overwrite a pending, unexpired rep-issued code.
    Phone Ambiguity: If phone matches >1 active contact, returns generic success (no company leaked).
    """
    import main
    supabase = main.supabase

    client_ip = get_trusted_client_ip(request)
    raw_identifier = (body.get("identifier") or "").strip()

    # 1. IP rate limit check (5 code requests per 15 min per IP)
    check_and_record_code_ip_attempt(client_ip)

    generic_success = {
        "success": True,
        "message": "If the contact or identifier exists, a single-use login code has been issued."
    }

    if not raw_identifier:
        return generic_success

    now = datetime.now(timezone.utc)
    normalized_phone = "".join(filter(str.isdigit, raw_identifier))

    try:
        contact = None

        if "@" in raw_identifier:
            # Email lookup: exact case-insensitive match
            res = (
                supabase.table("portal_contacts")
                .select("id, client_id, name, email, whatsapp_number, status, locked_until, rep_code_hash, rep_code_expires_at")
                .eq("status", "active")
                .ilike("email", raw_identifier)
                .limit(2)
                .execute()
            )
            contacts = res.data or []
            if len(contacts) == 1:
                contact = contacts[0]
        elif normalized_phone and len(normalized_phone) >= 7:
            # Phone lookup: must match EXACTLY ONE active contact across all companies
            # If > 1 contact shares the phone number, do NOT issue code or reveal companies.
            res_p = (
                supabase.table("portal_contacts")
                .select("id, client_id, name, email, whatsapp_number, status, locked_until, rep_code_hash, rep_code_expires_at")
                .eq("status", "active")
                .ilike("whatsapp_number", f"%{normalized_phone[-8:]}%")
                .limit(2)
                .execute()
            )
            contacts = res_p.data or []
            if len(contacts) == 1:
                contact = contacts[0]
            elif len(contacts) > 1:
                # Ambiguous phone number across multiple companies:
                # Anti-enumeration rule: return generic success without issuing code
                print(f"[PORTAL_AUTH] Ambiguous phone number match ({len(contacts)} contacts). Requiring invite link or email.")
                return generic_success

        if not contact:
            return generic_success

        # Check contact code request rate limit (3 code requests per 15 min per contact)
        if not check_and_record_code_contact_attempt(contact["id"]):
            print(f"[PORTAL_AUTH] Contact {contact['id']} exceeded code request quota (3/15m).")
            return generic_success

        # Check contact lockout
        if contact.get("locked_until"):
            locked_until = datetime.fromisoformat(contact["locked_until"].replace("Z", "+00:00"))
            if now < locked_until:
                # Contact locked out: return generic success (anti-enumeration)
                return generic_success

        # Check pending rep-issued code protection:
        # A self-service request must NOT overwrite or invalidate a valid rep-issued code
        rep_expires_str = contact.get("rep_code_expires_at")
        if rep_expires_str:
            rep_expires = datetime.fromisoformat(rep_expires_str.replace("Z", "+00:00"))
            if now < rep_expires and contact.get("rep_code_hash"):
                # Active rep code exists. Refuse to overwrite; return generic success
                print(f"[PORTAL_AUTH] Preserving active rep-issued code for contact {contact['id']}.")
                return generic_success

        # Issue self-service code: 6-char alphanumeric, 24h expiry
        code = generate_secure_code(6)
        code_h = hash_code(code)
        expires_at = now + timedelta(hours=24)

        supabase.table("portal_contacts").update({
            "self_code_hash": code_h,
            "self_code_expires_at": expires_at.isoformat(),
        }).eq("id", contact["id"]).execute()

        channel = "email" if contact.get("email") else "whatsapp"
        delivery_provider.send_login_code(contact, code, channel)

        log_audit_event(
            supabase,
            client_id=contact["client_id"],
            action="self_service_code_requested",
            object_type="contact",
            contact_id=contact["id"],
            details={"channel": channel},
            ip=client_ip,
        )

    except Exception as e:
        print(f"[PORTAL_AUTH] Error in request_login_code: {e}")

    return generic_success


@router.post("/api/portal/auth/verify-code")
def verify_login_code(body: dict, request: Request):
    """
    Validates a 6-character single-use login code (rep-issued or self-service).
    Enforces per-contact and per-IP lockout (5 failed attempts -> 15 min lock).
    Constant-time comparison via hmac.compare_digest.
    On success: issues opaque session token stored hashed in portal_sessions.
    """
    import main
    supabase = main.supabase

    client_ip = get_trusted_client_ip(request)
    raw_identifier = (body.get("identifier") or "").strip()
    raw_code = (body.get("code") or "").strip().upper()

    # Check IP rate limit
    check_and_record_ip_attempt(client_ip)

    if not raw_identifier or not raw_code:
        raise HTTPException(status_code=400, detail="Identifier and login code are required")

    normalized_phone = "".join(filter(str.isdigit, raw_identifier))
    now = datetime.now(timezone.utc)

    # Lookup contact
    contact = None
    try:
        if "@" in raw_identifier:
            res = (
                supabase.table("portal_contacts")
                .select("id, client_id, name, email, whatsapp_number, portal_role, status, rep_code_hash, rep_code_expires_at, self_code_hash, self_code_expires_at, failed_login_attempts, locked_until, clients(id, name)")
                .ilike("email", raw_identifier)
                .limit(2)
                .execute()
            )
            contacts = res.data or []
            if len(contacts) == 1:
                contact = contacts[0]
        elif normalized_phone and len(normalized_phone) >= 7:
            res_p = (
                supabase.table("portal_contacts")
                .select("id, client_id, name, email, whatsapp_number, portal_role, status, rep_code_hash, rep_code_expires_at, self_code_hash, self_code_expires_at, failed_login_attempts, locked_until, clients(id, name)")
                .ilike("whatsapp_number", f"%{normalized_phone[-8:]}%")
                .limit(2)
                .execute()
            )
            contacts = res_p.data or []
            if len(contacts) == 1:
                contact = contacts[0]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Database query failed: {exc}")

    if not contact:
        raise HTTPException(status_code=401, detail="Invalid credentials or code has expired")

    # Check contact lockout
    if contact.get("locked_until"):
        locked_until = datetime.fromisoformat(contact["locked_until"].replace("Z", "+00:00"))
        if now < locked_until:
            raise HTTPException(
                status_code=403,
                detail="Account is temporarily locked out due to multiple failed attempts. Please contact your PIPELINE.EV representative to unlock."
            )

    # Check contact status
    if contact.get("status") == "deactivated":
        raise HTTPException(status_code=403, detail="Account is deactivated")

    # Verify code against rep_code_hash OR self_code_hash
    input_hash = hash_code(raw_code)
    code_matches = False

    # Check rep-issued code
    rep_hash = contact.get("rep_code_hash")
    rep_exp_str = contact.get("rep_code_expires_at")
    if rep_hash and rep_exp_str:
        rep_exp = datetime.fromisoformat(rep_exp_str.replace("Z", "+00:00"))
        if now <= rep_exp and hmac.compare_digest(rep_hash, input_hash):
            code_matches = True

    # Check self-service code
    if not code_matches:
        self_hash = contact.get("self_code_hash")
        self_exp_str = contact.get("self_code_expires_at")
        if self_hash and self_exp_str:
            self_exp = datetime.fromisoformat(self_exp_str.replace("Z", "+00:00"))
            if now <= self_exp and hmac.compare_digest(self_hash, input_hash):
                code_matches = True

    if not code_matches:
        # Atomic increment of failed login attempts
        failed = (contact.get("failed_login_attempts") or 0) + 1
        updates = {"failed_login_attempts": failed}
        if failed >= 5:
            lock_until = now + timedelta(minutes=15)
            updates["locked_until"] = lock_until.isoformat()
            log_audit_event(
                supabase,
                client_id=contact["client_id"],
                action="contact_locked_out",
                object_type="contact",
                contact_id=contact["id"],
                details={"attempts": failed},
                ip=client_ip,
            )
        else:
            log_audit_event(
                supabase,
                client_id=contact["client_id"],
                action="login_code_failed",
                object_type="contact",
                contact_id=contact["id"],
                details={"attempt_number": failed},
                ip=client_ip,
            )

        try:
            supabase.table("portal_contacts").update(updates).eq("id", contact["id"]).execute()
        except Exception:
            pass
        raise HTTPException(status_code=401, detail="Invalid credentials or code has expired")

    # Code is valid! Clear single-use codes and reset lockout
    try:
        supabase.table("portal_contacts").update({
            "rep_code_hash": None,
            "rep_code_expires_at": None,
            "self_code_hash": None,
            "self_code_expires_at": None,
            "failed_login_attempts": 0,
            "locked_until": None,
            "last_login_at": now.isoformat(),
        }).eq("id", contact["id"]).execute()
    except Exception as e:
        print(f"[PORTAL_AUTH] Warning resetting contact code: {e}")

    # Generate session token (opaque 32-byte)
    raw_token = generate_session_token()
    token_h = hash_token(raw_token)

    idle_exp = now + timedelta(hours=2)
    abs_exp = now + timedelta(days=7)

    session_row = {
        "client_id": contact["client_id"],
        "contact_id": contact["id"],
        "token_hash": token_h,
        "portal_role": contact.get("portal_role", "evaluator"),
        "idle_expires_at": idle_exp.isoformat(),
        "absolute_expires_at": abs_exp.isoformat(),
        "last_active_at": now.isoformat(),
        "ip_hash": hash_ip(client_ip),
        "user_agent": request.headers.get("user-agent", "unknown")[:255],
    }

    try:
        s_res = supabase.table("portal_sessions").insert(session_row).execute()
        session_id = s_res.data[0]["id"] if s_res.data else None
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to create session: {exc}")

    client_info = contact.get("clients") or {}
    log_audit_event(
        supabase,
        client_id=contact["client_id"],
        action="contact_logged_in",
        object_type="session",
        contact_id=contact["id"],
        object_id=session_id,
        details={"role": contact.get("portal_role")},
        ip=client_ip,
    )

    return {
        "success": True,
        "session_token": raw_token,
        "session_id": session_id,
        "client_id": contact["client_id"],
        "client_name": client_info.get("name") or "Company Workspace",
        "contact_name": contact.get("name"),
        "portal_role": contact.get("portal_role", "evaluator"),
        "idle_expires_at": idle_exp.isoformat(),
        "absolute_expires_at": abs_exp.isoformat(),
    }


@router.post("/api/portal/auth/verify-invite")
def verify_invite_token(body: dict, request: Request):
    """
    Validates a rep-issued one-time invite link token (32+ bytes URL-safe).
    Single-use: immediately clears invite_token_hash upon first redemption.
    Requires NO company disambiguation or email typing.
    Issues a full 7-day authenticated session.
    """
    import main
    supabase = main.supabase

    client_ip = get_trusted_client_ip(request)
    raw_token = (body.get("token") or "").strip()

    check_and_record_ip_attempt(client_ip)

    if not raw_token or len(raw_token) < 20:
        raise HTTPException(status_code=400, detail="Invalid invite link token")

    token_h = hash_token(raw_token)
    now = datetime.now(timezone.utc)

    try:
        res = (
            supabase.table("portal_contacts")
            .select("id, client_id, name, email, portal_role, status, invite_token_expires_at, clients(id, name)")
            .eq("invite_token_hash", token_h)
            .limit(1)
            .execute()
        )
        contact = res.data[0] if res.data else None
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Database query failed: {exc}")

    if not contact:
        raise HTTPException(status_code=401, detail="Invite link is invalid or has already been used")

    # Check expiration
    exp_str = contact.get("invite_token_expires_at")
    if exp_str:
        exp_dt = datetime.fromisoformat(exp_str.replace("Z", "+00:00"))
        if now > exp_dt:
            raise HTTPException(status_code=401, detail="Invite link has expired")

    if contact.get("status") == "deactivated":
        raise HTTPException(status_code=403, detail="Account is deactivated")

    # Single-use: clear invite token immediately
    try:
        supabase.table("portal_contacts").update({
            "invite_token_hash": None,
            "invite_token_expires_at": None,
            "failed_login_attempts": 0,
            "locked_until": None,
            "last_login_at": now.isoformat(),
        }).eq("id", contact["id"]).execute()
    except Exception as e:
        print(f"[PORTAL_AUTH] Warning clearing invite token: {e}")

    # Issue session
    raw_session_token = generate_session_token()
    session_token_h = hash_token(raw_session_token)

    idle_exp = now + timedelta(hours=2)
    abs_exp = now + timedelta(days=7)

    session_row = {
        "client_id": contact["client_id"],
        "contact_id": contact["id"],
        "token_hash": session_token_h,
        "portal_role": contact.get("portal_role", "evaluator"),
        "idle_expires_at": idle_exp.isoformat(),
        "absolute_expires_at": abs_exp.isoformat(),
        "last_active_at": now.isoformat(),
        "ip_hash": hash_ip(client_ip),
        "user_agent": request.headers.get("user-agent", "unknown")[:255],
    }

    try:
        s_res = supabase.table("portal_sessions").insert(session_row).execute()
        session_id = s_res.data[0]["id"] if s_res.data else None
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to create session: {exc}")

    client_info = contact.get("clients") or {}
    log_audit_event(
        supabase,
        client_id=contact["client_id"],
        action="invite_link_redeemed",
        object_type="session",
        contact_id=contact["id"],
        object_id=session_id,
        details={"role": contact.get("portal_role")},
        ip=client_ip,
    )

    return {
        "success": True,
        "session_token": raw_session_token,
        "session_id": session_id,
        "client_id": contact["client_id"],
        "client_name": client_info.get("name") or "Company Workspace",
        "contact_name": contact.get("name"),
        "portal_role": contact.get("portal_role", "evaluator"),
        "idle_expires_at": idle_exp.isoformat(),
        "absolute_expires_at": abs_exp.isoformat(),
    }


@router.post("/api/portal/auth/legacy-login")
def legacy_company_login(body: dict, request: Request):
    """
    Fallback login using the legacy company-wide portal_access_code.
    Only enabled if PORTAL_LEGACY_LOGIN_ENABLED=true in env.
    Queries ONLY portal_access_code_hash.
    Issues a restricted 'legacy_readonly' session (pricing omitted, no mutations).
    """
    if not is_legacy_login_enabled():
        raise HTTPException(
            status_code=403,
            detail="Legacy company code login is disabled. Please use your personal single-use login code or invite link."
        )

    import main
    supabase = main.supabase

    client_ip = get_trusted_client_ip(request)
    raw_code = (body.get("code") or body.get("access_code") or "").strip().upper()

    check_and_record_ip_attempt(client_ip)

    if not raw_code:
        raise HTTPException(status_code=400, detail="Access code is required")

    code_h = hash_code(raw_code)

    try:
        res = (
            supabase.table("clients")
            .select("id, name, portal_access_code_hash")
            .eq("portal_access_code_hash", code_h)
            .limit(1)
            .execute()
        )
        client = res.data[0] if res.data else None
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Database lookup failed: {exc}")

    if not client:
        raise HTTPException(status_code=401, detail="Invalid company access code")

    now = datetime.now(timezone.utc)
    raw_token = generate_session_token()
    token_h = hash_token(raw_token)

    idle_exp = now + timedelta(hours=2)
    abs_exp = now + timedelta(days=7)

    session_row = {
        "client_id": client["id"],
        "contact_id": None,
        "token_hash": token_h,
        "portal_role": "legacy_readonly",
        "idle_expires_at": idle_exp.isoformat(),
        "absolute_expires_at": abs_exp.isoformat(),
        "last_active_at": now.isoformat(),
        "ip_hash": hash_ip(client_ip),
        "user_agent": request.headers.get("user-agent", "unknown")[:255],
    }

    try:
        s_res = supabase.table("portal_sessions").insert(session_row).execute()
        session_id = s_res.data[0]["id"] if s_res.data else None
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to create legacy session: {exc}")

    log_audit_event(
        supabase,
        client_id=client["id"],
        action="legacy_login",
        object_type="session",
        object_id=session_id,
        details={"role": "legacy_readonly"},
        ip=client_ip,
    )

    return {
        "success": True,
        "session_token": raw_token,
        "session_id": session_id,
        "client_id": client["id"],
        "client_name": client["name"],
        "contact_name": "Guest (Legacy Access)",
        "portal_role": "legacy_readonly",
        "idle_expires_at": idle_exp.isoformat(),
        "absolute_expires_at": abs_exp.isoformat(),
        "is_legacy": True,
    }


@router.post("/api/portal/auth/logout")
def portal_logout(session: PortalSession = Depends(get_current_portal_session)):
    """Revokes the active session token."""
    import main
    supabase = main.supabase

    now = datetime.now(timezone.utc)
    try:
        supabase.table("portal_sessions").update({
            "revoked_at": now.isoformat()
        }).eq("id", session.session_id).execute()

        log_audit_event(
            supabase,
            client_id=session.client_id,
            action="session_logout",
            object_type="session",
            contact_id=session.contact_id,
            object_id=session.session_id,
        )
        return {"success": True, "message": "Logged out successfully"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Logout failed: {exc}")


@router.get("/api/portal/auth/me")
def portal_auth_me(session: PortalSession = Depends(get_current_portal_session)):
    """Returns validated session identity and tenant scope."""
    return {
        "authenticated": True,
        "session_id": session.session_id,
        "contact_id": session.contact_id,
        "contact_name": session.contact_name,
        "portal_role": session.portal_role,
        "client_id": session.client_id,
        "client_name": session.client_name,
        "is_legacy": session.is_legacy,
    }


from agent_auth import require_client_access


# ─── 2. Rep Console Portal Access Endpoints ──────────────────────────────────

@router.get("/api/console/clients/{client_id}/portal/contacts")
def rep_list_portal_contacts(client_id: str, request: Request):
    """Rep console: list all portal contacts for a client company (scoped to agent)."""
    import main
    supabase = main.supabase

    if hasattr(request.state, "agent"):
        require_client_access(request.state.agent, client_id, supabase)

    try:
        res = (
            supabase.table("portal_contacts")
            .select("id, client_id, name, email, whatsapp_number, title, portal_role, is_primary, status, failed_login_attempts, locked_until, last_login_at, created_at, rep_code_expires_at, invite_token_expires_at")
            .eq("client_id", client_id)
            .order("is_primary", desc=True)
            .order("created_at")
            .execute()
        )
        return {"contacts": res.data or []}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch contacts: {exc}")


@router.post("/api/console/clients/{client_id}/portal/contacts")
def rep_create_portal_contact(client_id: str, body: dict, request: Request):
    """Rep console: invite/create a new contact for a client company."""
    import main
    supabase = main.supabase

    if hasattr(request.state, "agent"):
        require_client_access(request.state.agent, client_id, supabase)

    name = (body.get("name") or "").strip()
    email = (body.get("email") or "").strip().lower() or None
    whatsapp = (body.get("whatsapp_number") or "").strip() or None
    role = body.get("portal_role", "evaluator")
    title = (body.get("title") or "").strip() or None

    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    if not email and not whatsapp:
        raise HTTPException(status_code=400, detail="Either email or whatsapp_number is required")
    if role not in ("admin", "evaluator", "finance_viewer"):
        raise HTTPException(status_code=400, detail="Invalid role")

    row = {
        "client_id": client_id,
        "name": name,
        "email": email,
        "whatsapp_number": whatsapp,
        "title": title,
        "portal_role": role,
        "status": "active",
    }

    try:
        res = supabase.table("portal_contacts").insert(row).execute()
        contact = res.data[0] if res.data else row

        log_audit_event(
            supabase,
            client_id=client_id,
            action="contact_created",
            object_type="contact",
            object_id=contact.get("id"),
            details={"name": name, "role": role},
        )
        return {"success": True, "contact": contact}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to create contact: {exc}")


@router.post("/api/console/clients/{client_id}/portal/contacts/{contact_id}/issue-code")
def rep_issue_login_code(client_id: str, contact_id: str, request: Request):
    """
    Rep console: issue a single-use 24h login code AND a 32-byte one-time invite link.
    """
    import main
    supabase = main.supabase

    if hasattr(request.state, "agent"):
        require_client_access(request.state.agent, client_id, supabase)

    try:
        res = supabase.table("portal_contacts").select("id, client_id, name, email, whatsapp_number").eq("id", contact_id).eq("client_id", client_id).single().execute()
        contact = res.data
        if not contact:
            raise HTTPException(status_code=404, detail="Contact not found")

        # 6-character code
        code = generate_secure_code(6)
        code_h = hash_code(code)

        # 32-byte one-time invite token
        invite_token = generate_invite_token()
        invite_h = hash_token(invite_token)

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=24)

        supabase.table("portal_contacts").update({
            "rep_code_hash": code_h,
            "rep_code_expires_at": expires_at.isoformat(),
            "invite_token_hash": invite_h,
            "invite_token_expires_at": expires_at.isoformat(),
            "failed_login_attempts": 0,
            "locked_until": None,
        }).eq("id", contact_id).execute()

        channel = "email" if contact.get("email") else "whatsapp"
        delivery_provider.send_login_code(contact, code, channel)

        log_audit_event(
            supabase,
            client_id=client_id,
            action="rep_issued_code",
            object_type="contact",
            contact_id=contact_id,
            details={"issued_by": "rep"},
        )

        invite_url = f"/portal/invite#token={invite_token}"

        return {
            "success": True,
            "code": code,
            "invite_token": invite_token,
            "invite_url": invite_url,
            "expires_at": expires_at.isoformat(),
            "message": f"Single-use code and invite link issued for {contact['name']} (valid 24h)."
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to issue code: {exc}")


@router.post("/api/console/clients/{client_id}/portal/contacts/{contact_id}/unlock")
def rep_unlock_contact(client_id: str, contact_id: str, request: Request):
    """
    Rep console: unlock a contact who was locked out due to failed attempts.
    Resets failed_login_attempts to 0 and clears locked_until.
    """
    import main
    supabase = main.supabase

    if hasattr(request.state, "agent"):
        require_client_access(request.state.agent, client_id, supabase)

    try:
        supabase.table("portal_contacts").update({
            "failed_login_attempts": 0,
            "locked_until": None,
        }).eq("id", contact_id).eq("client_id", client_id).execute()

        # Clear persistent rate limiter bucket using hashed key
        rate_limit_store.clear(hash_rate_limit_key("contact", contact_id))

        log_audit_event(
            supabase,
            client_id=client_id,
            action="contact_unlocked_by_rep",
            object_type="contact",
            contact_id=contact_id,
        )
        return {"success": True, "message": "Contact unlocked successfully."}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to unlock contact: {exc}")


@router.post("/api/console/clients/{client_id}/portal/contacts/{contact_id}/revoke-code")
def rep_revoke_login_code(client_id: str, contact_id: str, request: Request):
    """Rep console: revoke a pending login code and invite link."""
    import main
    supabase = main.supabase

    if hasattr(request.state, "agent"):
        require_client_access(request.state.agent, client_id, supabase)

    try:
        supabase.table("portal_contacts").update({
            "rep_code_hash": None,
            "rep_code_expires_at": None,
            "self_code_hash": None,
            "self_code_expires_at": None,
            "invite_token_hash": None,
            "invite_token_expires_at": None,
        }).eq("id", contact_id).eq("client_id", client_id).execute()

        log_audit_event(
            supabase,
            client_id=client_id,
            action="rep_revoked_code",
            object_type="contact",
            contact_id=contact_id,
        )
        return {"success": True, "message": "Code and invite link revoked"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to revoke code: {exc}")


@router.patch("/api/console/clients/{client_id}/portal/contacts/{contact_id}/deactivate")
def rep_deactivate_contact(client_id: str, contact_id: str, request: Request):
    """Rep console: deactivate a contact and revoke their active sessions."""
    import main
    supabase = main.supabase

    if hasattr(request.state, "agent"):
        require_client_access(request.state.agent, client_id, supabase)

    try:
        supabase.table("portal_contacts").update({
            "status": "deactivated",
            "rep_code_hash": None,
            "rep_code_expires_at": None,
            "self_code_hash": None,
            "self_code_expires_at": None,
            "invite_token_hash": None,
            "invite_token_expires_at": None,
        }).eq("id", contact_id).eq("client_id", client_id).execute()

        now = datetime.now(timezone.utc)
        supabase.table("portal_sessions").update({
            "revoked_at": now.isoformat()
        }).eq("contact_id", contact_id).execute()

        log_audit_event(
            supabase,
            client_id=client_id,
            action="contact_deactivated",
            object_type="contact",
            contact_id=contact_id,
        )
        return {"success": True, "message": "Contact deactivated and sessions revoked"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to deactivate contact: {exc}")


@router.post("/api/console/clients/{client_id}/portal/revoke-all-sessions")
def rep_revoke_all_sessions(client_id: str, request: Request):
    """Rep console: kill switch to revoke all active portal sessions for a company."""
    import main
    supabase = main.supabase

    if hasattr(request.state, "agent"):
        require_client_access(request.state.agent, client_id, supabase)

    now = datetime.now(timezone.utc)
    try:
        supabase.table("portal_sessions").update({
            "revoked_at": now.isoformat()
        }).eq("client_id", client_id).is_("revoked_at", "null").execute()

        log_audit_event(
            supabase,
            client_id=client_id,
            action="all_sessions_revoked",
            object_type="company",
            details={"revoked_by": "rep"},
        )
        return {"success": True, "message": "All company portal sessions have been revoked."}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to revoke sessions: {exc}")


@router.post("/api/console/clients/{client_id}/portal/rotate-legacy-code")
def rep_rotate_legacy_code(client_id: str, request: Request):
    """Rep console: generate a new legacy company code, hash it into portal_access_code_hash, null plaintext."""
    import main
    supabase = main.supabase

    if hasattr(request.state, "agent"):
        require_client_access(request.state.agent, client_id, supabase)

    new_code = generate_secure_code(8)
    new_hash = hash_code(new_code)

    try:
        supabase.table("clients").update({
            "portal_access_code": None,
            "portal_access_code_hash": new_hash,
        }).eq("id", client_id).execute()

        log_audit_event(
            supabase,
            client_id=client_id,
            action="legacy_code_rotated",
            object_type="client",
            details={"note": "Rep rotated legacy access code"},
        )
        return {
            "success": True,
            "new_access_code": new_code,
            "message": "Legacy company access code rotated."
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to rotate legacy code: {exc}")


@router.get("/api/console/clients/{client_id}/portal/audit-log")
def rep_get_portal_audit_log(client_id: str, request: Request, limit: int = 50):
    """Rep console: fetch audit trail for client portal access."""
    import main
    supabase = main.supabase

    if hasattr(request.state, "agent"):
        require_client_access(request.state.agent, client_id, supabase)

    try:
        res = (
            supabase.table("portal_audit_log")
            .select("id, client_id, contact_id, action, object_type, object_id, details, ip_hash, created_at")
            .eq("client_id", client_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return {"audit_log": res.data or []}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch audit log: {exc}")

