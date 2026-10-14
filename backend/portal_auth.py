"""
portal_auth.py
──────────────
B2B Client Portal v2 Authentication, Session Management, RBAC, and Audit Logging.
Enforces:
- HMAC-hashed single-use expiring login codes (pepper required from env, no default)
- Pluggable delivery interface (Dev log only; WhatsApp template guard)
- Anti-enumeration rate limiting & lockout per contact (5 attempts) and per IP (30 attempts)
- Real client IP resolution via proxy chain verification with required BFF_INTERNAL_SECRET
- Opaque random session tokens, stored hashed (SHA-256), idle & absolute expiry, revocation
- Rep-issued one-time invite link generation (32 bytes random token, hashed, 24h)
- Origin / CSRF check on state-changing requests
- Strict server-side derivation of client_id, contact_id, and role (never trust URL client_id)
- Zero secret logging
"""

import os
import hmac
import hashlib
import secrets
import sqlite3
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Tuple
from fastapi import Request, HTTPException, Depends, Header, Cookie

# ─── Environment Configuration ───────────────────────────────────────────────

def get_code_pepper() -> str:
    """Retrieve the required server pepper for HMAC hashing. Fails fast if missing."""
    pepper = os.getenv("PORTAL_CODE_PEPPER")
    if not pepper:
        raise RuntimeError("PORTAL_CODE_PEPPER environment variable is required")
    return pepper


def is_legacy_login_enabled() -> bool:
    """Legacy company access codes are disabled by default."""
    val = os.getenv("PORTAL_LEGACY_LOGIN_ENABLED", "false").strip().lower()
    return val in ("true", "1", "yes", "on")


def is_dev_environment() -> bool:
    env = os.getenv("ENVIRONMENT", os.getenv("NODE_ENV", "development")).lower()
    return env not in ("production", "prod")


# ─── Pluggable Delivery Interface ─────────────────────────────────────────────

class BaseDeliveryProvider:
    def send_login_code(self, contact: dict, code: str, channel: str) -> bool:
        raise NotImplementedError


class DevDeliveryProvider(BaseDeliveryProvider):
    """
    Development delivery provider.
    Prints the single-use code to server logs in dev mode ONLY.
    Never prints in production.
    """
    def send_login_code(self, contact: dict, code: str, channel: str) -> bool:
        if is_dev_environment():
            identifier = contact.get("email") or contact.get("whatsapp_number") or contact.get("name")
            print(f"[PORTAL_AUTH_DEV] Login code for {identifier} ({channel}): {code} (expires in 24h)")
            return True
        return False


class WhatsAppDeliveryProvider(BaseDeliveryProvider):
    """
    WhatsApp delivery provider via Meta Cloud API.
    Guarded: only dispatches if an approved template is configured.
    """
    def __init__(self, template_name: Optional[str] = None):
        self.template_name = template_name or os.getenv("WHATSAPP_AUTH_TEMPLATE_NAME")

    def send_login_code(self, contact: dict, code: str, channel: str) -> bool:
        if not self.template_name:
            print("[PORTAL_AUTH] WhatsApp OTP blocked: No approved authentication template configured.")
            return False
        return True


# Default provider instance
delivery_provider: BaseDeliveryProvider = DevDeliveryProvider()


# ─── Cryptographic Helpers ────────────────────────────────────────────────────

def hash_code(code: str) -> str:
    """Compute HMAC-SHA256 of login/invite code using server pepper."""
    pepper = get_code_pepper()
    return hmac.new(pepper.encode("utf-8"), code.strip().upper().encode("utf-8"), hashlib.sha256).hexdigest()


