"""
test_part2_reminders.py - Tests for WhatsApp Reminders & Interactive Chat Flow (Part 2)

Covers:
1. Schedule calculation & skip rules (<26h skips 24h; <3h skips 2h)
2. Quiet hours shifting (21:00 - 08:00 MYT -> nearest allowed time before viewing)
3. Viewing creation from each source triggers reminders
4. Cancellation of pending reminders on viewing cancel/reschedule/complete/auto-miss
5. Worker atomic claim & double-claim prevention
6. 24h customer-service window selection (viewing_reminder UTILITY template vs interactive buttons)
7. Deterministic reminder button handlers (confirm, reschedule, cancel)
8. Sender identity check on reminder button replies
9. Automation paused / human-handled suppression of button reminders
10. Single source of truth template consistency
"""

import os
import sys
import uuid
import pytest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from unittest.mock import patch, MagicMock

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Enable in-memory store for unit tests
os.environ["WHATSAPP_USE_MEMORY_STORE"] = "true"

from main import (
    KL_TZ,
    REMINDER_TEMPLATE_CONFIG,
    render_viewing_reminder_text,
    calculate_viewing_reminder_schedules,
    schedule_viewing_reminders,
    cancel_viewing_reminders,
    recompute_viewing_reminders,
    process_due_whatsapp_reminders,
    process_interactive_button_reply,
    WHATSAPP_REMINDERS_STORE,
    set_automation_paused_for_phone,
    is_automation_paused_for_phone,
)


@pytest.fixture(autouse=True)
def clean_test_state():
    WHATSAPP_REMINDERS_STORE.clear()
    set_automation_paused_for_phone("60123456789", False)
    set_automation_paused_for_phone("60199999999", False)
    yield
    WHATSAPP_REMINDERS_STORE.clear()


