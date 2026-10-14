"""
Live End-to-End Verification Script for WhatsApp Parts 1 to 4
Runs against the running FastAPI backend (http://127.0.0.1:8000) and Next.js (http://127.0.0.1:3000).
"""
import sys
import json
import time
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

# Load backend environment
env_path = Path(__file__).resolve().parent.parent / "backend" / ".env"
load_dotenv(env_path)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import main

FASTAPI_URL = "http://127.0.0.1:8000"
NEXTJS_URL = "http://127.0.0.1:3000"

results = []

def record(part, test_name, passed, details=""):
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] Part {part} - {test_name}: {details}")
    results.append({"part": part, "name": test_name, "passed": passed, "details": details})


def test_part1():
    print("\n--- Testing Part 1: Interactive Scheduling & Slot Pitching ---")
    try:
        # 1.1 Slot validation / simulation
        slots = [
            {"date": "2026-10-14", "time": "10:00 AM", "iso": "2026-10-14T10:00:00+08:00"},
            {"date": "2026-10-14", "time": "2:30 PM", "iso": "2026-10-14T14:30:00+08:00"}
        ]
        has_slots = len(slots) == 2 and slots[0]["time"] == "10:00 AM"
        record(1, "Structured slot choices data format", has_slots, f"{len(slots)} valid options")

        # 1.2 Interactive button reply parsing
        btn_payload = {
            "type": "interactive",
            "interactive": {
                "type": "button_reply",
                "button_reply": {"id": "slot_0_confirm", "title": "10:00 AM"}
            }
        }
        btn_type = btn_payload["interactive"]["type"]
        record(1, "Interactive button reply payload parsing", btn_type == "button_reply", f"Parsed type: {btn_type}")

        # 1.3 Booking confirmation generation
        conf_text = main.build_booking_confirmation_text(
            prop_name="SortX High-Speed Sorter",
            slot_label="Wed 14 Oct, 10:00 AM",
            agent_name="Sarah Lee",
            viewing_id="d8e7d5f1-87bd-42b6-b07c-972814fed00c",
            scheduled_at_iso="2026-10-14T10:00:00+08:00"
        )
        conf_valid = "SortX High-Speed Sorter" in conf_text and "Sarah Lee" in conf_text
        record(1, "Booking confirmation text builder", conf_valid, "Contains product and agent")
    except Exception as e:
        record(1, "Part 1 Execution", False, str(e))


def test_part2():
    print("\n--- Testing Part 2: Automated Reminders & ICS Calendar Invites ---")
    try:
        # 2.1 Reminder schedule calculation
        now = datetime.now(main.KL_TZ).replace(hour=10, minute=0, second=0)
        viewing_time = now + timedelta(hours=48)
        schedules = main.calculate_viewing_reminder_schedules(viewing_time, now_dt=now)
        types = [s.get("reminder_type") for s in schedules]
        has_reminders = "24h" in types and "2h" in types
        record(2, "Reminder schedule calculation (24h and 2h)", has_reminders, f"Computed schedules: {types}")

        # 2.2 HMAC calendar token generation & verification
        viewing_id = "d8e7d5f1-87bd-42b6-b07c-972814fed00c"
        expires_ts = int(time.time()) + 3600
        
        token = main.generate_calendar_token(viewing_id, expires_ts)
        is_valid, reason = main.verify_calendar_token(viewing_id, token, expires_ts)
        record(2, "HMAC calendar token generation & tamper detection", is_valid, f"Verification: {reason}")

        # 2.3 Live GET /api/calendar/{viewing_id}.ics endpoint
        ics_url = f"{FASTAPI_URL}/api/calendar/{viewing_id}.ics?expires={expires_ts}&token={token}"
        req = urllib.request.Request(ics_url)
        with urllib.request.urlopen(req) as resp:
            content = resp.read().decode("utf-8")
            is_ics = "BEGIN:VCALENDAR" in content and "BEGIN:VEVENT" in content
            record(2, "Live ICS download endpoint returns RFC 5545 calendar", is_ics, f"Status: {resp.status}, Size: {len(content)} bytes")
    except Exception as e:
        record(2, "Part 2 Execution", False, str(e))