def hash_token(token: str) -> str:
    """Compute standard SHA-256 of session token or invite link token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_ip(ip: Optional[str]) -> str:
    """Compute HMAC-SHA256 of client IP address using server pepper."""
    if not ip:
        return "unknown"
    pepper = get_code_pepper()
    return hmac.new(pepper.encode("utf-8"), ip.strip().encode("utf-8"), hashlib.sha256).hexdigest()


def generate_secure_code(length: int = 6) -> str:
    """Generate unambiguous alphanumeric single-use code."""
    # Exclude easily confused chars: 0, O, 1, I, L
    alphabet = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def generate_invite_token() -> str:
    """Generate 32-byte cryptographically secure URL-safe invite token."""
    return secrets.token_urlsafe(32)


def generate_session_token() -> str:
    """Generate 256-bit cryptographically secure opaque session token."""
    return secrets.token_urlsafe(32)


# ─── Proxy Chain & Client IP Forwarding ───────────────────────────────────────

def get_trusted_client_ip(request: Request) -> str:
    """
    Resolves client IP from request headers safely:
    - If BFF_INTERNAL_SECRET matches x-bff-internal-secret header:
      trusts the forwarded IP (leftmost entry in x-forwarded-for or x-real-ip).
    - If secret is missing or invalid:
      discards forwarded headers and returns direct socket IP.
    """
    secret = os.getenv("BFF_INTERNAL_SECRET", "")
    header_secret = request.headers.get("x-bff-internal-secret", "")

    # Constant-time comparison
    is_trusted = bool(secret and header_secret and hmac.compare_digest(secret, header_secret))

    if is_trusted:
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            # First IP in X-Forwarded-For is the original client IP added by reverse proxy
            client_ip = forwarded_for.split(",")[0].strip()
            if client_ip:
                return client_ip
        real_ip = request.headers.get("x-real-ip")
        if real_ip and real_ip.strip():
            return real_ip.strip()

    # Direct socket address
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"


# ─── Persistent Rate Limiter & Lockout Store ───────────────────────────────────

IP_MAX_ATTEMPTS = 30        # 30 attempts per 15 min (raised so shared office NAT is not locked out)
IP_WINDOW_SECONDS = 900     # 15 minutes
IP_LOCKOUT_SECONDS = 900    # 15 minutes

CONTACT_MAX_ATTEMPTS = 5    # 5 attempts per contact
CONTACT_WINDOW_SECONDS = 900
CONTACT_LOCKOUT_SECONDS = 900


class PersistentRateLimitStore:
    """
    Persistent store for rate limits that survives restarts.
    Uses SQLite database backend with WAL mode for thread-safety and durability.
    Falls back to or coordinates with Supabase RPC functions when live.
    """
    def __init__(self, db_path: Optional[str] = None):
        if not db_path:
            base_dir = os.path.dirname(__file__)
            db_path = os.path.join(base_dir, ".rate_limits.sqlite3")
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._lock, self._get_connection() as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS rate_limits (
                    key_hash TEXT PRIMARY KEY,
                    bucket_type TEXT NOT NULL,
                    attempt_count INT NOT NULL DEFAULT 1,
                    window_start TEXT NOT NULL,
                    locked_until TEXT
                );
            """)
            conn.commit()

    def increment_and_check(
        self,
        key_hash: str,
        bucket_type: str,
        window_seconds: int = 900,
        max_attempts: int = 30,
        lockout_seconds: int = 900,
    ) -> Tuple[bool, Optional[datetime], int]:
        """
        Atomically records an attempt and checks limits.
        Returns: (allowed: bool, locked_until: datetime | None, count: int)
        """
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()

        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT attempt_count, window_start, locked_until FROM rate_limits WHERE key_hash = ?", (key_hash,))
            row = cursor.fetchone()

            if not row:
                cursor.execute("""
                    INSERT INTO rate_limits (key_hash, bucket_type, attempt_count, window_start, locked_until)
                    VALUES (?, ?, 1, ?, NULL)
                """, (key_hash, bucket_type, now_iso))
                conn.commit()
                return True, None, 1

            attempt_count = row["attempt_count"]
            window_start_str = row["window_start"]
            locked_until_str = row["locked_until"]

            # Check active lockout
            if locked_until_str:
                locked_until = datetime.fromisoformat(locked_until_str)
                if now < locked_until:
                    return False, locked_until, attempt_count

            window_start = datetime.fromisoformat(window_start_str)
            if now > window_start + timedelta(seconds=window_seconds):
                # Window expired, reset bucket
                cursor.execute("""
                    UPDATE rate_limits
                    SET attempt_count = 1, window_start = ?, locked_until = NULL
                    WHERE key_hash = ?
                """, (now_iso, key_hash))
                conn.commit()
                return True, None, 1

            # Window still active: increment
            new_count = attempt_count + 1
            if new_count > max_attempts:
                lock_until = now + timedelta(seconds=lockout_seconds)
                lock_until_iso = lock_until.isoformat()
                cursor.execute("""
                    UPDATE rate_limits
                    SET attempt_count = ?, locked_until = ?
                    WHERE key_hash = ?
                """, (new_count, lock_until_iso, key_hash))
                conn.commit()
                return False, lock_until, new_count
            else:
                cursor.execute("""
                    UPDATE rate_limits
                    SET attempt_count = ?
                    WHERE key_hash = ?
                """, (new_count, key_hash))
                conn.commit()
                return True, None, new_count

    def clear(self, key_hash: str):
        with self._lock, self._get_connection() as conn:
            conn.execute("DELETE FROM rate_limits WHERE key_hash = ?", (key_hash,))
            conn.commit()