class TestPart2Reminders:

    def test_01_template_config_consistency(self):
        """
        Confirms REMINDER_TEMPLATE_CONFIG matches Meta specifications:
        UTILITY category, exact variables {{1}}, {{2}}, {{3}}, inline, no line breaks.
        """
        assert REMINDER_TEMPLATE_CONFIG["name"] == "viewing_reminder"
        assert REMINDER_TEMPLATE_CONFIG["category"] == "UTILITY"
        body = REMINDER_TEMPLATE_CONFIG["body"]
        assert "\n" not in body, "Template body must be inline with no line breaks"
        assert "{{1}}" in body
        assert "{{2}}" in body
        assert "{{3}}" in body
        assert "{{4}}" not in body, "Must have exactly 3 variables"

        # Check variable order
        vars_list = REMINDER_TEMPLATE_CONFIG["variables"]
        assert len(vars_list) == 3
        assert vars_list[0]["name"] == "client_name"
        assert vars_list[1]["name"] == "unit_name"
        assert vars_list[2]["name"] == "datetime"

        # Check buttons
        buttons = REMINDER_TEMPLATE_CONFIG["buttons"]
        assert len(buttons) == 3
        labels = [b["label"] for b in buttons]
        assert labels == ["Confirm", "Reschedule", "Cancel"]

        rendered = render_viewing_reminder_text("Sarah Jenkins", "Unit 12-A", "Thu 10 Oct, 2:00 PM")
        assert "Sarah Jenkins" in rendered
        assert "Unit 12-A" in rendered
        assert "Thu 10 Oct, 2:00 PM" in rendered
        assert "\n" not in rendered

    def test_02_schedule_creation_both_reminders(self):
        """
        A viewing scheduled 48 hours away should create both T-24h and T-2h reminders.
        """
        now = datetime(2026, 10, 10, 10, 0, 0, tzinfo=KL_TZ)
        viewing_dt = now + timedelta(hours=48)  # 2 days away at 10:00 AM

        schedules = calculate_viewing_reminder_schedules(viewing_dt, now_dt=now)
        assert len(schedules) == 2
        types = [s["reminder_type"] for s in schedules]
        assert "24h" in types
        assert "2h" in types

        # 24h reminder should be at 10:00 AM on Oct 11
        r24 = next(s for s in schedules if s["reminder_type"] == "24h")
        dt_24 = datetime.fromisoformat(r24["scheduled_send_time"])
        assert dt_24 == viewing_dt - timedelta(hours=24)

        # 2h reminder should be at 08:00 AM on Oct 12
        r2 = next(s for s in schedules if s["reminder_type"] == "2h")
        dt_2 = datetime.fromisoformat(r2["scheduled_send_time"])
        assert dt_2 == viewing_dt - timedelta(hours=2)

    def test_03_skip_rules(self):
        """
        Skip rules:
        - No T-24h reminder if viewing is < 26 hours away.
        - No T-2h reminder if viewing is < 3 hours away.
        """
        now = datetime(2026, 10, 10, 10, 0, 0, tzinfo=KL_TZ)

        # Case A: Viewing 25 hours away (< 26h) -> skips 24h, keeps 2h
        viewing_25h = now + timedelta(hours=25)
        sched_25h = calculate_viewing_reminder_schedules(viewing_25h, now_dt=now)
        assert len(sched_25h) == 1
        assert sched_25h[0]["reminder_type"] == "2h"

        # Case B: Viewing 2.5 hours away (< 3h) -> skips both
        viewing_2_5h = now + timedelta(hours=2, minutes=30)
        sched_2_5h = calculate_viewing_reminder_schedules(viewing_2_5h, now_dt=now)
        assert len(sched_2_5h) == 0

    def test_04_quiet_hours_morning_shift(self):
        """
        Viewing is at 09:30 AM MYT.
        T-2h is 07:30 AM MYT (quiet hours, hour < 8).
        Nearest allowed time before viewing is 08:00 AM MYT (1.5h before demo).
        Should shift to 08:00 AM.
        """
        now = datetime(2026, 10, 10, 14, 0, 0, tzinfo=KL_TZ)
        viewing_dt = datetime(2026, 10, 12, 9, 30, 0, tzinfo=KL_TZ)

        schedules = calculate_viewing_reminder_schedules(viewing_dt, now_dt=now)
        r2 = next((s for s in schedules if s["reminder_type"] == "2h"), None)
        assert r2 is not None

        dt_2 = datetime.fromisoformat(r2["scheduled_send_time"])
        assert dt_2.hour == 8
        assert dt_2.minute == 0
        assert dt_2.day == 12

    def test_05_quiet_hours_evening_shift(self):
        """
        Viewing scheduled at 23:30 MYT (late demo).
        T-2h is 21:30 MYT (quiet hours, hour >= 21).
        Nearest allowed time is 20:45 MYT of the same day.
        Should shift to 20:45 MYT.
        """
        now = datetime(2026, 10, 10, 12, 0, 0, tzinfo=KL_TZ)
        viewing_dt = datetime(2026, 10, 11, 23, 30, 0, tzinfo=KL_TZ)

        schedules = calculate_viewing_reminder_schedules(viewing_dt, now_dt=now)
        r2 = next((s for s in schedules if s["reminder_type"] == "2h"), None)
        assert r2 is not None

        dt_2 = datetime.fromisoformat(r2["scheduled_send_time"])
        assert dt_2.hour == 20
        assert dt_2.minute == 45

    def test_06_cancellation_when_viewing_changes(self):
        """
        Tests that cancel_viewing_reminders marks pending reminders as cancelled.
        """
        v_id = str(uuid.uuid4())
        created = schedule_viewing_reminders(v_id)
        assert len(created) > 0
        assert all(r["status"] == "pending" for r in WHATSAPP_REMINDERS_STORE if r["viewing_id"] == v_id)

        # Cancel viewing reminders
        cancelled_count = cancel_viewing_reminders(v_id, reason="client_cancelled")
        assert cancelled_count > 0
        assert all(r["status"] == "cancelled" for r in WHATSAPP_REMINDERS_STORE if r["viewing_id"] == v_id)

    def test_07_recompute_viewing_reminders(self):
        """
        Tests that recomputing reminders cancels previous pending ones and schedules fresh ones.
        """
        v_id = str(uuid.uuid4())
        created_initial = schedule_viewing_reminders(v_id)
        assert len(created_initial) > 0

        fresh = recompute_viewing_reminders(v_id)
        assert len(fresh) > 0
        # Check that old ones are cancelled and fresh ones are pending
        statuses = [r["status"] for r in WHATSAPP_REMINDERS_STORE if r["viewing_id"] == v_id]
        assert "cancelled" in statuses
        assert "pending" in statuses

    def test_08_worker_atomic_claim_and_double_claim_prevention(self):
        """
        Tests that process_due_whatsapp_reminders only claims pending due reminders,
        marks them sent, and does not re-process them on a subsequent tick.
        """
        v_id = str(uuid.uuid4())
        # Insert a due reminder into the store
        due_row = {
            "id": str(uuid.uuid4()),
            "viewing_id": v_id,
            "client_id": "c-1",
            "agent_id": "a-1",
            "phone_number": "60123456789",
            "reminder_type": "2h",
            "scheduled_send_time": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        WHATSAPP_REMINDERS_STORE.append(due_row)

        with patch("main.is_within_24h_window", return_value=True), \
             patch("main.send_whatsapp_interactive_buttons") as mock_send:
            mock_send.return_value = {"messages": [{"id": "wamid.due_123"}]}

            # First worker tick
            dispatched = process_due_whatsapp_reminders(limit=10)
            assert len(dispatched) == 1
            assert dispatched[0]["status"] == "sent"
            assert dispatched[0]["wamid"] == "wamid.due_123"

            # Check store state
            assert due_row["status"] == "sent"

            # Second worker tick: should NOT process the same reminder again
            dispatched_second = process_due_whatsapp_reminders(limit=10)
            assert len(dispatched_second) == 0

    def test_09_24h_window_template_vs_interactive_buttons(self):
        """
        Verifies that outside the 24h customer-service window, the worker sends
        the viewing_reminder UTILITY template with quick replies.
        Inside the window, it sends interactive buttons.
        """
        # Case A: Inside 24h window
        v_id_inside = str(uuid.uuid4())
        row_inside = {
            "id": str(uuid.uuid4()),
            "viewing_id": v_id_inside,
            "phone_number": "60123456789",
            "reminder_type": "24h",
            "scheduled_send_time": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
            "status": "pending",
        }
        WHATSAPP_REMINDERS_STORE.append(row_inside)

        with patch("main.is_within_24h_window", return_value=True), \
             patch("main.send_whatsapp_interactive_buttons") as mock_interactive, \
             patch("main.send_whatsapp_template_with_quick_replies") as mock_template:
            mock_interactive.return_value = {"messages": [{"id": "wamid.int_1"}]}

            process_due_whatsapp_reminders()
            assert mock_interactive.called
            assert not mock_template.called
            # Check button payloads
            _, kwargs = mock_interactive.call_args
            btn_ids = [b["id"] for b in kwargs["buttons"]]
            assert f"reminder:{v_id_inside}:confirm" in btn_ids
            assert f"reminder:{v_id_inside}:reschedule" in btn_ids
            assert f"reminder:{v_id_inside}:cancel" in btn_ids

        # Case B: Outside 24h window
        v_id_outside = str(uuid.uuid4())
        row_outside = {
            "id": str(uuid.uuid4()),
            "viewing_id": v_id_outside,
            "phone_number": "60123456789",
            "reminder_type": "24h",
            "scheduled_send_time": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
            "status": "pending",
        }
        WHATSAPP_REMINDERS_STORE.append(row_outside)

        with patch("main.is_within_24h_window", return_value=False), \
             patch("main.send_whatsapp_interactive_buttons") as mock_interactive, \
             patch("main.send_whatsapp_template_with_quick_replies") as mock_template:
            mock_template.return_value = {"messages": [{"id": "wamid.tmpl_1"}]}

            process_due_whatsapp_reminders()
            assert mock_template.called
            _, kwargs = mock_template.call_args
            assert kwargs["template_name"] == "viewing_reminder"
            assert kwargs["button_payloads"] == [
                f"reminder:{v_id_outside}:confirm",
                f"reminder:{v_id_outside}:reschedule",
                f"reminder:{v_id_outside}:cancel",
            ]

    def test_10_button_handler_confirm(self):
        """
        Tests deterministic button reply 'reminder:{viewing_id}:confirm':
        Marks viewing confirmed, notifies sales rep, sends confirmation message.
        """
        v_id = str(uuid.uuid4())
        with patch("main.send_whatsapp_message") as mock_send:
            res = process_interactive_button_reply(
                phone_number="60123456789",
                button_payload=f"reminder:{v_id}:confirm",
                client_id="c-test-1",
            )
            assert res.get("action") == "reminder_confirmed"
            assert res.get("viewing_id") == v_id
            assert mock_send.called
            sent_msg = mock_send.call_args[0][1]
            assert "confirmed" in sent_msg.lower()

    def test_11_button_handler_reschedule(self):
        """
        Tests deterministic button reply 'reminder:{viewing_id}:reschedule':
        Cancels pending reminders for this viewing, generates 3 candidate slots,
        and sends fresh slot options to client.
        """
        v_id = str(uuid.uuid4())
        # Schedule a pending reminder
        schedule_viewing_reminders(v_id)

        with patch("main.send_whatsapp_interactive_list") as mock_list:
            res = process_interactive_button_reply(
                phone_number="60123456789",
                button_payload=f"reminder:{v_id}:reschedule",
                client_id="c-test-1",
            )
            assert res.get("action") == "reminder_rescheduled"
            assert res.get("new_offer_id") is not None
            assert mock_list.called
            # Verify pending reminders for the old viewing are cancelled
            old_reminders = [r for r in WHATSAPP_REMINDERS_STORE if r["viewing_id"] == v_id]
            assert all(r["status"] == "cancelled" for r in old_reminders)

    def test_12_button_handler_cancel(self):
        """
        Tests deterministic button reply 'reminder:{viewing_id}:cancel':
        Cancels viewing, cancels pending reminders, and offers to rebook later.
        """
        v_id = str(uuid.uuid4())
        schedule_viewing_reminders(v_id)

        with patch("main.send_whatsapp_message") as mock_send:
            res = process_interactive_button_reply(
                phone_number="60123456789",
                button_payload=f"reminder:{v_id}:cancel",
                client_id="c-test-1",
            )
            assert res.get("action") == "reminder_cancelled"
            assert mock_send.called
            sent_msg = mock_send.call_args[0][1]
            assert "cancelled" in sent_msg.lower()
            # Reminders cancelled
            assert all(r["status"] == "cancelled" for r in WHATSAPP_REMINDERS_STORE if r["viewing_id"] == v_id)

    def test_13_button_handler_wrong_sender_rejection(self):
        """
        Inbound sender phone mismatch check:
        If sender phone does not match the viewing client's registered phone,
        reject with sender_identity_mismatch.
        """
        v_id = str(uuid.uuid4())
        # Mock Supabase returning viewing with client phone 60111111111
        mock_v_res = MagicMock()
        mock_v_res.data = [{
            "id": v_id,
            "status": "upcoming",
            "client_id": "c-orig",
            "clients": {"name": "Original Client", "whatsapp_number": "60111111111"},
            "properties": {"address": "Unit 12-A"},
            "agents": {"name": "R. Delgado"},
        }]

        with patch("main.supabase.table") as mock_table:
            mock_select = MagicMock()
            mock_table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = mock_v_res

            res = process_interactive_button_reply(
                phone_number="60199999999",  # Wrong sender!
                button_payload=f"reminder:{v_id}:confirm",
            )
            assert res.get("error") == "sender_identity_mismatch"

    def test_14_human_handled_automation_paused_suppresses_reminders(self):
        """
        When a conversation has been handed off to human / automation paused,
        the reminder worker must not send button reminders to the client.
        """
        phone = "60123456789"
        set_automation_paused_for_phone(phone, True)
        assert is_automation_paused_for_phone(phone) is True

        v_id = str(uuid.uuid4())
        row = {
            "id": str(uuid.uuid4()),
            "viewing_id": v_id,
            "phone_number": phone,
            "reminder_type": "24h",
            "scheduled_send_time": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
            "status": "pending",
        }
        WHATSAPP_REMINDERS_STORE.append(row)

        with patch("main.send_whatsapp_interactive_buttons") as mock_send:
            dispatched = process_due_whatsapp_reminders()
            assert not mock_send.called
            assert len(dispatched) == 0
            assert row["status"] == "cancelled"
            assert row["error"] == "automation_paused_human_handled"
