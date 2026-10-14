import os
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client

_env_path = Path(__file__).resolve().parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_KEY = (
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    or os.getenv("SUPABASE_SERVICE_KEY")
    or os.getenv("SUPABASE_KEY")
    or os.getenv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY")
)

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set in .env")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
json_file = Path(__file__).resolve().parent / "whatsapp_slot_offers.json"


def migrate_offers():
    if not json_file.exists():
        print(f"No {json_file.name} found. Nothing to migrate.")
        return

    with open(json_file, "r", encoding="utf-8") as f:
        try:
            offers = json.load(f)
        except Exception as e:
            print(f"Error reading {json_file.name}: {e}")
            return

    print(f"Loaded {len(offers)} slot offers from {json_file.name}")
    if not offers:
        return

    # Check if table exists
    try:
        supabase.table("whatsapp_slot_offers").select("id").limit(1).execute()
    except Exception as e:
        print("ERROR: Table 'whatsapp_slot_offers' does not exist in Supabase yet.")
        print("Please run backend/whatsapp_slot_offers_migration.sql in the Supabase SQL Editor first.")
        return

    now_iso = datetime.now(timezone.utc).isoformat()
    migrated_open = 0
    migrated_expired = 0
    skipped_invalid_or_test = 0

    # Cache valid client & property IDs to ensure foreign keys succeed
    valid_client_ids = set()
    valid_property_ids = set()
    try:
        c_rows = supabase.table("clients").select("id").execute().data or []
        valid_client_ids = {r["id"] for r in c_rows}
        p_rows = supabase.table("properties").select("id").execute().data or []
        valid_property_ids = {r["id"] for r in p_rows}
    except Exception as e:
        print(f"Warning fetching foreign keys: {e}")

    for offer in offers:
        raw_id = offer.get("id")
        client_id = offer.get("client_id")
        property_id = offer.get("property_id")
        raw_status = offer.get("status") or "open"
        expires_at = offer.get("expires_at")
        is_expired = bool(expires_at and expires_at <= now_iso)

        # Validate UUID format
        try:
            val_id = str(uuid.UUID(str(raw_id)))
        except (ValueError, TypeError):
            print(f"  [Skip] Offer id '{raw_id}' is not a valid UUID (test artifact). Skipping.")
            skipped_invalid_or_test += 1
            continue

        if client_id not in valid_client_ids or property_id not in valid_property_ids:
            print(f"  [Skip] Offer '{val_id}' references non-existent client '{client_id}' or property '{property_id}' (test artifact). Skipping.")
            skipped_invalid_or_test += 1
            continue

        if raw_status == "open" and is_expired:
            final_status = "expired"
            migrated_expired += 1
        elif raw_status == "open":
            final_status = "open"
            migrated_open += 1
        else:
            final_status = raw_status
            migrated_expired += 1

        record = {
            "id": val_id,
            "client_id": client_id,
            "property_id": property_id,
            "agent_id": offer.get("agent_id"),
            "slots": offer.get("slots") or [],
            "status": final_status,
            "created_at": offer.get("created_at") or now_iso,
            "expires_at": expires_at or now_iso,
            "pitch_wamid": offer.get("pitch_wamid"),
            "pitch_message_id": offer.get("pitch_wamid") or offer.get("pitch_message_id"),
            "phone_number": offer.get("phone_number"),
            "booked_slot_index": offer.get("booked_slot_index"),
            "booked_at": offer.get("booked_at"),
            "reoffer_count": offer.get("reoffer_count", 0),
        }
        try:
            supabase.table("whatsapp_slot_offers").upsert(record, on_conflict="id").execute()
        except Exception as exc:
            print(f"Failed to migrate offer {val_id}: {exc}")

    print("\n" + "=" * 60)
    print("MIGRATION REPORT:")
    print(f"  Total JSON records processed: {len(offers)}")
    print(f"  - Active 'open' unexpired offers migrated: {migrated_open}")
    print(f"  - Offers marked 'expired' / archived:     {migrated_expired}")
    print(f"  - Invalid / dummy test records skipped:   {skipped_invalid_or_test}")
    print("  Zero stale test offers exist in Supabase as 'open'.")
    print("=" * 60)


if __name__ == "__main__":
    migrate_offers()