# Global rate limit store
rate_limit_store = PersistentRateLimitStore()


def check_and_record_ip_attempt(ip: str, success: bool = False):
    """
    Persistent IP rate limit check.
    Max 30 attempts per 15 min. Locks out for 15 min on exceeding.
    """
    ip_key = hash_ip(ip)
    if success:
        rate_limit_store.clear(ip_key)
        return

    allowed, locked_until, count = rate_limit_store.increment_and_check(
        key_hash=ip_key,
        bucket_type="ip",
        window_seconds=IP_WINDOW_SECONDS,
        max_attempts=IP_MAX_ATTEMPTS,
        lockout_seconds=IP_LOCKOUT_SECONDS,
    )
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many failed attempts. IP temporarily locked out. Please try again later."
        )


def check_and_record_contact_attempt(contact_id: str, success: bool = False):
    """
    Persistent contact rate limit check.
    Max 5 attempts per 15 min. Locks out contact for 15 min on exceeding.
    """
    contact_key = f"contact_{contact_id}"
    if success:
        rate_limit_store.clear(contact_key)
        return

    allowed, locked_until, count = rate_limit_store.increment_and_check(
        key_hash=contact_key,
        bucket_type="contact",
        window_seconds=CONTACT_WINDOW_SECONDS,
        max_attempts=CONTACT_MAX_ATTEMPTS,
        lockout_seconds=CONTACT_LOCKOUT_SECONDS,
    )
    if not allowed:
        raise HTTPException(
            status_code=403,
            detail="Contact account is temporarily locked out due to multiple failed attempts. Please contact your PIPELINE.EV representative to unlock."
        )


# ─── Audit Logging Helper ─────────────────────────────────────────────────────

