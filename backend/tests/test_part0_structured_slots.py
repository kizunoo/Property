import os
import sys
import unittest
from datetime import datetime, timedelta, time
from unittest.mock import patch, MagicMock

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import (
    KL_TZ,
    parse_slots_from_text,
    resolve_agent_from_pitch_text,
    send_pitch_via_whatsapp,
    is_within_business_hours,
    BUSINESS_HOURS_START,
    BUSINESS_HOURS_END,
    SLOT_DURATION_MINUTES,
)
from fastapi import HTTPException


class TestStructuredSlotsPart0(unittest.TestCase):

    def setUp(self):
        # Global mock for any WhatsApp HTTP/network dispatchers
        self.mock_sender_patch = patch("main._send_meta_request", return_value={
            "messaging_product": "whatsapp",
            "contacts": [{"input": "60109722730", "wa_id": "60109722730"}],
            "messages": [{"id": "wamid.test_mock_123"}],
            "status": "delivered",
            "simulated": True,
        })
        self.mock_sender = self.mock_sender_patch.start()

        # Global mock for supabase table queries to avoid network delays
        self.mock_supabase_patch = patch("main.supabase")
        self.mock_supabase = self.mock_supabase_patch.start()

        mock_tbl = MagicMock()
        self.mock_supabase.table.return_value = mock_tbl
        mock_tbl.select.return_value = mock_tbl
        mock_tbl.eq.return_value = mock_tbl
        mock_tbl.single.return_value = mock_tbl
        mock_tbl.order.return_value = mock_tbl
        mock_tbl.limit.return_value = mock_tbl
        mock_tbl.update.return_value = mock_tbl
        mock_tbl.insert.return_value = mock_tbl
        mock_tbl.upsert.return_value = mock_tbl
        mock_tbl.execute.return_value = MagicMock(data={"name": "Acme Corp", "address": "Unit 4B"})

    def tearDown(self):
        self.mock_sender_patch.stop()
        self.mock_supabase_patch.stop()

    def test_december_pitch_with_january_slot_rollover(self):
        """
        Test that a slot specified in early January (e.g. 'Mon 5 Jan, 10:00 AM')
        when parsed in fallback infers the nearest FUTURE date.
        """
        sample_text = (
            "Hi there! Would you like a demo? Proposed slots:\n"
            "1) Mon 5 Jan, 10:00 AM  2) Tue 6 Jan, 2:00 PM\n"
            "Reply 1 or 2 to book."
        )
        slots = parse_slots_from_text(sample_text)
        self.assertEqual(len(slots), 2)

        now_kl = datetime.now(KL_TZ)
        for s in slots:
            dt = datetime.fromisoformat(s["slot_iso"])
            self.assertGreater(dt, now_kl - timedelta(minutes=1))
            self.assertEqual(dt.month, 1)

    def test_edited_signoff_does_not_override_sender_agent_id(self):
        """
        Test that editing the text sign-off to another rep's name does NOT change
        the slot offer attribution. sender_agent_id takes absolute precedence.
        """
        agent_a_id = "agent-uuid-alice"

        future_slot_time = (datetime.now(KL_TZ) + timedelta(days=2)).replace(hour=10, minute=0, second=0, microsecond=0)
        while future_slot_time.weekday() >= 5:
            future_slot_time += timedelta(days=1)

        payload = {
            "client_id": "client-123",
            "property_id": "prop-456",
            "sender_agent_id": agent_a_id,
            # Rep edited sign-off to mention Bob instead of Alice
            "message_text": (
                "Hi Acme Corp,\n\nHere are some times.\n\n"
                f"Proposed slots:\n1) {future_slot_time.strftime('%a %d %b, %I:%M %p')}\n\n"
                "Best regards,\nBob Imposter\nSenior Rep"
            ),
            "slots": [
                {
                    "index": 1,
                    "label": future_slot_time.strftime("%a %d %b, %I:%M %p"),
                    "slot_iso": future_slot_time.isoformat(),
                }
            ],
        }

        res = send_pitch_via_whatsapp(payload)
        slot_offer = res["slot_offer"]
        self.assertEqual(slot_offer["agent_id"], agent_a_id)

    def test_edited_slot_labels_preserve_exact_structured_iso(self):
        """
        Test that even if slot labels or surrounding text are edited,
        the stored slot offer keeps the canonical ISO timestamp.
        """
        agent_id = "agent-123"

        future_slot = (datetime.now(KL_TZ) + timedelta(days=3)).replace(hour=14, minute=0, second=0, microsecond=0)
        while future_slot.weekday() >= 5:
            future_slot += timedelta(days=1)

        expected_iso = future_slot.isoformat()

        payload = {
            "client_id": "c-1",
            "property_id": "p-1",
            "sender_agent_id": agent_id,
            "message_text": "Custom text with no standard formatting",
            "slots": [
                {
                    "index": 1,
                    "label": "Custom Informal Label: Sometime Tuesday Afternoon",
                    "slot_iso": expected_iso,
                }
            ],
        }

        res = send_pitch_via_whatsapp(payload)
        self.assertEqual(res["slot_offer"]["slots"][0]["slot_iso"], expected_iso)

    def test_two_agents_with_same_client(self):
        """
        Test that two different agents can propose slots to the same client,
        and their offers remain isolated with respective agent_ids.
        """
        client_id = "shared-client-789"
        agent_1 = "agent-alpha"
        agent_2 = "agent-beta"

        slot_time = (datetime.now(KL_TZ) + timedelta(days=4)).replace(hour=11, minute=0, second=0, microsecond=0)
        while slot_time.weekday() >= 5:
            slot_time += timedelta(days=1)

        res1 = send_pitch_via_whatsapp({
            "client_id": client_id,
            "property_id": "prop-1",
            "sender_agent_id": agent_1,
            "slots": [{"index": 1, "label": "Slot 1", "slot_iso": slot_time.isoformat()}],
            "message_text": "From Agent Alpha",
        })

        res2 = send_pitch_via_whatsapp({
            "client_id": client_id,
            "property_id": "prop-2",
            "sender_agent_id": agent_2,
            "slots": [{"index": 1, "label": "Slot 1", "slot_iso": slot_time.isoformat()}],
            "message_text": "From Agent Beta",
        })

        self.assertEqual(res1["slot_offer"]["agent_id"], agent_1)
        self.assertEqual(res2["slot_offer"]["agent_id"], agent_2)
        self.assertNotEqual(res1["slot_offer"]["id"], res2["slot_offer"]["id"])

    def test_server_validation_rejects_past_slots(self):
        """
        Test server-side rejection (HTTP 400) when a slot is in the past.
        """
        past_iso = (datetime.now(KL_TZ) - timedelta(days=1)).isoformat()
        with self.assertRaises(HTTPException) as cm:
            send_pitch_via_whatsapp({
                "client_id": "c-1",
                "property_id": "p-1",
                "slots": [{"index": 1, "label": "Past Slot", "slot_iso": past_iso}],
            })
        self.assertEqual(cm.exception.status_code, 400)
        self.assertIn("in the past", cm.exception.detail)

    def test_server_validation_rejects_weekend_slots(self):
        """
        Test server-side rejection (HTTP 400) when a slot falls on a weekend.
        """
        dt = datetime.now(KL_TZ) + timedelta(days=1)
        while dt.weekday() != 5:  # 5 = Saturday
            dt += timedelta(days=1)
        dt = dt.replace(hour=10, minute=0)

        with self.assertRaises(HTTPException) as cm:
            send_pitch_via_whatsapp({
                "client_id": "c-1",
                "property_id": "p-1",
                "slots": [{"index": 1, "label": "Weekend Slot", "slot_iso": dt.isoformat()}],
            })
        self.assertEqual(cm.exception.status_code, 400)
        self.assertIn("weekend", cm.exception.detail.lower())

    def test_server_validation_unified_business_hours(self):
        """
        Test unified business hours rule: slots start 09:00 or later,
        and must END by 18:00 including slot length (60 minutes).
        """
        # Find next weekday
        dt = datetime.now(KL_TZ) + timedelta(days=1)
        while dt.weekday() >= 5:
            dt += timedelta(days=1)

        # 1. Starts before 09:00 (e.g. 08:30) -> REJECT
        too_early = dt.replace(hour=8, minute=30, second=0, microsecond=0)
        with self.assertRaises(HTTPException) as cm:
            send_pitch_via_whatsapp({
                "client_id": "c-1",
                "property_id": "p-1",
                "slots": [{"index": 1, "label": "Early Slot", "slot_iso": too_early.isoformat()}],
            })
        self.assertEqual(cm.exception.status_code, 400)
        self.assertIn("business hours", cm.exception.detail.lower())

        # 2. Starts at 17:30 -> Ends at 18:30 (exceeds 18:00) -> REJECT
        too_late = dt.replace(hour=17, minute=30, second=0, microsecond=0)
        with self.assertRaises(HTTPException) as cm:
            send_pitch_via_whatsapp({
                "client_id": "c-1",
                "property_id": "p-1",
                "slots": [{"index": 1, "label": "Late Slot", "slot_iso": too_late.isoformat()}],
            })
        self.assertEqual(cm.exception.status_code, 400)
        self.assertIn("business hours", cm.exception.detail.lower())

        # 3. Starts at 17:00 -> Ends at 18:00 (exactly at close) -> ACCEPT
        valid_close = dt.replace(hour=17, minute=0, second=0, microsecond=0)
        res = send_pitch_via_whatsapp({
            "client_id": "c-1",
            "property_id": "p-1",
            "slots": [{"index": 1, "label": "Valid Close Slot", "slot_iso": valid_close.isoformat()}],
        })
        self.assertEqual(res["slot_offer"]["slots"][0]["slot_iso"], valid_close.isoformat())


if __name__ == "__main__":
    unittest.main()