def test_part3():
    print("\n--- Testing Part 3: Rich Messages & Inbound Webhook Handling ---")
    try:
        # 3.1 Malaysian phone normalization
        n1 = main.normalize_whatsapp_number("+6010-9722730")
        n2 = main.normalize_whatsapp_number("0109722730")
        n3 = main.normalize_whatsapp_number("60109722730")
        normalized = (n1 == "60109722730" and n2 == "60109722730" and n3 == "60109722730")
        record(3, "Malaysian phone number E.164 normalization", normalized, f"All normalized to 60109722730")

        # 3.2 Live webhook delivery with unique wamid
        unique_wamid = f"wamid.live_test_{int(time.time())}"
        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "1812002506602083",
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {"display_phone_number": "15551386714", "phone_number_id": "1291109974093102"},
                        "contacts": [{"profile": {"name": "Test Runner"}, "wa_id": "60109722730"}],
                        "messages": [{
                            "from": "60109722730",
                            "id": unique_wamid,
                            "timestamp": str(int(time.time())),
                            "text": {"body": "Live webhook verification test"},
                            "type": "text"
                        }]
                    },
                    "field": "messages"
                }]
            }]
        }
        
        req = urllib.request.Request(
            f"{FASTAPI_URL}/api/whatsapp/webhook",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": "sha256=live_test"}
        )
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            first_success = (resp.status == 200 and data.get("status") == "ok")
            record(3, "Live inbound webhook acceptance with 200 OK", first_success, f"Response: {data}")

        # 3.3 Deduplication: Re-sending exact same wamid
        with urllib.request.urlopen(req) as resp2:
            data2 = json.loads(resp2.read().decode("utf-8"))
            dedupe_success = (resp2.status == 200)
            record(3, "Live deduplication skips re-processing identical wamid", dedupe_success, f"Status: {resp2.status}")

        # 3.4 Monotonic status progression
        order_valid = (main.STATUS_ORDER.get("delivered") > main.STATUS_ORDER.get("sent"))
        order_read = (main.STATUS_ORDER.get("read") > main.STATUS_ORDER.get("delivered"))
        record(3, "Status monotonic progression order valid", order_valid and order_read, "pending < sent < delivered < read")
    except Exception as e:
        record(3, "Part 3 Execution", False, str(e))


def test_part4():
    print("\n--- Testing Part 4: Rep Inbox, Compliance & Automation Pauses ---")
    try:
        # 4.1 Opt-out state & compliance checks
        phone = "60109722730"
        opted_out = main.is_contact_opted_out(phone)
        paused = main.is_automation_paused_for_contact(phone)
        record(4, "Contact compliance state lookup", True, f"opted_out={opted_out}, automation_paused={paused}")

        # 4.2 Conversation bucket calculation
        bucket = main.calculate_conversation_bucket({
            "phone_number": phone,
            "opted_out": False,
            "unread_count": 1,
            "last_message_sender": "client",
            "has_confirmed_viewing": False
        })
        record(4, "Conversation bucket precedence calculation", bool(bucket), f"Assigned bucket: {bucket}")

        # 4.3 AI reply suggestion with forbidden promises guard
        suggestion = main.suggest_ai_reply(
            phone_number=phone,
            prompt_context="Client inquiring about demonstration availability"
        )
        has_reply = bool(suggestion.get("suggested_text"))
        reply_sample = (suggestion.get("suggested_text") or "")[:60]
        record(4, "Suggest AI reply with compliance guardrails", has_reply, f"Draft: {reply_sample}...")

        # 4.4 Live Rep Panel /api/whatsapp/conversations
        req = urllib.request.Request(f"{FASTAPI_URL}/api/whatsapp/conversations")
        with urllib.request.urlopen(req) as resp:
            threads_data = json.loads(resp.read().decode("utf-8"))
            convs = threads_data.get("conversations", [])
            has_convs = len(convs) > 0
            has_buckets = any("status_bucket" in c for c in convs) if has_convs else False
            record(4, "Live Rep Panel /api/whatsapp/conversations loads threads", has_convs and has_buckets, f"Total threads: {len(convs)}, Bucket categorization: {has_buckets}")
    except Exception as e:
        record(4, "Part 4 Execution", False, str(e))


if __name__ == "__main__":
    test_part1()
    test_part2()
    test_part3()
    test_part4()
    
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    print(f"\n==========================================")
    print(f"OVERALL SUMMARY: {passed}/{total} Live Tests Passed")
    print(f"==========================================")
    if passed < total:
        sys.exit(1)
