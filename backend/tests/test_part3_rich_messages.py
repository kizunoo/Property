import os
import sys
import json
import time
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from main import (
    app,
    KL_TZ,
    normalize_whatsapp_number,
    validate_unit_image_url,
    generate_calendar_token,
    verify_calendar_token,
    generate_google_calendar_url,
    generate_ics_download_url,
    build_booking_confirmation_text,
    send_pitch_via_whatsapp,
    process_interactive_button_reply,
    process_due_whatsapp_reminders,
    receive_whatsapp_webhook,
    _PROCESSED_WEBHOOK_MSG_IDS,
    _ICS_RATE_LIMITS,
    WHATSAPP_MESSAGE_HISTORY,
    WHATSAPP_SLOT_OFFERS,
    WHATSAPP_REMINDERS_STORE,
    persist_slot_offer,
)


class TestPart3RichMessages(unittest.TestCase):

    def setUp(self):
        os.environ["ENABLE_WA_SIMULATOR"] = "true"
        os.environ["WHATSAPP_DRY_RUN"] = "true"
        os.environ["WHATSAPP_USE_MEMORY_STORE"] = "true"
        os.environ["WHATSAPP_TEST_MODE"] = "true"
        os.environ["CALENDAR_SIGNING_SECRET"] = "test_calendar_secret_xyz_2026"
        os.environ["PUBLIC_BASE_URL"] = "http://localhost:3000"
        os.environ["WHATSAPP_APP_SECRET"] = ""

        import main
        main.WHATSAPP_USE_MEMORY_STORE = True
        main.CALENDAR_SIGNING_SECRET = "test_calendar_secret_xyz_2026"
        main.PUBLIC_BASE_URL = "http://localhost:3000"
        main.WHATSAPP_APP_SECRET = None

        _PROCESSED_WEBHOOK_MSG_IDS.clear()
        _ICS_RATE_LIMITS.clear()
        WHATSAPP_MESSAGE_HISTORY.clear()
        WHATSAPP_SLOT_OFFERS.clear()
        WHATSAPP_REMINDERS_STORE.clear()
        main.WHATSAPP_AUTOMATION_PAUSED_PHONES.clear()

        self.client = TestClient(app)

        # Mock Meta requests
        self.mock_meta_patch = patch("main._send_meta_request", return_value={
            "messaging_product": "whatsapp",
            "contacts": [{"input": "60109722730", "wa_id": "60109722730"}],
            "messages": [{"id": "wamid.mock_part3_123"}],
            "status": "delivered",
            "simulated": True,
        })
        self.mock_meta = self.mock_meta_patch.start()

        # Mock Supabase
        self.mock_sb_patch = patch("main.supabase")
        self.mock_sb = self.mock_sb_patch.start()
        self.mock_table = MagicMock()
        self.current_table = None

        def get_tbl(name):
            self.current_table = name
            return self.mock_table

        self.mock_sb.table.side_effect = get_tbl
        self.mock_table.select.return_value = self.mock_table
        self.mock_table.eq.return_value = self.mock_table
        self.mock_table.gte.return_value = self.mock_table
        self.mock_table.lte.return_value = self.mock_table
        self.mock_table.in_.return_value = self.mock_table
        self.mock_table.not_.return_value = self.mock_table
        self.mock_table.is_.return_value = self.mock_table
        self.mock_table.order.return_value = self.mock_table
        self.mock_table.limit.return_value = self.mock_table
        self.mock_table.single.return_value = self.mock_table
        self.mock_table.update.return_value = self.mock_table
        self.mock_table.insert.return_value = self.mock_table
        self.mock_table.upsert.return_value = self.mock_table

        def mock_execute():
            if self.current_table == "agents":
                return MagicMock(data=[{"id": "agent-1", "name": "Elena Rostova"}])
            if self.current_table == "properties":
                return MagicMock(data=[{
                    "id": "prop-1",
                    "address": "Unit 12-A, The Horizon",
                    "neighborhood": "Bangsar South",
                    "image_url": "https://images.pexels.com/photos/256381/pexels-photo-256381.jpeg",
                }])
            if self.current_table == "clients":
                return MagicMock(data=[{"id": "client-1", "name": "Sarah Jenkins", "whatsapp_number": "60109722730", "assigned_agent_id": "agent-1"}])
            if self.current_table == "scheduled_viewings":
                return MagicMock(data=[{
                    "id": "viewing-part3-123",
                    "scheduled_at": "2026-10-15T14:00:00+08:00",
                    "status": "upcoming",
                    "properties": {"address": "Unit 12-A, The Horizon"},
                    "agents": {"name": "Elena Rostova"},
                }])
            if self.current_table == "whatsapp_messages":
                return MagicMock(data=[])
            return MagicMock(data=[])

        self.mock_table.execute.side_effect = mock_execute

    def tearDown(self):
        self.mock_meta_patch.stop()
        self.mock_sb_patch.stop()

    def test_01_malaysian_phone_normalization(self):
        """Test normalization for various Malaysian and international formats."""
        self.assertEqual(normalize_whatsapp_number("010-9722730"), "60109722730")
        self.assertEqual(normalize_whatsapp_number("+60 10 972 2730"), "60109722730")
        self.assertEqual(normalize_whatsapp_number("60109722730"), "60109722730")
        self.assertEqual(normalize_whatsapp_number("012-345 6789"), "60123456789")
        self.assertEqual(normalize_whatsapp_number("03-8888 1234"), "60388881234")
        self.assertEqual(normalize_whatsapp_number("+1 (555) 123-4567"), "15551234567")
        self.assertEqual(normalize_whatsapp_number(""), "")
        self.assertEqual(normalize_whatsapp_number(None), "")

    def test_02_unit_image_validation(self):
        """Test image URL validation rules."""
        # Valid https with extension
        is_val, _ = validate_unit_image_url("https://images.pexels.com/photos/123/img.jpg")
        self.assertTrue(is_val)

        # Insecure http must be rejected
        is_val, reason = validate_unit_image_url("http://insecure.com/unit.jpg")
        self.assertFalse(is_val)
        self.assertIn("HTTPS", reason)

        # Empty / None must be rejected
        is_val, reason = validate_unit_image_url(None)
        self.assertFalse(is_val)

    def test_03_calendar_signing_and_tamper_detection(self):
        """Dedicated CALENDAR_SIGNING_SECRET creates valid HMAC tokens; tampered/expired tokens are rejected."""
        viewing_id = "viewing-part3-123"
        future_ts = int((datetime.now(timezone.utc) + timedelta(days=7)).timestamp())
        past_ts = int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp())

        token = generate_calendar_token(viewing_id, future_ts)
        self.assertTrue(bool(token))

        # 1. Valid token passes
        is_val, reason = verify_calendar_token(viewing_id, token, future_ts)
        self.assertTrue(is_val)

        # 2. Tampered token fails
        is_val, reason = verify_calendar_token(viewing_id, token + "tampered", future_ts)
        self.assertFalse(is_val)
        self.assertIn("Invalid token", reason)

        # 3. Wrong viewing_id fails
        is_val, reason = verify_calendar_token("wrong-viewing-id", token, future_ts)
        self.assertFalse(is_val)

        # 4. Expired timestamp fails
        expired_token = generate_calendar_token(viewing_id, past_ts)
        is_val, reason = verify_calendar_token(viewing_id, expired_token, past_ts)
        self.assertFalse(is_val)
        self.assertIn("expired", reason.lower())

    def test_04_booking_confirmation_contains_calendar_links(self):
        """Booking confirmation text includes Google Calendar link and signed .ics link with neutral location."""
        viewing_id = "viewing-test-777"
        iso_time = "2026-10-15T14:00:00+08:00"

        text = build_booking_confirmation_text(
            prop_name="Unit 12-A, The Horizon",
            slot_label="Thu 15 Oct, 2:00 PM",
            agent_name="Elena Rostova",
            viewing_id=viewing_id,
            scheduled_at_iso=iso_time,
        )

        self.assertIn("Unit 12-A, The Horizon", text)
        self.assertIn("Thu 15 Oct, 2:00 PM", text)
        self.assertNotIn("📅 Add to Calendar:", text)
        self.assertNotIn("calendar.google.com", text)
        self.assertNotIn(".ics", text)

        # Google calendar URL verification
        gcal_url = generate_google_calendar_url("Unit 12-A, The Horizon", iso_time, "Elena Rostova")
        self.assertIn("Your+facility+%28details+to+be+confirmed+by+Elena+Rostova%29", gcal_url)
        # Neutral location requirement: properties.address or neighborhood NOT in location param
        self.assertNotIn("Bangsar+South", gcal_url)

    def test_05_calendar_ics_endpoint_download(self):
        """GET /api/calendar/{viewing_id}.ics returns RFC 5545 format with minimal payload and neutral location."""
        viewing_id = "viewing-part3-123"
        expires_ts = int((datetime.now(timezone.utc) + timedelta(days=7)).timestamp())
        token = generate_calendar_token(viewing_id, expires_ts)

        response = self.client.get(f"/api/calendar/{viewing_id}.ics?token={token}&expires={expires_ts}")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/calendar", response.headers["content-type"])
        body = response.text

        self.assertIn("BEGIN:VCALENDAR", body)
        self.assertIn("BEGIN:VEVENT", body)
        self.assertIn(f"UID:viewing-{viewing_id}@pipeline-ev.com", body)
        self.assertIn("SUMMARY:On-Site Demonstration: Unit 12-A, The Horizon", body)
        self.assertIn("LOCATION:Your facility (details to be confirmed by Elena Rostova)", body)
        self.assertIn("END:VEVENT", body)
        self.assertIn("END:VCALENDAR", body)

    def test_06_calendar_ics_tampered_and_expired(self):
        """GET /api/calendar/{viewing_id}.ics rejects tampered and expired requests."""
        viewing_id = "viewing-part3-123"

        # Tampered token -> 403
        future_ts = int((datetime.now(timezone.utc) + timedelta(days=7)).timestamp())
        resp_tampered = self.client.get(f"/api/calendar/{viewing_id}.ics?token=tampered_signature&expires={future_ts}")
        self.assertEqual(resp_tampered.status_code, 403)

        # Expired token -> 401
        past_ts = int((datetime.now(timezone.utc) - timedelta(minutes=5)).timestamp())
        exp_token = generate_calendar_token(viewing_id, past_ts)
        resp_expired = self.client.get(f"/api/calendar/{viewing_id}.ics?token={exp_token}&expires={past_ts}")
        self.assertEqual(resp_expired.status_code, 401)

    def test_07_calendar_ics_rate_limiting(self):
        """Rate limit caps requests at 15 per minute per IP returning 429."""
        viewing_id = "viewing-part3-123"
        expires_ts = int((datetime.now(timezone.utc) + timedelta(days=7)).timestamp())
        token = generate_calendar_token(viewing_id, expires_ts)

        # First 15 requests succeed
        for _ in range(15):
            res = self.client.get(f"/api/calendar/{viewing_id}.ics?token={token}&expires={expires_ts}")
            self.assertEqual(res.status_code, 200)

        # 16th request must trigger 429
        res_limit = self.client.get(f"/api/calendar/{viewing_id}.ics?token={token}&expires={expires_ts}")
        self.assertEqual(res_limit.status_code, 429)
        self.assertIn("Too many calendar download requests", res_limit.json()["detail"])

    def test_08_pitch_image_in_window_only(self):
        """Pitch unit image is only dispatched when 24h window is open, and is logged prior to the slot interactive message."""
        phone = "60109722730"

        # Ensure inside 24h window
        with patch("main.is_within_24h_window", return_value=True):
            res = send_pitch_via_whatsapp({
                "client_id": "client-1",
                "property_id": "prop-1",
                "to_number": phone,
                "attach_image": True,
                "slots": [
                    {"index": 1, "date": "2026-10-16", "time": "10:00", "label": "Fri 16 Oct, 10:00 AM"},
                ],
            })
            self.assertTrue(res.get("image_sent"))
            # Check message ordering in history: image message logged BEFORE interactive message
            msgs = [m for m in WHATSAPP_MESSAGE_HISTORY if m.get("to_number") == phone]
            self.assertGreaterEqual(len(msgs), 2)
            self.assertIn("[Unit Image:", msgs[-2]["text"])
            self.assertIn("Demo Invitation", str(self.mock_meta.call_args_list))

        # Outside window: attach_image is ignored, image is NOT sent
        with patch("main.is_within_24h_window", return_value=False):
            res_outside = send_pitch_via_whatsapp({
                "client_id": "client-1",
                "property_id": "prop-1",
                "to_number": phone,
                "attach_image": True,
                "slots": [
                    {"index": 1, "date": "2026-10-16", "time": "10:00", "label": "Fri 16 Oct, 10:00 AM"},
                ],
            })
            self.assertFalse(res_outside.get("image_sent"))

    def test_09_webhook_unreachable_db_returns_200(self):
        """Meta webhook MUST return HTTP 200 even when database is completely unreachable."""
        payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "entry-1",
                    "changes": [
                        {
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": {"display_phone_number": "60109722730", "phone_number_id": "pn-1"},
                                "messages": [
                                    {
                                        "from": "010-9722730",
                                        "id": "wamid.unreachable_db_test_999",
                                        "timestamp": "1728460000",
                                        "text": {"body": "Hello pipeline team"},
                                        "type": "text",
                                    }
                                ],
                            },
                            "field": "messages",
                        }
                    ],
                }
            ],
        }

        # Simulate unreachable DB by making table() raise an operational connection error
        self.mock_sb.table.side_effect = RuntimeError("Supabase connection timeout: host unreachable")

        response = self.client.post("/api/whatsapp/webhook", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get("status"), "ok")

    def test_10_missing_calendar_secret_returns_503_and_omits_link(self):
        """When CALENDAR_SIGNING_SECRET is missing, .ics link generation returns None and endpoint returns 503."""
        with patch.dict(os.environ, {}, clear=True), patch("main.CALENDAR_SIGNING_SECRET", None):
            # 1. Generation returns None
            url = generate_ics_download_url("viewing-123")
            self.assertIsNone(url)

            # 2. Endpoint returns 503
            resp = self.client.get("/api/calendar/viewing-123.ics?token=xyz&expires=1234567890")
            self.assertEqual(resp.status_code, 503)
            self.assertIn("not configured", resp.json()["detail"].lower())

    def test_11_missing_public_base_url_omits_ics_retains_gcal(self):
        """When PUBLIC_BASE_URL is missing, .ics link is omitted and Google Calendar is also not present."""
        with patch.dict(os.environ, {"CALENDAR_SIGNING_SECRET": "secret_123"}, clear=True), patch("main.PUBLIC_BASE_URL", None):
            text = build_booking_confirmation_text(
                prop_name="Unit 12-A, The Horizon",
                slot_label="Thu 15 Oct, 2:00 PM",
                agent_name="Elena Rostova",
                viewing_id="viewing-777",
                scheduled_at_iso="2026-10-15T14:00:00+08:00",
            )
            self.assertNotIn("calendar.google.com", text)
            self.assertNotIn("/api/calendar/", text)
            self.assertNotIn(".ics", text)

    def test_12_webhook_signature_failure_returns_403(self):
        """Webhook request with invalid HMAC signature must return HTTP 403."""
        with patch.dict(os.environ, {"WHATSAPP_APP_SECRET": "test_app_secret_999"}):
            import main
            main.WHATSAPP_APP_SECRET = "test_app_secret_999"
            payload = {"object": "whatsapp_business_account", "entry": []}
            headers = {"X-Hub-Signature-256": "sha256=invalid_hex_digest_0000000000"}

            resp = self.client.post("/api/whatsapp/webhook", json=payload, headers=headers)
            self.assertEqual(resp.status_code, 403)
            self.assertEqual(resp.json()["detail"], "Bad signature")

    def test_13_webhook_dedupe_after_restart_skips_processing(self):
        """If server restarts (in-memory dedupe cleared), duplicate wamid in DB is skipped."""
        wamid = "wamid.restarted_duplicate_001"
        payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "entry-1",
                    "changes": [
                        {
                            "value": {
                                "messaging_product": "whatsapp",
                                "messages": [
                                    {
                                        "from": "60109722730",
                                        "id": wamid,
                                        "timestamp": "1728460000",
                                        "text": {"body": "Test message after reboot"},
                                        "type": "text",
                                    }
                                ],
                            },
                            "field": "messages",
                        }
                    ],
                }
            ],
        }

        # Clear in-memory cache to simulate cold process restart
        _PROCESSED_WEBHOOK_MSG_IDS.clear()

        # Mock DB returning existing row for this wamid
        def mock_execute_dup():
            if self.current_table == "whatsapp_messages":
                return MagicMock(data=[{"id": wamid}])
            return MagicMock(data=[])

        self.mock_table.execute.side_effect = mock_execute_dup

        initial_history_len = len(WHATSAPP_MESSAGE_HISTORY)
        response = self.client.post("/api/whatsapp/webhook", json=payload)
        self.assertEqual(response.status_code, 200)

        # Confirm message was NOT re-processed or added to history
        new_msgs = [m for m in WHATSAPP_MESSAGE_HISTORY if m.get("id") == wamid]
        self.assertEqual(len(new_msgs), 0)

    def test_14_image_failure_falls_back_to_slot_dispatch_with_warning(self):
        """If unit image dispatch fails, interactive slot dispatch still proceeds and warning is returned."""
        phone = "60109722730"

        # Mock _send_meta_request to fail on image send (first call) but succeed on slot message (second call)
        call_count = [0]
        def side_effect_meta(payload):
            call_count[0] += 1
            if payload.get("type") == "image":
                raise RuntimeError("Meta Cloud API image upload failed: 500 internal")
            return {
                "messaging_product": "whatsapp",
                "messages": [{"id": "wamid.slot_msg_succeeded"}],
                "status": "delivered",
            }

        with patch("main._send_meta_request", side_effect=side_effect_meta), \
             patch("main.is_within_24h_window", return_value=True):
            res = send_pitch_via_whatsapp({
                "client_id": "client-1",
                "property_id": "prop-1",
                "to_number": phone,
                "attach_image": True,
                "slots": [
                    {"index": 1, "date": "2026-10-16", "time": "10:00", "label": "Fri 16 Oct, 10:00 AM"},
                ],
            })

            # Image failed, but slot dispatch succeeded
            self.assertFalse(res.get("image_sent"))
            self.assertIsNotNone(res.get("image_warning"))
            self.assertIn("Meta Cloud API image upload failed", res["image_warning"])
            self.assertEqual(res["message"]["status"], "sent")

    def test_15_in_window_reminder_contains_calendar_link(self):
        """In-window interactive reminder message includes calendar link."""
        phone = "60109722730"
        scheduled_iso = "2026-10-15T14:00:00+08:00"

        WHATSAPP_REMINDERS_STORE.append({
            "id": "rem-test-001",
            "viewing_id": "viewing-part3-123",
            "client_id": "client-1",
            "agent_id": "agent-1",
            "phone_number": phone,
            "reminder_type": "24h",
            "scheduled_send_time": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
            "status": "pending",
        })

        with patch("main.is_within_24h_window", return_value=True), \
             patch("main.WHATSAPP_USE_MEMORY_STORE", True):
            dispatched = process_due_whatsapp_reminders(limit=10)
            self.assertEqual(len(dispatched), 1)

            # Check sent payload contains Add to Calendar link
            sent_payloads = [call_args[0][0] for call_args in self.mock_meta.call_args_list if call_args[0]]
            interactive_payloads = [p for p in sent_payloads if p.get("type") == "interactive"]
            self.assertGreaterEqual(len(interactive_payloads), 1)
            reminder_text = interactive_payloads[-1]["interactive"]["body"]["text"]
            self.assertNotIn("calendar.google.com", reminder_text)


if __name__ == "__main__":
    unittest.main()
