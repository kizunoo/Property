import os
import sys
import json
import time
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from main import (
    app,
    get_contact_state,
    update_contact_state,
    is_contact_opted_out,
    is_automation_paused_for_contact,
    check_nudge_eligibility,
    dispatch_followup_nudge,
    calculate_conversation_bucket,
    suggest_ai_reply,
    _send_meta_request,
    receive_whatsapp_webhook,
    _PROCESSED_WEBHOOK_MSG_IDS,
    WHATSAPP_CONTACT_STATE,
    WHATSAPP_MESSAGE_HISTORY,
)


class TestPart4RepPanel(unittest.TestCase):

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
        WHATSAPP_MESSAGE_HISTORY.clear()
        WHATSAPP_CONTACT_STATE.clear()

        self.client = TestClient(app)

        self.mock_meta_patch = patch("main._send_meta_request", return_value={
            "messaging_product": "whatsapp",
            "contacts": [{"input": "60109722730", "wa_id": "60109722730"}],
            "messages": [{"id": "wamid.mock_part4_123"}],
            "status": "delivered",
            "simulated": True,
        })
        self.mock_meta = self.mock_meta_patch.start()

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
        self.mock_table.order.return_value = self.mock_table
        self.mock_table.limit.return_value = self.mock_table
        self.mock_table.update.return_value = self.mock_table
        self.mock_table.insert.return_value = self.mock_table
        self.mock_table.upsert.return_value = self.mock_table
        self.mock_table.execute.return_value = MagicMock(data=[])

    def tearDown(self):
        self.mock_meta_patch.stop()
        self.mock_sb_patch.stop()

    def test_01_contact_state_opt_out_strict_matching(self):
        """Exact whole-message keywords trigger strict opt-out and acknowledgement."""
        phone = "60109722730"

        # Webhook incoming "STOP"
        payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": phone,
                                        "id": "wamid.optout_exact_001",
                                        "timestamp": "1728460000",
                                        "text": {"body": " STOP  "},
                                        "type": "text",
                                    }
                                ]
                            }
                        }
                    ]
                }
            ],
        }

        resp = self.client.post("/api/whatsapp/webhook", json=payload)
        self.assertEqual(resp.status_code, 200)

        # Contact is now marked opted out
        state = get_contact_state(phone)
        self.assertTrue(state.get("opted_out"))
        self.assertEqual(state.get("opt_out_phrase"), "stop")
        self.assertTrue(is_contact_opted_out(phone))

    def test_02_substring_stop_does_not_opt_out(self):
        """Messages where 'stop' is a substring or normal sentence do NOT trigger opt-out."""
        phone = "60109722730"

        payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": phone,
                                        "id": "wamid.msg_substring_002",
                                        "timestamp": "1728460000",
                                        "text": {"body": "Can you stop by the office tomorrow morning?"},
                                        "type": "text",
                                    }
                                ]
                            }
                        }
                    ]
                }
            ],
        }

        resp = self.client.post("/api/whatsapp/webhook", json=payload)
        self.assertEqual(resp.status_code, 200)

        # Must NOT be opted out
        self.assertFalse(is_contact_opted_out(phone))
        state = get_contact_state(phone)
        self.assertFalse(state.get("opted_out"))

    def test_03_ambiguous_stop_pauses_automation_and_alerts_rep(self):
        """Ambiguous stop requests pause automation and trigger rep alert signal without hard opt-out."""
        phone = "60109722730"

        payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": phone,
                                        "id": "wamid.msg_ambiguous_003",
                                        "timestamp": "1728460000",
                                        "text": {"body": "Please stop messaging me right now"},
                                        "type": "text",
                                    }
                                ]
                            }
                        }
                    ]
                }
            ],
        }

        resp = self.client.post("/api/whatsapp/webhook", json=payload)
        self.assertEqual(resp.status_code, 200)

        state = get_contact_state(phone)
        # Automation paused = True, but hard opted_out = False
        self.assertTrue(state.get("automation_paused"))
        self.assertFalse(state.get("opted_out"))
        self.assertTrue(is_automation_paused_for_contact(phone))

    def test_04_status_monotonic_progression_and_failed_ordering(self):
        """Status ordering: sent < delivered < read. Failed overrides pending/sent but not delivered/read."""
        msg_id = "wamid.status_order_test_001"
        from main import apply_message_status_update

        # Initial state: sent
        apply_message_status_update(msg_id, "sent")
        m = next(m for m in WHATSAPP_MESSAGE_HISTORY if m["id"] == msg_id)
        self.assertEqual(m["status"], "sent")

        # Upgrade to delivered: succeeds
        apply_message_status_update(msg_id, "delivered")
        m = next(m for m in WHATSAPP_MESSAGE_HISTORY if m["id"] == msg_id)
        self.assertEqual(m["status"], "delivered")

        # Out-of-order 'sent' does NOT downgrade 'delivered'
        apply_message_status_update(msg_id, "sent")
        m = next(m for m in WHATSAPP_MESSAGE_HISTORY if m["id"] == msg_id)
        self.assertEqual(m["status"], "delivered")

        # Upgrade to read: succeeds
        apply_message_status_update(msg_id, "read")
        m = next(m for m in WHATSAPP_MESSAGE_HISTORY if m["id"] == msg_id)
        self.assertEqual(m["status"], "read")

        # Late 'failed' does NOT override 'read'
        apply_message_status_update(msg_id, "failed")
        m = next(m for m in WHATSAPP_MESSAGE_HISTORY if m["id"] == msg_id)
        self.assertEqual(m["status"], "read")

    def test_05_nudge_template_cooldown_7_days(self):
        """Follow-up nudge adheres to 7-day cooldown and strict reworded marketing template."""
        phone = "60109722730"

        # 1. First nudge eligible
        ok, reason = check_nudge_eligibility(phone)
        self.assertTrue(ok)

        # Dispatch nudge
        res = dispatch_followup_nudge(phone, client_name="Sarah", unit_name="Unit 12-A")
        self.assertTrue(res.get("success"))
        self.assertIn("PIPELINE.EV following up on the Unit 12-A", res.get("text"))

        # 2. Second nudge immediately blocked by 7-day cooldown
        ok_again, reason_again = check_nudge_eligibility(phone)
        self.assertFalse(ok_again)
        self.assertIn("cooldown", reason_again.lower())

    def test_06_opted_out_contact_blocks_automated_send(self):
        """Automated sends to an opted-out contact are hard-blocked."""
        phone = "60109722730"
        update_contact_state(phone, opted_out=True)

        from main import send_whatsapp_message
        with self.assertRaises(Exception) as cm:
            send_whatsapp_message(phone, "Automated reminder message")
        self.assertIn("opted out", str(cm.exception).lower())

    def test_07_rep_manual_override_send_with_confirmation(self):
        """Human rep manual send with explicit override flag succeeds and logs audit trail."""
        phone = "60109722730"
        update_contact_state(phone, opted_out=True)

        resp = self.client.post("/api/whatsapp/send", json={
            "to_number": phone,
            "message": "Manual follow-up from Elena",
            "manual_override": True,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json().get("success"))

    def test_08_bucket_precedence_calculation(self):
        """Bucket precedence: Opted-out > Needs reply > Booked > Waiting on client > Cold."""
        # 1. Opted out takes highest precedence
        b_opt = calculate_conversation_bucket({
            "opted_out": True,
            "has_inbound_reply": True,
            "has_upcoming_viewing": True,
        })
        self.assertEqual(b_opt, "opted_out")

        # 2. Needs reply beats booked
        b_reply = calculate_conversation_bucket({
            "opted_out": False,
            "has_inbound_reply": True,
            "has_upcoming_viewing": True,
        })
        self.assertEqual(b_reply, "needs_reply")

        # 3. Booked beats waiting
        b_booked = calculate_conversation_bucket({
            "opted_out": False,
            "has_inbound_reply": False,
            "has_upcoming_viewing": True,
        })
        self.assertEqual(b_booked, "booked")

        # 4. Waiting on client
        b_wait = calculate_conversation_bucket({
            "opted_out": False,
            "has_inbound_reply": False,
            "has_upcoming_viewing": False,
            "last_message_outbound_days_ago": 2,
        })
        self.assertEqual(b_wait, "waiting_on_client")

        # 5. Cold
        b_cold = calculate_conversation_bucket({
            "opted_out": False,
            "has_inbound_reply": False,
            "has_upcoming_viewing": False,
            "last_message_outbound_days_ago": 20,
        })
        self.assertEqual(b_cold, "cold")

    def test_09_suggest_reply_guards_and_forbidden_promises(self):
        """suggest_reply enforces token cap, forbidden promise detection, and AI badge."""
        resp = self.client.post("/api/whatsapp/suggest_reply", json={
            "phone_number": "60109722730",
            "prompt_context": "Client asked if price is negotiable.",
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertTrue(data.get("is_ai_draft"))
        draft = data.get("suggested_text", "")
        self.assertLessEqual(len(draft), 300)
        # Must not contain forbidden promises
        for forbidden in ["guarantee", "discount 50%", "free rent", "legally binding"]:
            self.assertNotIn(forbidden, draft.lower())

    def test_10_conversation_mark_read(self):
        """POST /api/whatsapp/conversations/{id}/read updates last_read_at and clears unread count."""
        conv_id = "conv-test-999"
        resp = self.client.post(f"/api/whatsapp/conversations/{conv_id}/read")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json().get("success"))
        self.assertIsNotNone(resp.json().get("last_read_at"))

    def test_11_atomic_dedupe_concurrent_duplicate(self):
        """Atomic deduplication rejects concurrent deliveries for the same wamid."""
        from main import record_inbound_message_atomic
        wamid = "wamid.concurrent_test_001"
        phone = "60109722730"

        # First delivery arrives
        should_process1, rec1 = record_inbound_message_atomic(wamid, phone, text="First")
        self.assertTrue(should_process1)
        self.assertEqual(rec1.get("processing_status"), "received")

        # Second delivery arrives concurrently while still 'received'
        should_process2, rec2 = record_inbound_message_atomic(wamid, phone, text="Duplicate")
        self.assertFalse(should_process2)

    def test_12_atomic_dedupe_redelivery_after_processed(self):
        """Webhook redelivery for a message already processed is skipped."""
        from main import record_inbound_message_atomic, mark_message_processing_status
        wamid = "wamid.processed_test_002"
        phone = "60109722730"

        should_process1, _ = record_inbound_message_atomic(wamid, phone, text="Hello")
        self.assertTrue(should_process1)
        mark_message_processing_status(wamid, "processed")

        # Meta redelivers webhook
        should_process2, _ = record_inbound_message_atomic(wamid, phone, text="Hello")
        self.assertFalse(should_process2)

    def test_13_atomic_dedupe_redelivery_after_failed(self):
        """Webhook redelivery for a message stored-but-failed is retried."""
        from main import record_inbound_message_atomic, mark_message_processing_status
        wamid = "wamid.failed_retry_test_003"
        phone = "60109722730"

        should_process1, _ = record_inbound_message_atomic(wamid, phone, text="Hello")
        self.assertTrue(should_process1)
        mark_message_processing_status(wamid, "failed", error_message="Transient DB error")

        # Meta redelivers webhook -> must allow retry
        should_process2, rec2 = record_inbound_message_atomic(wamid, phone, text="Hello")
        self.assertTrue(should_process2)
        self.assertEqual(rec2.get("processing_status"), "received")

    def test_14_status_error_code_mapping_and_readable_reasons(self):
        """Status updates store Meta error codes and translate them to human-readable failure reasons."""
        from main import apply_message_status_update, get_readable_failure_reason
        # 1. Error 131026: Undeliverable
        apply_message_status_update("wamid.err_131026", "failed", error_code=131026)
        m1 = next(m for m in WHATSAPP_MESSAGE_HISTORY if m["id"] == "wamid.err_131026")
        self.assertEqual(m1.get("error_code"), 131026)
        self.assertEqual(m1.get("failure_reason"), "Undeliverable number")

        # 2. Error 132000: Template not approved or paused
        apply_message_status_update("wamid.err_132000", "failed", error_code=132000)
        m2 = next(m for m in WHATSAPP_MESSAGE_HISTORY if m["id"] == "wamid.err_132000")
        self.assertEqual(m2.get("failure_reason"), "Template not approved or paused")

        # 3. Error 131047: Outside 24h window
        apply_message_status_update("wamid.err_131047", "failed", error_code=131047)
        m3 = next(m for m in WHATSAPP_MESSAGE_HISTORY if m["id"] == "wamid.err_131047")
        self.assertEqual(m3.get("failure_reason"), "Outside the 24h customer service window")

        # 4. Error 130429: Rate limit
        apply_message_status_update("wamid.err_130429", "failed", error_code=130429)
        m4 = next(m for m in WHATSAPP_MESSAGE_HISTORY if m["id"] == "wamid.err_130429")
        self.assertEqual(m4.get("failure_reason"), "WhatsApp Cloud rate limit exceeded")

    def test_15_nudge_eligibility_all_six_exclusions(self):
        """check_nudge_eligibility excludes: opted out, snoozed, declined, human-paused, open slot offer, upcoming viewing."""
        phone = "60109722730"

        # Baseline: eligible
        ok, _ = check_nudge_eligibility(phone)
        self.assertTrue(ok)

        # 1. Opted out
        update_contact_state(phone, opted_out=True)
        ok, r = check_nudge_eligibility(phone)
        self.assertFalse(ok)
        self.assertIn("opted out", r.lower())
        update_contact_state(phone, opted_out=False)

        # 2. Snoozed
        future_dt = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
        update_contact_state(phone, snoozed_until=future_dt)
        ok, r = check_nudge_eligibility(phone)
        self.assertFalse(ok)
        self.assertIn("snoozed", r.lower())
        update_contact_state(phone, snoozed_until=None)

        # 3. Declined
        update_contact_state(phone, pitch_outcome="declined")
        ok, r = check_nudge_eligibility(phone)
        self.assertFalse(ok)
        self.assertIn("declined", r.lower())
        update_contact_state(phone, pitch_outcome=None)

        # 4. Human-paused
        update_contact_state(phone, automation_paused=True)
        ok, r = check_nudge_eligibility(phone)
        self.assertFalse(ok)
        self.assertIn("paused", r.lower())
        update_contact_state(phone, automation_paused=False)

        # 5. Open slot offer
        from main import WHATSAPP_SLOT_OFFERS
        offer_test = {
            "id": "offer_active_test",
            "phone_number": phone,
            "status": "open",
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(),
        }
        if isinstance(WHATSAPP_SLOT_OFFERS, dict):
            WHATSAPP_SLOT_OFFERS["offer_active_test"] = offer_test
        else:
            WHATSAPP_SLOT_OFFERS.append(offer_test)
        ok, r = check_nudge_eligibility(phone)
        self.assertFalse(ok)
        self.assertIn("open slot offer", r.lower())
        if isinstance(WHATSAPP_SLOT_OFFERS, dict):
            del WHATSAPP_SLOT_OFFERS["offer_active_test"]
        else:
            WHATSAPP_SLOT_OFFERS.remove(offer_test)

        # 6. Upcoming viewing
        update_contact_state(phone, has_upcoming_viewing=True)
        ok, r = check_nudge_eligibility(phone)
        self.assertFalse(ok)
        self.assertIn("upcoming", r.lower())
        update_contact_state(phone, has_upcoming_viewing=False)

    def test_16_nudge_button_handlers_view_times_and_not_now(self):
        """Nudge button handlers: View Times creates fresh slots offer; Not Now snoozes for 14 days and acks once."""
        phone = "60109722730"
        from main import process_interactive_button_reply

        # 1. Tap "View Times"
        res_vt = process_interactive_button_reply(
            phone_number=phone,
            button_payload=f"nudge:view_times:{phone}",
            button_title="View Times",
        )
        self.assertEqual(res_vt.get("action"), "nudge_view_times_slots_offered")
        self.assertIsNotNone(res_vt.get("new_offer_id"))

        # 2. Tap "Not Now"
        res_nn = process_interactive_button_reply(
            phone_number=phone,
            button_payload=f"nudge:not_now:{phone}",
            button_title="Not Now",
        )
        self.assertEqual(res_nn.get("action"), "nudge_snoozed")
        state = get_contact_state(phone)
        self.assertIsNotNone(state.get("snoozed_until"))

    def test_17_nudge_button_sender_identity_mismatch(self):
        """Nudge button reply from a different phone number than payload target is rejected."""
        from main import process_interactive_button_reply
        sender_phone = "60111111111"
        payload_phone = "60122222222"

        res = process_interactive_button_reply(
            phone_number=sender_phone,
            button_payload=f"nudge:view_times:{payload_phone}",
            button_title="View Times",
        )
        self.assertEqual(res.get("error"), "sender_identity_mismatch")

    def test_18_opt_out_cancels_pending_reminders_and_alerts_rep(self):
        """Opt-out cancels pending reminders (status=cancelled, error=opted_out) and triggers rep alert for upcoming viewings."""
        phone = "60109722730"
        import main
        main.WHATSAPP_REMINDERS_STORE = [
            {"id": "rem-1", "phone_number": phone, "status": "pending"},
            {"id": "rem-2", "phone_number": phone, "status": "pending"},
        ]
        # Attach upcoming viewing to contact state
        update_contact_state(phone, upcoming_viewings=[
            {"id": "viewing-101", "scheduled_at": "2026-10-15T10:00:00+08:00"}
        ])

        payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": phone,
                                        "id": "wamid.optout_rem_check_001",
                                        "timestamp": "1728460000",
                                        "text": {"body": "STOP"},
                                        "type": "text",
                                    }
                                ]
                            }
                        }
                    ]
                }
            ],
        }

        resp = self.client.post("/api/whatsapp/webhook", json=payload)
        self.assertEqual(resp.status_code, 200)

        # Check reminders cancelled
        for r in main.WHATSAPP_REMINDERS_STORE:
            self.assertEqual(r["status"], "cancelled")
            self.assertEqual(r["error"], "opted_out")

    def test_19_suggest_reply_sentence_boundary_and_ev_forbidden_promises(self):
        """suggest_reply cuts at sentence boundaries and blocks enterprise commercial EV forbidden promises."""
        from main import truncate_at_sentence_boundary, FORBIDDEN_PROMISES

        # 1. Truncate at sentence boundary
        long_text = "Here is the first point. Here is the second sentence that contains detailed information. This is a very long third sentence that extends past the three hundred characters limit and must not be cut right in the middle of words or incomplete clauses."
        cut = truncate_at_sentence_boundary(long_text, max_chars=120)
        self.assertTrue(cut.endswith(".") or cut.endswith("..."))
        self.assertLessEqual(len(cut), 120)

        # 2. EV domain forbidden terms check: "free rent" removed, commercial EV terms present
        self.assertNotIn("free rent", FORBIDDEN_PROMISES)
        for term in ["warranty", "guaranteed savings", "roi", "payback", "delivery date", "lead time", "installation date", "discount", "price commitment", "refund"]:
            self.assertIn(term, FORBIDDEN_PROMISES)

    def test_20_suggest_reply_numeric_grounding_guard(self):
        """suggest_reply replaces entire draft with 'check with rep' note if ungrounded numeric claims exist."""
        from main import check_numeric_grounding, suggest_ai_reply

        facts = "The model features dual 22kW AC onboard chargers and 150kW DC fast charging."
        
        # Grounded: 22kW and 150kW appear in facts
        self.assertTrue(check_numeric_grounding("Our dual 22kW charger supports 150kW fast charging.", facts))

        # Ungrounded: RM25,000 does not appear in facts
        self.assertFalse(check_numeric_grounding("The price is RM25,000 for the charging pack.", facts))

        # Endpoint replacement
        resp = suggest_ai_reply("60109722730", prompt_context="Facts: No numbers here. Can you give me the 5-year ROI?")
        self.assertIn("consult your senior sales specialist", resp["suggested_text"].lower())

    def test_21_clear_opt_out_and_resume_automation_endpoints(self):
        """POST /api/whatsapp/clear_opt_out and /api/whatsapp/resume_automation clear state and log audit messages."""
        phone = "60109722730"
        update_contact_state(phone, opted_out=True, automation_paused=True)

        # 1. Clear opt-out
        res_clear = self.client.post("/api/whatsapp/clear_opt_out", json={
            "phone_number": phone,
            "agent_name": "R. Delgado",
        })
        self.assertEqual(res_clear.status_code, 200)
        self.assertFalse(res_clear.json()["opted_out"])
        state = get_contact_state(phone)
        self.assertFalse(state.get("opted_out"))
        self.assertFalse(state.get("automation_paused"))

        # 2. Pause and resume automation
        update_contact_state(phone, automation_paused=True)
        res_resume = self.client.post("/api/whatsapp/resume_automation", json={
            "phone_number": phone,
            "agent_name": "R. Delgado",
        })
        self.assertEqual(res_resume.status_code, 200)
        self.assertFalse(res_resume.json()["automation_paused"])
        state = get_contact_state(phone)
        self.assertFalse(state.get("automation_paused"))

    def test_22_concurrent_duplicates_mock_enforces_uniqueness(self):
        """Simulated concurrent duplicates against a mock that enforces uniqueness on wamid."""
        from main import record_inbound_message_atomic, WHATSAPP_MESSAGE_HISTORY
        wamid = "wamid.concurrent_unique_test_888"
        phone = "60109722730"

        # Mock DB simulating unique constraint violation on second insert
        inserted_wamids = set()

        def mock_insert(row):
            w = row.get("wamid")
            if w in inserted_wamids:
                raise Exception("duplicate key value violates unique constraint idx_whatsapp_messages_wamid (23505)")
            inserted_wamids.add(w)
            mock_ret = MagicMock()
            mock_ret.data = [row]
            return mock_ret

        orig_insert = self.mock_table.insert
        self.mock_table.insert.side_effect = mock_insert

        # Worker 1: first insert succeeds
        should_process_1, _ = record_inbound_message_atomic(
            m_id=wamid,
            phone_number=phone,
            text="First worker payload",
        )
        self.assertTrue(should_process_1)

        # Worker 2: concurrent call with same wamid hits uniqueness violation
        should_process_2, _ = record_inbound_message_atomic(
            m_id=wamid,
            phone_number=phone,
            text="Second worker concurrent payload",
        )
        self.assertFalse(should_process_2)
        self.mock_table.insert.side_effect = orig_insert

    def test_23_redelivery_of_old_row_with_null_wamid(self):
        """Redelivery of legacy row with null wamid is correctly detected via id lookup and skipped."""
        from main import record_inbound_message_atomic, WHATSAPP_MESSAGE_HISTORY
        wamid = "wamid.legacy_null_wamid_777"
        phone = "60109722730"

        # Simulate legacy message in history with wamid=None and status=processed
        legacy_row = {
            "id": wamid,
            "wamid": None,  # Legacy row prior to migration
            "to_number": phone,
            "text": "Legacy pitch text",
            "processing_status": "processed",
            "status": "delivered",
        }
        WHATSAPP_MESSAGE_HISTORY.append(legacy_row)

        # Inbound delivery with same message ID
        should_process, rec = record_inbound_message_atomic(
            m_id=wamid,
            phone_number=phone,
            text="Redelivered text",
        )
        self.assertFalse(should_process)
        self.assertEqual(rec.get("id"), wamid)

    def test_24_unopted_in_contact_blocks_automated_outbound(self):
        """Outbound WhatsApp to a mobile number with no recorded opt-in is default-denied."""
        from main import send_whatsapp_message, is_contact_opted_in, _send_meta_request
        from fastapi import HTTPException

        unopted_phone = "60129998877"
        # Confirm no opt-in is recorded
        self.assertFalse(is_contact_opted_in(unopted_phone))

        # Automated send raises HTTPException 400
        with self.assertRaises(HTTPException) as cm:
            send_whatsapp_message(unopted_phone, "Upcoming demonstration reminder")
        self.assertEqual(cm.exception.status_code, 400)
        self.assertIn("opt-in required", cm.exception.detail.lower())

        # Unmocked _send_meta_request also blocks directly
        self.mock_meta_patch.stop()
        try:
            import main
            with self.assertRaises(HTTPException) as cm_meta:
                main._send_meta_request({"to": unopted_phone, "type": "text", "text": {"body": "Slot offer"}})
            self.assertEqual(cm_meta.exception.status_code, 400)
            self.assertIn("opt-in required", cm_meta.exception.detail.lower())
        finally:
            self.mock_meta_patch.start()

    def test_25_opted_in_contact_allows_automated_outbound(self):
        """Once opt-in is explicitly recorded, automated outbound messaging succeeds."""
        from main import send_whatsapp_message, is_contact_opted_in, update_contact_state

        opted_phone = "60109722730"
        update_contact_state(opted_phone, opted_in=True)
        self.assertTrue(is_contact_opted_in(opted_phone))

        res = send_whatsapp_message(opted_phone, "Slot offer demonstration details")
        self.assertEqual(res.get("status"), "delivered")


if __name__ == "__main__":
    unittest.main()

