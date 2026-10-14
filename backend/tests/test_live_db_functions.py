"""
backend/tests/test_live_db_functions.py
───────────────────────────────────────
Opt-in test suite for PostgreSQL RPC functions against live Supabase.
Run with:
    pytest backend/tests/test_live_db_functions.py -m live_db
"""

import os
import uuid
import pytest

pytestmark = pytest.mark.live_db


@pytest.mark.live_db
def test_portal_increment_rate_limit_live():
    """Opt-in test for atomic rate limiter RPC on live database."""
    supabase_url = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")

    if not supabase_url or not supabase_key:
        pytest.skip("Supabase credentials not configured in environment.")

    from supabase import create_client
    supabase = create_client(supabase_url, supabase_key)

    test_key = f"zz_live_test:{uuid.uuid4()}"
    try:
        # Call 1
        res1 = supabase.rpc("portal_increment_rate_limit", {"p_key": test_key, "p_window_seconds": 60}).execute()
        assert res1.data and len(res1.data) > 0
        attempts1 = res1.data[0]["out_attempts"]
        assert attempts1 == 1

        # Call 2
        res2 = supabase.rpc("portal_increment_rate_limit", {"p_key": test_key, "p_window_seconds": 60}).execute()
        assert res2.data and len(res2.data) > 0
        attempts2 = res2.data[0]["out_attempts"]
        assert attempts2 == 2
    finally:
        # Cleanup
        supabase.table("portal_rate_limits").delete().eq("key", test_key).execute()
