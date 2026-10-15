"""
backend/tests/test_live_db_functions.py
───────────────────────────────────────
Opt-in test suite for PostgreSQL RPC functions against live Supabase.
Runs ONLY when explicitly selected:
    pytest backend/tests/test_live_db_functions.py -m live_db

Verifies:
1. portal_increment_rate_limit: called twice, increments counter atomically.
2. portal_record_failed_login:
   - Called twice, increments failed attempts.
   - Third attempt locks contact.
   - Subsequent attempt while locked does NOT extend lock.
   - Simulating window expiry (> 15 minutes) resets counter.
   - portal_reset_contact_lockout resets lock cleanly.
3. agent_record_failed_login:
   - Called twice, increments counter.
   - Locks at max attempts.
   - Active lock is not extended by further attempts.
   - Window expiry resets counter.
   - agent_reset_failed_login resets lock cleanly.
"""

import os
import uuid
from datetime import datetime, timezone, timedelta
import pytest

pytestmark = pytest.mark.live_db


def get_live_supabase():
    supabase_url = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
    if not supabase_url or not supabase_key:
        pytest.skip("Supabase credentials not configured in environment.")
    from supabase import create_client
    return create_client(supabase_url, supabase_key)


@pytest.mark.live_db
def test_portal_increment_rate_limit_live():
    """Opt-in test for atomic rate limiter RPC on live database."""
    supabase = get_live_supabase()
    test_key = f"zz_live_test:{uuid.uuid4()}"
    try:
        # Call 1
        res1 = supabase.rpc("portal_increment_rate_limit", {"p_key": test_key, "p_window_seconds": 60}).execute()
        assert res1.data and len(res1.data) > 0
        assert res1.data[0]["out_attempts"] == 1

        # Call 2
        res2 = supabase.rpc("portal_increment_rate_limit", {"p_key": test_key, "p_window_seconds": 60}).execute()
        assert res2.data and len(res2.data) > 0
        assert res2.data[0]["out_attempts"] == 2
    finally:
        supabase.table("portal_rate_limits").delete().eq("key", test_key).execute()


@pytest.mark.live_db
def test_portal_lockout_and_window_semantics_live():
    """Verifies lockout, non-extension, and 15m window reset for portal contacts."""
    supabase = get_live_supabase()
    suffix = uuid.uuid4().hex[:8]

    # Create temporary client & contact
    c_res = supabase.table("clients").insert({
        "name": f"__live_test_client_{suffix}__",
        "portal_access_code_hash": "dummy_test_hash"
    }).execute()
    client_id = c_res.data[0]["id"]

    try:
        cont_res = supabase.table("portal_contacts").insert({
            "client_id": client_id,
            "name": f"Live Test Contact {suffix}",
            "email": f"test_contact_{suffix}@example.com",
            "is_primary": True
        }).execute()
        contact_id = cont_res.data[0]["id"]

        # 1. Call twice: attempts 1 and 2
        res1 = supabase.rpc("portal_record_failed_login", {
            "p_contact_id": contact_id,
            "p_max_attempts": 3,
            "p_lockout_seconds": 900,
            "p_window_seconds": 900
        }).execute()
        assert res1.data[0]["out_failed_attempts"] == 1
        assert res1.data[0]["out_is_locked"] is False

        res2 = supabase.rpc("portal_record_failed_login", {
            "p_contact_id": contact_id,
            "p_max_attempts": 3,
            "p_lockout_seconds": 900,
            "p_window_seconds": 900
        }).execute()
        assert res2.data[0]["out_failed_attempts"] == 2
        assert res2.data[0]["out_is_locked"] is False

        # 2. Third attempt triggers lock
        res3 = supabase.rpc("portal_record_failed_login", {
            "p_contact_id": contact_id,
            "p_max_attempts": 3,
            "p_lockout_seconds": 900,
            "p_window_seconds": 900
        }).execute()
        assert res3.data[0]["out_failed_attempts"] == 3
        assert res3.data[0]["out_is_locked"] is True
        locked_until_1 = res3.data[0]["out_locked_until"]
        assert locked_until_1 is not None

        # 3. Fourth attempt while locked: PROVE LOCK IS NOT EXTENDED
        res4 = supabase.rpc("portal_record_failed_login", {
            "p_contact_id": contact_id,
            "p_max_attempts": 3,
            "p_lockout_seconds": 900,
            "p_window_seconds": 900
        }).execute()
        assert res4.data[0]["out_is_locked"] is True
        assert res4.data[0]["out_locked_until"] == locked_until_1

        # 4. Reset lockout
        supabase.rpc("portal_reset_contact_lockout", {"p_contact_id": contact_id}).execute()
        check_reset = supabase.table("portal_contacts").select("failed_attempts, locked_until").eq("id", contact_id).execute()
        assert check_reset.data[0]["failed_attempts"] == 0
        assert check_reset.data[0]["locked_until"] is None

        # 5. Simulate 15-minute window expiry by setting last_failed_at to 20 minutes ago
        past_time = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
        supabase.table("portal_contacts").update({
            "failed_attempts": 2,
            "last_failed_at": past_time
        }).eq("id", contact_id).execute()

        # Calling again after window expiry resets counter to 1
        res_win = supabase.rpc("portal_record_failed_login", {
            "p_contact_id": contact_id,
            "p_max_attempts": 3,
            "p_lockout_seconds": 900,
            "p_window_seconds": 900
        }).execute()
        assert res_win.data[0]["out_failed_attempts"] == 1
        assert res_win.data[0]["out_is_locked"] is False

    finally:
        supabase.table("portal_contacts").delete().eq("client_id", client_id).execute()
        supabase.table("clients").delete().eq("id", client_id).execute()


