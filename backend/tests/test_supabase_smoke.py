import os
from pathlib import Path
import pytest
from dotenv import load_dotenv

# Load backend/.env if available
_backend_env = Path(__file__).resolve().parent.parent / ".env"
if _backend_env.exists():
    load_dotenv(_backend_env)

RUN_LIVE = os.getenv("RUN_LIVE_SUPABASE_TESTS", "").lower() in ("true", "1")


@pytest.mark.skipif(not RUN_LIVE, reason="Live Supabase smoke tests are disabled by default. Set RUN_LIVE_SUPABASE_TESTS=true to run.")
class TestSupabaseLiveSmoke:
    """
    Opt-in smoke tests that verify live Supabase schema and functions.
    Skipped by default in standard test suites.
    """

    @pytest.fixture(autouse=True)
    def setup_client(self):
        from supabase import create_client
        url = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
        key = (
            os.getenv("SUPABASE_SERVICE_ROLE_KEY")
            or os.getenv("SUPABASE_SERVICE_KEY")
            or os.getenv("SUPABASE_KEY")
            or os.getenv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY")
        )
        if not url or not key:
            pytest.skip("Supabase URL or Key not configured in environment")
        self.sb = create_client(url, key)

    def test_whatsapp_slot_offers_table_exists(self):
        """Verifies whatsapp_slot_offers table exists and responds to SELECT queries."""
        res = self.sb.table("whatsapp_slot_offers").select("id").limit(1).execute()
        assert res is not None
        assert hasattr(res, "data")
        print(f"\n[LIVE SMOKE] whatsapp_slot_offers accessible. Row count sample: {len(res.data or [])}")

    def test_claim_and_book_slot_offer_rpc_exists(self):
        """Verifies the atomic transactional RPC claim_and_book_slot_offer is installed."""
        dummy_uuid = "00000000-0000-0000-0000-000000000000"
        res = self.sb.rpc("claim_and_book_slot_offer", {
            "p_offer_id": dummy_uuid,
            "p_slot_index": 1,
        }).execute()
        assert res is not None
        # On a dummy UUID, it should return success: false ("Offer not available or expired")
        data = res.data
        assert isinstance(data, dict)
        assert data.get("success") is False
        assert "not available or expired" in data.get("error", "").lower()
        print(f"\n[LIVE SMOKE] claim_and_book_slot_offer RPC verified! Response: {data}")
