"""
scripts/reset_agent_password_cli.py
───────────────────────────────────
CLI emergency recovery script for administrators and agents who forgot passwords
or are locked out. There is NO public self-service reset path for admins.

This script directly operates via Supabase connection to:
1. Unlock the account (reset failed_login_attempts to 0, locked_until to NULL).
2. Set a new Argon2id password via hidden interactive prompt (getpass), OR issue a one-time 15-minute reset code.
3. Invalidate/revoke ALL existing active sessions for that agent.
4. Record an audit entry in agent_audit_log.

Usage:
  # Option A: Reset password interactively via hidden prompt (never in shell history)
  python scripts/reset_agent_password_cli.py --email admin@pipeline-ev.com

  # Option B: Unlock and generate a one-time reset code
  python scripts/reset_agent_password_cli.py --email admin@pipeline-ev.com --issue-code
"""

import sys
import argparse
import getpass
from pathlib import Path
from datetime import datetime, timezone, timedelta

backend_dir = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

from agent_auth import (
    hash_password,
    validate_password_complexity,
    generate_enrollment_code,
    hash_enrollment_code,
    log_agent_audit_event,
)


def reset_password_cli(email: str, issue_code: bool = False):
    email_clean = email.strip().lower()

    import main
    supabase = main.supabase

    # Lookup agent
    res = supabase.table("agent_accounts").select("*").eq("email", email_clean).limit(1).execute()
    if not res.data:
        print(f"ERROR: No agent account found with email: {email_clean}")
        return False

    agent = res.data[0]
    agent_id = agent["id"]
    now = datetime.now(timezone.utc)

    if issue_code:
        code = generate_enrollment_code()
        code_h = hash_enrollment_code(code)
        exp = now + timedelta(minutes=15)

        supabase.table("agent_accounts").update({
            "reset_code_hash": code_h,
            "reset_code_expires_at": exp.isoformat(),
            "failed_login_attempts": 0,
            "locked_until": None,
            "updated_at": now.isoformat(),
        }).eq("id", agent_id).execute()

        # Revoke existing sessions
        supabase.table("agent_sessions").update({
            "revoked_at": now.isoformat()
        }).eq("account_id", agent_id).is_("revoked_at", None).execute()

        log_agent_audit_event(
            supabase,
            agent_id=agent_id,
            action="cli_reset_code_issued",
            object_type="agent_account",
            object_id=agent_id,
            details={"email": email_clean, "expires_at": exp.isoformat()},
        )

        print("\n" + "=" * 64)
        print(f"RECOVERY RESET CODE ISSUED: {agent['name']} <{email_clean}>")
        print(f"One-Time Code:   {code}")
        print(f"Expires At:      {exp.isoformat()} (15 minutes)")
        print("=" * 64)
        print("ACTION REQUIRED:")
        print("Agent must use POST /api/agent/reset-password with this code to complete reset.\n")
        return True

    else:
        # Prompt securely using getpass
        print(f"\nEntering password reset for: {agent['name']} <{email_clean}>")
        pwd1 = getpass.getpass("Enter new password (min 12 characters): ")
        if not pwd1:
            print("ERROR: Password cannot be empty.")
            return False

        pwd2 = getpass.getpass("Confirm new password: ")
        if pwd1 != pwd2:
            print("ERROR: Passwords do not match.")
            return False

        try:
            validate_password_complexity(pwd1, email_clean)
        except Exception as exc:
            print(f"ERROR: Password complexity check failed: {exc}")
            return False

        pwd_hash = hash_password(pwd1)
        supabase.table("agent_accounts").update({
            "password_hash": pwd_hash,
            "failed_login_attempts": 0,
            "locked_until": None,
            "status": "active",
            "reset_code_hash": None,
            "reset_code_expires_at": None,
            "updated_at": now.isoformat(),
        }).eq("id", agent_id).execute()

        # Revoke existing sessions
        supabase.table("agent_sessions").update({
            "revoked_at": now.isoformat()
        }).eq("account_id", agent_id).is_("revoked_at", None).execute()

        log_agent_audit_event(
            supabase,
            agent_id=agent_id,
            action="cli_password_reset_direct",
            object_type="agent_account",
            object_id=agent_id,
            details={"email": email_clean},
        )

        print("\n" + "=" * 64)
        print(f"PASSWORD DIRECTLY RESET & ACCOUNT UNLOCKED: {agent['name']} <{email_clean}>")
        print(f"Status:          ACTIVE")
        print(f"Sessions:        ALL PREVIOUS SESSIONS REVOKED")
        print("=" * 64 + "\n")
        return True


def main_cli():
    parser = argparse.ArgumentParser(description="Emergency CLI recovery for agent accounts.")
    parser.add_argument("--email", required=True, help="Agent email address")
    parser.add_argument("--issue-code", action="store_true", help="Generate a one-time 15-minute reset code instead of setting password directly via prompt")

    args = parser.parse_args()
    success = reset_password_cli(args.email, issue_code=args.issue_code)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main_cli()
