import os
import sys
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import (
    KL_TZ,
    send_pitch_via_whatsapp,
    simulate_incoming_whatsapp_message,
    process_interactive_button_reply,
    get_slot_offer_by_id,
    WHATSAPP_SLOT_OFFERS,
)


class TestPart1InteractiveSimulation(unittest.TestCase):

    def setUp(self):
        os.environ["ENABLE_WA_SIMULATOR"] = "true"
        os.environ["WHATSAPP_DRY_RUN"] = "true"
        os.environ["WHATSAPP_USE_MEMORY_STORE"] = "true"
        os.environ["WHATSAPP_TEST_MODE"] = "true"

        import main
        main.WHATSAPP_USE_MEMORY_STORE = True

        # Mock Meta requests to prevent any outbound network calls
        self.mock_sender_patch = patch("main._send_meta_request", return_value={
            "messaging_product": "whatsapp",
            "contacts": [{"input": "60109722730", "wa_id": "60109722730"}],
            "messages": [{"id": "wamid.mock_interactive_123"}],
            "status": "delivered",
            "simulated": True,
        })
        self.mock_sender = self.mock_sender_patch.start()

        # Mock Supabase table queries to avoid external latency
        self.mock_supabase_patch = patch("main.supabase")
        self.mock_supabase = self.mock_supabase_patch.start()

        mock_tbl = MagicMock()
        self.current_table = None

        def get_table(name):
            self.current_table = name
            return mock_tbl

        self.mock_supabase.table.side_effect = get_table
        mock_tbl.select.return_value = mock_tbl
        mock_tbl.eq.return_value = mock_tbl
        mock_tbl.single.return_value = mock_tbl
        mock_tbl.order.return_value = mock_tbl
        mock_tbl.limit.return_value = mock_tbl
        mock_tbl.update.return_value = mock_tbl
        mock_tbl.insert.return_value = mock_tbl
        mock_tbl.upsert.return_value = mock_tbl

        def mock_execute():
            if self.current_table == "clients":
                return MagicMock(data=[{"name": "Client Acme", "assigned_agent_id": "agent-rep-789"}])
            if self.current_table == "agents":
                return MagicMock(data=[{"name": "R. Delgado", "id": "agent-rep-789"}])
            if self.current_table == "properties":
                return MagicMock(data=[{"address": "Bay 14 Robotics Site", "neighborhood": "Klang Valley"}])
            if self.current_table == "scheduled_viewings":
                return MagicMock(data=[{"id": "viewing-123", "status": "upcoming"}])
            # For whatsapp_slot_offers and others, return empty so memory store acts as clean source of truth
            return MagicMock(data=[])

        mock_tbl.execute.side_effect = mock_execute

    def tearDown(self):
        self.mock_sender_patch.stop()
        self.mock_supabase_patch.stop()

    def test_end_to_end_button_flow_simulation(self):
        """
        Tests complete interactive loop:
        1. Rep sends pitch with structured slots.
        2. Client taps Button for Option 2 (payload: slot_pick:{offer_id}:2).
        3. Webhook/simulator routes deterministically by button ID (NO LLM).
        4. Booking is confirmed, stage updated, confirmation sent.
        5. Duplicate button tap is safely rejected.
        """
        now_kl = datetime.now(KL_TZ)
        base_day = now_kl + timedelta(days=2)
        while base_day.weekday() >= 5:
            base_day += timedelta(days=1)

        slot1_dt = base_day.replace(hour=10, minute=0, second=0, microsecond=0)
        slot2_dt = base_day.replace(hour=14, minute=0, second=0, microsecond=0)
        slot3_dt = base_day.replace(hour=16, minute=0, second=0, microsecond=0)

        slots = [
            {"index": 1, "label": slot1_dt.strftime("%a %d %b, %I:%M %p"), "slot_iso": slot1_dt.isoformat()},
            {"index": 2, "label": slot2_dt.strftime("%a %d %b, %I:%M %p"), "slot_iso": slot2_dt.isoformat()},
            {"index": 3, "label": slot3_dt.strftime("%a %d %b, %I:%M %p"), "slot_iso": slot3_dt.isoformat()},
        ]

        test_phone = "60109722730"

        # ── Step 1: Rep dispatches pitch ─────────────────────────────────────
        pitch_res = send_pitch_via_whatsapp({
            "client_id": "client-abc-123",
            "property_id": "prop-xyz-456",
            "sender_agent_id": "agent-rep-789",
            "to_number": test_phone,
            "slots": slots,
            "message_text": "Outreach pitch with proposed demo times",
        })

        offer = pitch_res["slot_offer"]
        offer_id = offer["id"]
        self.assertIsNotNone(offer_id)
        self.assertEqual(offer["status"], "open")
        self.assertEqual(len(offer["slots"]), 3)

        # ── Step 2: Client taps Button 2 in simulation ────────────────────────
        button_payload = f"slot_pick:{offer_id}:2"
        sim_res = simulate_incoming_whatsapp_message({
            "from_number": test_phone,
            "button_payload": button_payload,
            "button_title": "Option 2",
            "client_id": "client-abc-123",
            "client_name": "Client Acme",
        })

        self.assertTrue(sim_res["success"])
        auto_sched = sim_res["auto_scheduling"]
        self.assertEqual(auto_sched["action"], "booked")
        self.assertEqual(auto_sched["slot_label"], slots[1]["label"])
        self.assertEqual(auto_sched["scheduled_at"], slot2_dt.isoformat())

        # Verify offer is now marked booked in state
        stored_offer = get_slot_offer_by_id(offer_id)
        self.assertEqual(stored_offer["status"], "booked")
        self.assertEqual(stored_offer.get("booked_slot_index"), 2)

        # ── Step 3: Concurrency / Double-tap prevention ───────────────────────
        dup_res = simulate_incoming_whatsapp_message({
            "from_number": test_phone,
            "button_payload": button_payload,
            "button_title": "Option 2",
            "client_id": "client-abc-123",
        })
        self.assertEqual(dup_res["auto_scheduling"]["action"], "offer_expired_or_already_booked")

    def test_reschedule_button_flow_simulation(self):
        """
        Tests that tapping 'Different time' generates and sends fresh alternative slots.
        """
        offer_id = "test-offer-resched-part1"
        WHATSAPP_SLOT_OFFERS.append({
            "id": offer_id,
            "client_id": "c-1",
            "property_id": "prop-xyz",
            "agent_id": "agent-rep-789",
            "status": "open",
            "slots": [],
            "phone_number": "60109722730",
        })

        sim_res = simulate_incoming_whatsapp_message({
            "from_number": "60109722730",
            "button_payload": f"action:{offer_id}:reschedule",
            "button_title": "Different time",
        })

        auto_sched = sim_res["auto_scheduling"]
        self.assertEqual(auto_sched["action"], "reschedule_slots_sent")
        self.assertIn("new_offer_id", auto_sched)

    def test_talk_to_human_button_flow_simulation(self):
        """
        Tests that tapping 'Talk to a person' notifies the rep without booking.
        """
        offer_id = "test-offer-human-part1"
        WHATSAPP_SLOT_OFFERS.append({
            "id": offer_id,
            "client_id": "c-1",
            "property_id": "prop-xyz",
            "agent_id": "agent-rep-789",
            "status": "open",
            "slots": [],
            "phone_number": "60109722730",
        })

        sim_res = simulate_incoming_whatsapp_message({
            "from_number": "60109722730",
            "button_payload": f"action:{offer_id}:human",
            "button_title": "Talk to a person",
        })

        auto_sched = sim_res["auto_scheduling"]
        self.assertEqual(auto_sched["action"], "human_handoff_requested")


if __name__ == "__main__":
    unittest.main()