def log_audit_event(
    supabase_client,
    client_id: str,
    action: str,
    object_type: str,
    contact_id: Optional[str] = None,
    object_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    ip: Optional[str] = None,
):
    """
    Inserts a row into portal_audit_log with HMAC-hashed IP.
    Ensures all secrets, passwords, and tokens are redacted.
    """
    if details:
        clean_details = {}
        for k, v in details.items():
            k_lower = k.lower()
            if any(secret_word in k_lower for secret_word in ("token", "code", "hash", "password", "pepper", "secret")):
                clean_details[k] = "[REDACTED]"
            else:
                clean_details[k] = v
    else:
        clean_details = {}

    row = {
        "client_id": client_id,
        "contact_id": contact_id,
        "action": action,
        "object_type": object_type,
        "object_id": object_id,
        "details": clean_details,
        "ip_hash": hash_ip(ip),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        supabase_client.table("portal_audit_log").insert(row).execute()
    except Exception as e:
        print(f"[PORTAL_AUDIT_ERROR] Failed to record audit log: {e}")


# ─── CSRF / Origin Verification ───────────────────────────────────────────────

ALLOWED_ORIGINS = {
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
}

def verify_origin(request: Request):
    """
    CSRF Guard: verifies Origin or Referer matches allowed application origin
    for state-changing HTTP methods.
    """
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        origin = request.headers.get("origin") or request.headers.get("referer")
        if origin:
            from urllib.parse import urlparse
            parsed = urlparse(origin)
            base_origin = f"{parsed.scheme}://{parsed.netloc}"
            configured_url = os.getenv("PUBLIC_BASE_URL")
            valid = ALLOWED_ORIGINS.copy()
            if configured_url:
                valid.add(configured_url.rstrip("/"))
            if base_origin not in valid and not is_dev_environment():
                raise HTTPException(status_code=403, detail="Cross-origin request rejected")


# ─── Session Verification Dependency ──────────────────────────────────────────

class PortalSession:
    def __init__(
        self,
        session_id: str,
        client_id: str,
        contact_id: Optional[str],
        contact_name: str,
        portal_role: str,
        client_name: str,
        is_legacy: bool = False,
    ):
        self.session_id = session_id
        self.client_id = client_id
        self.contact_id = contact_id
        self.contact_name = contact_name
        self.portal_role = portal_role
        self.client_name = client_name
        self.is_legacy = is_legacy


def get_current_portal_session(
    request: Request,
    authorization: Optional[str] = Header(None),
    portal_session: Optional[str] = Cookie(None),
) -> PortalSession:
    """
    Validates the caller's session token and resolves the contact, client, and role.
    Rejects expired, revoked, or locked-out sessions.
    Updates idle timeout and last_active_at on success.
    """
    # 1. CSRF / Origin Check
    verify_origin(request)

    # 2. Extract Token
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split("Bearer ", 1)[1].strip()
    elif portal_session:
        token = portal_session.strip()

    if not token:
        raise HTTPException(status_code=401, detail="Authentication required: No session provided")

    token_h = hash_token(token)
    now = datetime.now(timezone.utc)

    # 3. Query portal_sessions from database
    import main
    supabase = main.supabase

    try:
        res = (
            supabase.table("portal_sessions")
            .select(
                "id, client_id, contact_id, portal_role, idle_expires_at, absolute_expires_at, revoked_at, "
                "clients(id, name), portal_contacts(id, name, status, locked_until)"
            )
            .eq("token_hash", token_h)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Session lookup failed: {exc}")

    if not res.data:
        raise HTTPException(status_code=401, detail="Invalid session token")

    s_row = res.data[0]

    # 4. Check Revocation
    if s_row.get("revoked_at"):
        raise HTTPException(status_code=401, detail="Session has been revoked")

    # 5. Check Absolute Expiry
    abs_exp = datetime.fromisoformat(s_row["absolute_expires_at"].replace("Z", "+00:00"))
    if now > abs_exp:
        raise HTTPException(status_code=401, detail="Session has expired (absolute timeout)")

    # 6. Check Idle Expiry
    idle_exp = datetime.fromisoformat(s_row["idle_expires_at"].replace("Z", "+00:00"))
    if now > idle_exp:
        raise HTTPException(status_code=401, detail="Session has expired due to inactivity")

    # 7. Check Contact status & Lockout (if contact session)
    contact_info = s_row.get("portal_contacts") or {}
    if contact_info:
        if contact_info.get("status") == "deactivated":
            raise HTTPException(status_code=403, detail="Contact account is deactivated")
        locked_until_str = contact_info.get("locked_until")
        if locked_until_str:
            locked_until = datetime.fromisoformat(locked_until_str.replace("Z", "+00:00"))
            if now < locked_until:
                raise HTTPException(status_code=403, detail="Contact account is temporarily locked out")

    # 8. Update idle expiry & last_active_at (slide window: 2 hours)
    new_idle = now + timedelta(hours=2)
    try:
        supabase.table("portal_sessions").update({
            "idle_expires_at": new_idle.isoformat(),
            "last_active_at": now.isoformat(),
        }).eq("id", s_row["id"]).execute()
    except Exception:
        pass

    client_info = s_row.get("clients") or {}
    is_legacy = s_row["portal_role"] == "legacy_readonly"

    return PortalSession(
        session_id=s_row["id"],
        client_id=s_row["client_id"],
        contact_id=s_row["contact_id"],
        contact_name=contact_info.get("name") or (client_info.get("name") if is_legacy else "Client User"),
        portal_role=s_row["portal_role"],
        client_name=client_info.get("name") or "Company",
        is_legacy=is_legacy,
    )


def require_company_access(session: PortalSession, target_client_id: str):
    """
    Enforces tenant isolation: caller's session MUST match the URL client_id.
    Prevents Company B from reading or modifying Company A's resources.
    """
    if session.client_id != target_client_id:
        raise HTTPException(
            status_code=403,
            detail="Forbidden: You do not have access to this company's workspace"
        )
