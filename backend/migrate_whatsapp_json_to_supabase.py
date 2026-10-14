import os
import json
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client

_env_path = Path(__file__).resolve().parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY") or os.getenv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY") or os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set in .env")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
json_file = Path(__file__).resolve().parent / "whatsapp_messages.json"

def migrate():
    if not json_file.exists():
        print("No whatsapp_messages.json found.")
        return

    with open(json_file, "r", encoding="utf-8") as f:
        messages = json.load(f)

    print(f"Loaded {len(messages)} messages from {json_file.name}")

    # Check if tables exist
    try:
        supabase.table("whatsapp_conversations").select("id").limit(1).execute()
    except Exception as e:
        print("ERROR: Table whatsapp_conversations does not exist in Supabase yet.")
        print("Please run backend/whatsapp_tables_migration.sql in the Supabase SQL Editor first.")
        return

    # Group by phone number
    conversations = {}
    for m in messages:
        num = m.get("to_number")
        if not num:
            continue
        if num not in conversations:
            conversations[num] = {
                "phone_number": num,
                "client_id": m.get("client_id"),
                "client_name": m.get("client_name") or "Contact",
                "agent_id": m.get("agent_id"),
            }

    conv_id_map = {}
    for num, conv_data in conversations.items():
        try:
            res = supabase.table("whatsapp_conversations").upsert(conv_data, on_conflict="phone_number").execute()
            if res.data:
                conv_id_map[num] = res.data[0]["id"]
                print(f"Upserted conversation for {num}: {res.data[0]['id']}")
        except Exception as e:
            print(f"Failed upserting conversation {num}: {e}")

    # Insert messages
    inserted = 0
    for m in messages:
        num = m.get("to_number")
        conv_id = conv_id_map.get(num)
        msg_payload = {
            "id": m.get("id"),
            "conversation_id": conv_id,
            "to_number": num,
            "client_id": m.get("client_id"),
            "agent_id": m.get("agent_id"),
            "client_name": m.get("client_name") or "Contact",
            "sender": m.get("sender") or "agent",
            "text": m.get("text") or "",
            "status": m.get("status") or "sent",
            "timestamp": m.get("timestamp"),
        }
        try:
            supabase.table("whatsapp_messages").upsert(msg_payload, on_conflict="id").execute()
            inserted += 1
        except Exception as e:
            print(f"Failed to upsert message {m.get('id')}: {e}")

    print(f"Successfully migrated {inserted}/{len(messages)} messages to Supabase!")

if __name__ == "__main__":
    migrate()