@pytest.mark.live_db
def test_agent_lockout_and_window_semantics_live():
    """Verifies lockout, non-extension, and 15m window reset for agent accounts."""
    supabase = get_live_supabase()
    suffix = uuid.uuid4().hex[:8]

    acc_res = supabase.table("agent_accounts").insert({
        "name": f"Live Agent {suffix}",
        "email": f"live_agent_{suffix}@pipeline-ev.com",
        "role": "agent",
        "status": "active"
    }).execute()
    account_id = acc_res.data[0]["id"]

    try:
        # 1. Call twice
        res1 = supabase.rpc("agent_record_failed_login", {
            "p_account_id": account_id,
            "p_max_attempts": 3,
            "p_lockout_seconds": 900,
            "p_window_seconds": 900
        }).execute()
        assert res1.data[0]["out_failed_attempts"] == 1
        assert res1.data[0]["out_is_locked"] is False

        res2 = supabase.rpc("agent_record_failed_login", {
            "p_account_id": account_id,
            "p_max_attempts": 3,
            "p_lockout_seconds": 900,
            "p_window_seconds": 900
        }).execute()
        assert res2.data[0]["out_failed_attempts"] == 2
        assert res2.data[0]["out_is_locked"] is False

        # 2. Lock on 3rd attempt
        res3 = supabase.rpc("agent_record_failed_login", {
            "p_account_id": account_id,
            "p_max_attempts": 3,
            "p_lockout_seconds": 900,
            "p_window_seconds": 900
        }).execute()
        assert res3.data[0]["out_is_locked"] is True
        locked_until_1 = res3.data[0]["out_locked_until"]

        # 3. Prove lock is NOT extended
        res4 = supabase.rpc("agent_record_failed_login", {
            "p_account_id": account_id,
            "p_max_attempts": 3,
            "p_lockout_seconds": 900,
            "p_window_seconds": 900
        }).execute()
        assert res4.data[0]["out_locked_until"] == locked_until_1

        # 4. Reset
        supabase.rpc("agent_reset_failed_login", {"p_account_id": account_id}).execute()
        check_reset = supabase.table("agent_accounts").select("failed_login_attempts, locked_until").eq("id", account_id).execute()
        assert check_reset.data[0]["failed_login_attempts"] == 0
        assert check_reset.data[0]["locked_until"] is None

        # 5. Simulate 15m window expiry
        past_time = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
        supabase.table("agent_accounts").update({
            "failed_login_attempts": 2,
            "last_failed_at": past_time
        }).eq("id", account_id).execute()

        res_win = supabase.rpc("agent_record_failed_login", {
            "p_account_id": account_id,
            "p_max_attempts": 3,
            "p_lockout_seconds": 900,
            "p_window_seconds": 900
        }).execute()
        assert res_win.data[0]["out_failed_attempts"] == 1
        assert res_win.data[0]["out_is_locked"] is False

    finally:
        supabase.table("agent_accounts").delete().eq("id", account_id).execute()
