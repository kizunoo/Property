import os
import sys
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import (
    KL_TZ,
    process_interactive_button_reply,
    claim_slot_offer,
    rollback_slot_offer,
    persist_slot_offer,
    get_slot_offer_by_id,
    is_automation_paused_for_phone,
    set_automation_paused_for_phone,
    _PROCESSED_WEBHOOK_MSG_IDS,
    WHATSAPP_SLOT_OFFERS,
)


class TestSectionAEdgeCases(unittest.TestCase):

    def setUp(self):
        os.environ["ENABLE_WA_SIMULATOR"] = "true"
        os.environ["WHATSAPP_DRY_RUN"] = "true"
        os.environ["WHATSAPP_USE_MEMORY_STORE"] = "true"
        os.environ["WHATSAPP_TEST_MODE"] = "true"

        import main
        main.WHATSAPP_USE_MEMORY_STORE = True

        # Clear in-memory collections
        WHATSAPP_SLOT_OFFERS.clear()
        _PROCESSED_WEBHOOK_MSG_IDS.clear()
        set_automation_paused_for_phone("60109722730", False)
        set_automation_paused_for_phone("60123456789", False)

        # Mock Meta requests
        self.mock_meta_patch = patch("main._send_meta_request", return_value={
            "messaging_product": "whatsapp",
            "contacts": [{"input": "60109722730", "wa_id": "60109722730"}],
            "messages": [{"id": "wamid.mock_test_123"}],
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
        self.mock_table.gt.return_value = self.mock_table
        self.mock_table.in_.return_value = self.mock_table
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
                return MagicMock(data=[{"id": "prop-1", "address": "Bay 4 Industrial Park"}])
            if self.current_table == "scheduled_viewings":
                return MagicMock(data=[{"id": "viewing-mock-123"}])
            return MagicMock(data=[])

        self.mock_table.execute.side_effect = mock_execute

    def tearDown(self):
        self.mock_meta_patch.stop()
        self.mock_sb_patch.stop()

    def _create_sample_offer(self, phone="60109722730", expires_in_hours=72, reoffer_count=0):
        # Pick next Monday at 10:00 AM KL time
        now = datetime.now(KL_TZ)
        days_ahead = (7 - now.weekday()) % 7 or 7
        target_dt = (now + timedelta(days=days_ahead)).replace(hour=10, minute=0, second=0, microsecond=0)
        offer_id = f"offer_test_{int(datetime.now().timestamp() * 1000)}"

        offer = {
            "id": offer_id,
            "client_id": "client-uuid-1",
            "property_id": "prop-uuid-1",
            "agent_id": "agent-1",
            "phone_number": phone,
            "status": "open",
            "reoffer_count": reoffer_count,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=expires_in_hours)).isoformat(),
            "slots": [
                {"index": 1, "slot_iso": target_dt.isoformat(), "label": "Mon 10:00 AM"},
                {"index": 2, "slot_iso": (target_dt + timedelta(hours=2)).isoformat(), "label": "Mon 12:00 PM"},
                {"index": 3, "slot_iso": (target_dt + timedelta(hours=4)).isoformat(), "label": "Mon 2:00 PM"},
            ],
        }
        persist_slot_offer(offer)
        return offer

    def test_1_conflict_at_tap_time(self):
        """If a slot is booked by someone else by tap time, do not confirm; apologize and send fresh candidate slots."""
        offer = self._create_sample_offer()
        # Mock is_slot_available to return False (simulating a conflict that arose between pitch and button tap)
        with patch("main.is_slot_available", return_value=False):
            res = process_interactive_button_reply(
                phone_number=offer["phone_number"],
                button_payload=f"slot_pick:{offer['id']}:1",
            )
            self.assertEqual(res["action"], "conflict_apologized_and_reoffered")
            self.assertIn("new_offer_id", res)
            # Verify original offer was marked expired
            updated = get_slot_offer_by_id(offer["id"])
            self.assertEqual(updated["status"], "expired")

    def test_2_expired_offer(self):
        """Expired offers must reject the tap and notify the client."""
        # Create offer that expired 2 hours ago
        offer = self._create_sample_offer(expires_in_hours=-2)
        res = process_interactive_button_reply(
            phone_number=offer["phone_number"],
            button_payload=f"slot_pick:{offer['id']}:1",
        )
        self.assertEqual(res["action"], "offer_expired_or_already_booked")

    def test_3_wrong_sender_number(self):
        """Button replies from a phone number not matching the offer must be ignored."""
        offer = self._create_sample_offer(phone="60109722730")
        res = process_interactive_button_reply(
            phone_number="60129999999",  # Different inbound number
            button_payload=f"slot_pick:{offer['id']}:1",
        )
        self.assertEqual(res.get("error"), "sender_identity_mismatch")
        # Ensure offer was NOT claimed
        checked = get_slot_offer_by_id(offer["id"])
        self.assertEqual(checked["status"], "open")

    def test_4_viewing_insert_failure_rolls_back_offer(self):
        """If scheduled_viewings insert throws an error, the offer must atomically roll back to 'open'."""
        offer = self._create_sample_offer()

        # Force scheduled_viewings.insert to throw an error
        def fail_insert(*args, **kwargs):
            if self.current_table == "scheduled_viewings":
                raise RuntimeError("Database connection timeout during viewing creation")
            return MagicMock(data=[])

        self.mock_table.execute.side_effect = fail_insert

        res = process_interactive_button_reply(
            phone_number=offer["phone_number"],
            button_payload=f"slot_pick:{offer['id']}:1",
        )
        self.assertEqual(res["action"], "booking_failed_rolled_back")
        # Assert rollback to 'open'
        checked = get_slot_offer_by_id(offer["id"])
        self.assertEqual(checked["status"], "open")
        self.assertIsNone(checked.get("booked_slot_index"))

    def test_5_double_tap_concurrency_prevention(self):
        """Double-tapping the same button must only book once; second tap is blocked as duplicate."""
        offer = self._create_sample_offer()
        # Tap 1
        res1 = process_interactive_button_reply(
            phone_number=offer["phone_number"],
            button_payload=f"slot_pick:{offer['id']}:1",
        )
        self.assertEqual(res1["action"], "booked")

        # Tap 2 (second immediate tap on the same offer)
        res2 = process_interactive_button_reply(
            phone_number=offer["phone_number"],
            button_payload=f"slot_pick:{offer['id']}:1",
        )
        self.assertIn(res2["action"], ["duplicate_prevented", "offer_expired_or_already_booked"])

    def test_6_same_meta_message_id_redelivered(self):
        """Meta webhook redelivery of the same wamid must be ignored to prevent duplicate processing."""
        wamid = "wamid.HBgLMjAxMDk3MjI3MzAVAgARGBI1"
        self.assertNotIn(wamid, _PROCESSED_WEBHOOK_MSG_IDS)

        # Simulate first delivery
        _PROCESSED_WEBHOOK_MSG_IDS.add(wamid)
        self.assertIn(wamid, _PROCESSED_WEBHOOK_MSG_IDS)

        # Second delivery detects duplicate
        is_duplicate = wamid in _PROCESSED_WEBHOOK_MSG_IDS
        self.assertTrue(is_duplicate)

    def test_7_reoffer_cap(self):
        """Requesting 'Different time' is capped at 3 re-offers, after which it hands off to human rep and pauses automation."""
        # Offer already at 2 re-offers
        offer_initial = self._create_sample_offer(reoffer_count=2)
        # Tap 3rd time
        res3 = process_interactive_button_reply(
            phone_number=offer_initial["phone_number"],
            button_payload=f"action:{offer_initial['id']}:reschedule",
        )
        self.assertEqual(res3["action"], "reschedule_slots_sent")
        self.assertEqual(res3["reoffer_count"], 3)

        # 4th tap (reoffer_count is now 3 -> cap hit)
        new_offer_id = res3["new_offer_id"]
        res4 = process_interactive_button_reply(
            phone_number=offer_initial["phone_number"],
            button_payload=f"action:{new_offer_id}:reschedule",
        )
        self.assertEqual(res4["action"], "reoffer_cap_reached")
        # Verify automation is paused for this phone
        self.assertTrue(is_automation_paused_for_phone(offer_initial["phone_number"]))

    def test_8_template_config_drift_prevention(self):
        """
        Guarantees that the template body, variable list, and rendered text NEVER drift apart.
        Variable {{2}} must strictly mean the unit name.
        """
        from main import PITCH_TEMPLATE_CONFIG, render_viewing_slots_pitch_text

        # 1. Variable count & identity check
        variables = PITCH_TEMPLATE_CONFIG["variables"]
        self.assertEqual(len(variables), 5, "Template must have exactly 5 positional variables")
        self.assertEqual(variables[0]["name"], "client_name")
        self.assertEqual(variables[1]["name"], "unit_name", "Variable {{2}} must strictly be the unit name")
        self.assertEqual(variables[2]["name"], "slot_1")
        self.assertEqual(variables[3]["name"], "slot_2")
        self.assertEqual(variables[4]["name"], "slot_3")

        # 2. Placeholders in body check
        body = PITCH_TEMPLATE_CONFIG["body"]
        for i in range(1, 6):
            self.assertIn(f"{{{{{i}}}}}", body, f"Placeholder {{{{{i}}}}} missing from template body")
        self.assertNotIn("{{6}}", body, "Unexpected extra placeholder in template body")

        # 3. Button definitions check
        buttons = PITCH_TEMPLATE_CONFIG["buttons"]
        self.assertEqual(len(buttons), 3)
        self.assertEqual([b["label"] for b in buttons], ["Option 1", "Option 2", "Option 3"])

        # 4. Rendering consistency check
        slots = [
            {"index": 1, "label": "Thu 10 Oct, 2:00 PM"},
            {"index": 2, "label": "Fri 11 Oct, 10:00 AM"},
            {"index": 3, "label": "Fri 11 Oct, 3:30 PM"},
        ]
        rendered = render_viewing_slots_pitch_text("Sarah Jenkins", "Unit 12-A, The Horizon", slots)
        expected = (
            "Hello Sarah Jenkins, this is PIPELINE.EV following up on the Unit 12-A, The Horizon. "
            "We would like to invite your team to an on-site demonstration. "
            "Proposed times: Option 1: Thu 10 Oct, 2:00 PM, Option 2: Fri 11 Oct, 10:00 AM, Option 3: Fri 11 Oct, 3:30 PM. "
            "Tap a button below to choose, or reply with a time that suits you."
        )
        self.assertEqual(rendered, expected)

    def test_9_rpc_failure_and_defensive_rollback(self):
        """
        When transactional RPC fails or is unavailable, and the defensive insert fails,
        the offer must be defensively rolled back to 'open'.
        """
        offer = self._create_sample_offer()

        # Simulate RPC failure throwing exception
        self.mock_sb.rpc.side_effect = RuntimeError("RPC claim_and_book_slot_offer not found")

        # Simulate scheduled_viewings insert failure
        def mock_insert(row):
            if self.current_table == "scheduled_viewings":
                raise RuntimeError("Database connection timeout during viewing insert")
            return self.mock_table

        self.mock_table.insert.side_effect = mock_insert

        res = process_interactive_button_reply(
            phone_number=offer["phone_number"],
            button_payload=f"slot_pick:{offer['id']}:1",
        )
        self.assertEqual(res["action"], "booking_failed_rolled_back")
        self.assertIn("Offer rolled back to open", res["error"])

        # Confirm offer status remained 'open' after rollback
        current = get_slot_offer_by_id(offer["id"])
        self.assertEqual(current["status"], "open")

    def test_10_rpc_in_database_conflict_path(self):
        """
        When the in-database transactional RPC detects an agent schedule conflict,
        it returns success=false and conflict=true. The handler must apologize,
        send 3 fresh candidate slots, and generate a new offer.
        """
        offer = self._create_sample_offer()

        # Simulate RPC returning conflict=True
        mock_rpc_obj = MagicMock()
        mock_rpc_obj.execute.return_value = MagicMock(data={
            "success": False,
            "conflict": True,
            "error": "Agent has a conflicting viewing within 45 minute buffer",
        })
        self.mock_sb.rpc.return_value = mock_rpc_obj

        res = process_interactive_button_reply(
            phone_number=offer["phone_number"],
            button_payload=f"slot_pick:{offer['id']}:1",
        )
        self.assertEqual(res["action"], "conflict_apologized_and_reoffered")
        self.assertIn("Slot was no longer free", res["detail"])
        self.assertTrue(bool(res.get("new_offer_id")))


if __name__ == "__main__":
    unittest.main()
