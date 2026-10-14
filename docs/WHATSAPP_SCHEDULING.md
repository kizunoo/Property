# WhatsApp Scheduling - Developer Guide

> **Scope:** Full WhatsApp scheduling lifecycle covering slot-pitch + auto-booking (Part 1), reminder engine (Part 2), rich messages, unit images, signed calendar links (Part 3), and rep panel, 24h window gating, status bucket progression, opt-out handling, and follow-up nudge (Part 4).

---

## Table of Contents

1. [Feature Overview](#1-feature-overview)
2. [System Architecture](#2-system-architecture)
3. [Flow - Pitch to Pick to Book](#3-flow--pitch-to-pick-to-book)
4. [Flow - Reminders](#4-flow--reminders)
5. [Flow - Follow-Up Nudges and Opt-Outs](#5-flow--follow-up-nudges-and-opt-outs)
6. [Environment Variables](#6-environment-variables)
7. [Dry-Run and Allowlist Settings](#7-dry-run-and-allowlist-settings)
8. [Meta Template Specifications](#8-meta-template-specifications)
9. [Mobile Calendar Links and Cross-Platform Behavior](#9-mobile-calendar-links-and-cross-platform-behavior)
10. [Rep Operations Panel and Safety Guards](#10-rep-operations-panel-and-safety-guards)
11. [Database Schema Summary](#11-database-schema-summary)
12. [Testing with simulate_incoming](#12-testing-with-simulate_incoming)
13. [Manual End-to-End Test Script](#13-manual-end-to-end-test-script)
14. [Known Limitations](#14-known-limitations)
15. [Production Checklist](#15-production-checklist)

---

## 1. Feature Overview

PIPELINE.EV coordinates WhatsApp communication with prospects using the official Meta Cloud API.
The system is divided into four integrated modules:

| Module | Feature | Trigger | What it does |
|---|---|---|---|
| Part 1 | Slot Pitch & Booking | Sales rep clicks "Send Pitch" in agent dashboard | Dispatches 3 proposed demo times via interactive button or template; client tap books atomically. |
| Part 2 | Reminder Engine | APScheduler worker tick (every 1 min) | Sends quiet-hours-aware T-24h and T-2h reminders with inline Confirm / Reschedule / Cancel actions. |
| Part 3 | Rich Messages & Calendar Links | Booking confirmation & pitch dispatch | Delivers unit photos (inside 24h window), Google Calendar direct links, and HMAC-SHA256 signed .ics downloads. |
| Part 4 | Rep Operations Panel & Automation Guards | Rep WhatsApp Panel UI & inbound webhooks | Provides 24h customer window gating, status bucket progression, atomic inbound deduplication, opt-out handling, and 7-day cooldown marketing nudges. |

---

## 2. System Architecture

```
Agent Dashboard & Rep Panel (Next.js)
  ├─ POST /api/whatsapp/send_pitch
  ├─ POST /api/whatsapp/nudge
  ├─ POST /api/whatsapp/suggest_reply
  ├─ POST /api/whatsapp/clear_opt_out
  └─ POST /api/whatsapp/resume_automation
                                  ├──> backend/main.py (FastAPI)
                                         ├── send_whatsapp_template_with_quick_replies()
                                         ├── send_whatsapp_interactive_buttons() / list()
                                         ├── send_whatsapp_image_message()
                                         ├── record_inbound_message_atomic()
                                         └── Supabase Database & Vault

Meta Cloud API  ── webhook ──>  POST /api/whatsapp/webhook (X-Hub-Signature-256)
                                         ├── record_inbound_message_atomic() (received/processed/failed)
                                         ├── Status Updates (sent/delivered/read/failed + error codes)
                                         ├── Strict Opt-Out ("STOP" -> cancel reminders + rep alert)
                                         ├── Button Replies:
                                         │     ├── slot_pick:* -> claim_and_book_slot_offer() RPC
                                         │     ├── reminder:* -> confirm / reschedule / cancel
                                         │     └── nudge:* -> nudge:view_times / nudge:not_now
                                         └── Free-text fallback & AI suggestion engine

APScheduler (every 1 min)
  └── process_due_whatsapp_reminders()
        ├── claim_due_whatsapp_reminders() RPC (atomic, SKIP LOCKED)
        ├── Check automation paused / opted out
        ├── Inside 24h window  ──> send_whatsapp_interactive_buttons()
        └── Outside 24h window ──> send viewing_reminder UTILITY template
```

---

## 3. Flow - Pitch to Pick to Book

1. Agent triggers pitch via dashboard → `POST /api/whatsapp/send_pitch`.
2. Backend:
   - Validates candidate slots (weekday, business hours 09:00–18:00 MYT, 45-min agent buffer).
   - If 24h customer window is open: sends unit image first (if requested), then interactive buttons or list.
   - If 24h customer window is closed: sends `viewing_slots_pitch` MARKETING template.
   - Persists a `whatsapp_slot_offers` row (`status='open'`, `expires_at = now() + 72h`).
3. Client taps an option button in WhatsApp → Meta fires webhook to `/api/whatsapp/webhook`.
4. Backend executes Supabase RPC `claim_and_book_slot_offer(offer_id, slot_index)`:
   - Locks the offer row (`SELECT FOR UPDATE`).
   - Checks validity, expiration, and conflict with +/-45 min buffer.
   - Atomically marks offer `booked` and inserts `scheduled_viewings` row (`source='whatsapp_auto'`).
5. Backend formats booking confirmation with Google Calendar link and HMAC-SHA256 signed `.ics` download link.
6. Quiet-hours-aware reminders scheduled at T-24h and T-2h.

---

## 4. Flow - Reminders

**Scheduling (at booking time):**
- Calculates T-24h (skipped if viewing < 26h away) and T-2h (skipped if viewing < 3h away).
- Shifts send times out of quiet hours (21:00–08:00 MYT) to the latest allowed time before the appointment.

**Sending (APScheduler tick, every 1 min):**
```
claim_due_whatsapp_reminders(limit=10)  <- atomic, SKIP LOCKED
  ├── for each reminder:
        ├── automation paused or opted out? -> cancel, skip
        ├── Inside 24h window -> send_whatsapp_interactive_buttons(Confirm / Reschedule / Cancel) + calendar links
        └── Outside 24h window -> send viewing_reminder UTILITY template
```

**Button reply handlers:**
| Button Payload | Action |
|---|---|
| `reminder:{viewing_id}:confirm` | Marks viewing `confirmation_status='confirmed'`, sends calendar acknowledgment. |
| `reminder:{viewing_id}:reschedule` | Cancels old reminders, generates fresh slots, sends 3 alternative options. |
| `reminder:{viewing_id}:cancel` | Cancels viewing and reminders, offers to rebook when convenient. |

**Sender identity guard:** The inbound sender phone must strictly match the client's registered WhatsApp number. Identity mismatches return `sender_identity_mismatch` and are rejected.

---

## 5. Flow - Follow-Up Nudges and Opt-Outs

### Follow-Up Nudge
- Sales rep clicks "Send Nudge" in the WhatsApp Rep Panel.
- `check_nudge_eligibility` validates that none of the 6 exclusion rules apply:
  1. Client opted out
  2. Client snoozed (`snoozed_until > now`)
  3. Client declined previous offer
  4. Automation paused by rep
  5. Open slot offer already active
  6. Scheduled viewing already upcoming or confirmed
- Enforces strict 7-day cooldown between nudges.
- Dispatches `viewing_followup_nudge` MARKETING template with quick-reply buttons `View Times` and `Not Now`.
- When client taps `View Times`: generates fresh candidate slots and sends an updated offer.
- When client taps `Not Now`: snoozes contact for 14 days and acknowledges once.

### Opt-Out Handling
- Inbound message containing exact opt-out keywords (`stop`, `unsubscribe`, `berhenti`, `jangan hubungi`):
  - Sets `opted_out=True`, `automation_paused=True` in contact state.
  - Cancels all pending reminders (`status='cancelled'`, `error='opted_out'`).
  - Checks for upcoming viewings: if any exist, fires a `whatsapp_opt_out_rep_alert` signal to notify the rep to handle the client manually.
  - Sends immediate unsubscribe confirmation message with resubscribe instructions (`START`).
- Resubscribe (`start`, `mula`, `subscribe`): reactivates automated messaging.
- Sales reps can clear opt-out or resume automation in the Rep Panel with full audit logging.

---

## 6. Environment Variables

| Variable | Required | Description |
|---|---|---|
| `SUPABASE_URL` | Yes | Supabase project URL |
| `SUPABASE_KEY` | Yes | Publishable / anon key (read bounds enforced) |
| `SUPABASE_SERVICE_ROLE_KEY` | Yes | Service-role key for backend writes and RLS bypass |
| `WHATSAPP_PHONE_NUMBER_ID` | Yes | Meta Cloud API phone number ID |
| `WHATSAPP_ACCESS_TOKEN` | Yes | Meta permanent system user access token |
| `WHATSAPP_BUSINESS_ACCOUNT_ID` | Yes | Meta WhatsApp Business Account ID |
| `WHATSAPP_VERIFY_TOKEN` | Yes | Webhook verification token configured in Meta Developer Console |
| `WHATSAPP_APP_SECRET` | Yes | Meta App Secret for validating `X-Hub-Signature-256` HMAC hashes |
| `PUBLIC_BASE_URL` | Yes | Public HTTPS origin used to generate calendar download URLs (e.g. `https://pipeline-ev.com`) |
| `CALENDAR_SIGNING_SECRET` | Yes | High-entropy secret used for HMAC-SHA256 signature tokens on `.ics` calendar download links |
| `TRUST_PROXY_HEADERS` | Optional | Set to `true` when running behind a reverse proxy (e.g. NGINX, Cloudflare) for client IP rate-limiting |
| `WHATSAPP_DRY_RUN` | Optional | Set to `true` to run in simulated mode without making live Meta API calls |
| `WHATSAPP_ALLOWED_TEST_NUMBERS` | Optional | Comma-separated E.164 phone numbers allowed to receive real WhatsApp dispatches |
| `WHATSAPP_TEST_NUMBER` | Optional | Fallback test phone number |
| `ENABLE_WA_SIMULATOR` | Optional | Enables `/api/whatsapp/simulate_incoming` endpoint for testing |
| `ENFORCE_WA_SIGNATURE` | Optional | Rejects webhook payloads with missing or invalid `X-Hub-Signature-256` |
| `WHATSAPP_USE_MEMORY_STORE` | Test only | Instructs backend test suites to use in-memory stores rather than Supabase |

---

## 7. Dry-Run and Allowlist Settings

### Dry-Run Mode (Local Development)
```
WHATSAPP_DRY_RUN=true
```
No outbound HTTP requests are made to Meta. Simulated `wamid.mock_*` IDs are assigned, and operations are logged to the console and in-memory history.

### Allowlist Mode (Staging / Verification)
```
WHATSAPP_DRY_RUN=false
WHATSAPP_ALLOWED_TEST_NUMBERS=60109722730,60123456789
```
Only numbers explicitly listed in `WHATSAPP_ALLOWED_TEST_NUMBERS` will receive real Meta Cloud API requests. Messages to other numbers are safely diverted to log-only simulation.

### Production
```
WHATSAPP_DRY_RUN=false
ENFORCE_WA_SIGNATURE=true
# WHATSAPP_ALLOWED_TEST_NUMBERS is unset
```

---

## 8. Meta Template Specifications

All three templates are submitted in Meta Business Manager and obey quiet hours (21:00–08:00 MYT).

> **Code Confirmation:** The exact template names dispatched by backend code are:
> 1. `viewing_slots_pitch` — called in `send_pitch_via_whatsapp`
> 2. `viewing_reminder` — called in `process_due_whatsapp_reminders`
> 3. `viewing_followup_nudge` — called in `dispatch_followup_nudge`

### 1. `viewing_slots_pitch` (MARKETING)
Used for initial demonstration invitations sent outside the 24-hour customer window.
- **Status:** Pending Meta approval <!-- EDITABLE: Pending Meta approval | Approved | Rejected -->
- **Body:**
  ```
  Hello {{1}}, this is PIPELINE.EV following up on the {{2}}. We would like to invite your team to an on-site demonstration. Proposed times: Option 1: {{3}}, Option 2: {{4}}, Option 3: {{5}}. Tap a button below to choose, or reply with a time that suits you.
  ```
- **Variables:**
  1. `client_name` (e.g. "Sarah Jenkins")
  2. `unit_name` (e.g. "AMR-4000 Heavy-Lift Pallet Jack")
  3. `slot_1` (e.g. "Thu 15 Oct, 10:00 AM")
  4. `slot_2` (e.g. "Thu 15 Oct, 2:00 PM")
  5. `slot_3` (e.g. "Fri 16 Oct, 11:00 AM")
- **Buttons (Quick Reply):** `Option 1` | `Option 2` | `Option 3`

### 2. `viewing_reminder` (UTILITY)
Dispatched for appointment reminders outside the 24-hour customer window.
- **Status:** Pending Meta approval <!-- EDITABLE: Pending Meta approval | Approved | Rejected -->
- **Body:**
  ```
  Hello {{1}}, this is PIPELINE.EV following up on the {{2}}. Your on-site demonstration is confirmed for {{3}}. Please confirm your attendance, or let us know if you need to reschedule.
  ```
- **Variables:**
  1. `client_name` (e.g. "Sarah Jenkins")
  2. `unit_name` (e.g. "AMR-4000 Heavy-Lift Pallet Jack")
  3. `datetime` (e.g. "Thu 15 Oct, 10:00 AM")
- **Buttons (Quick Reply):** `Confirm` | `Reschedule` | `Cancel`

### 3. `viewing_followup_nudge` (MARKETING)
Reworded strictly in accordance with Meta Marketing Template policies to avoid promotional rejection.
- **Status:** Pending Meta approval <!-- EDITABLE: Pending Meta approval | Approved | Rejected -->
- **Body:**
  ```
  Hello {{1}}, we previously shared demonstration times for the {{2}}. Would your team like to review updated availability for this week?
  ```
- **Variables:**
  1. `client_name` (e.g. "Sarah Jenkins")
  2. `unit_name` (e.g. "AMR-4000 Heavy-Lift Pallet Jack")
- **Buttons (Quick Reply):** `View Times` | `Not Now`
- **Rules:** Enforces a 7-day cooldown since last nudge. Sender identity verified on button taps.

---

## 9. Mobile Calendar Links and Cross-Platform Behavior

Booking confirmations and reminder messages provide two calendar links:
1. **Google Calendar Web URL:** Pre-populated link opening directly in the browser or Google Calendar app.
2. **Signed `.ics` Download URL:** `https://<PUBLIC_BASE_URL>/api/calendar/<viewing_id>?token=<hmac_token>`

### Cross-Platform Mobile Verification
> **Note:** Behavior to be verified on a phone across devices:
- **iOS (iPhone / Safari):** Tapping the `.ics` link in WhatsApp opens Safari and prompts the built-in iOS Calendar event import ("Add to Calendar"); Google Calendar link opens the event in the mobile browser or Google Calendar app (to be verified on a phone).
- **Android (Chrome):** Tapping the `.ics` link downloads the file and prompts the device calendar app (Samsung Calendar, Google Calendar, etc.); Google Calendar link opens directly in browser or app (to be verified on a phone).
- **Security & Integrity:**
  - The `.ics` endpoint validates the HMAC-SHA256 signature against `CALENDAR_SIGNING_SECRET`. Tampered parameters return `403 Forbidden`.
  - Links expire after 30 days.
  - Rate limiting protects the endpoint (maximum 30 requests per IP per minute).

---

## 10. Rep Operations Panel and Safety Guards

Located at `components/pipeline/whatsapp-rep-panel.tsx`, the sales representative operations panel provides:

1. **24-Hour Customer Window Gating:**
   - Displays real-time window status and remaining countdown.
   - When the window is **open**: Free-text messaging and AI reply suggestions are enabled.
   - When the window is **closed**: Free-text composer is locked; only pre-approved Meta templates can be initiated.
2. **Status Bucket Progression:**
   - `AWAITING REPLY`: Outbound pitch sent, waiting for client response.
   - `FOLLOW UP NEEDED`: 48 hours without inbound response.
   - `NUDGE ELIGIBLE`: Eligible for reworded marketing nudge after 7 days.
   - `IN PROGRESS`: Client active within 24 hours.
   - `OPTED OUT`: Client sent opt-out keyword; automation blocked.
3. **Atomic Deduplication:**
   - Uses `record_inbound_message_atomic` with `processing_status` states: `received`, `processed`, `failed`.
   - Prevents duplicate webhook deliveries and race conditions. Redeliveries of failed messages trigger retries.
4. **AI Reply Suggestions & Domain Guards:**
   - AI drafts truncate strictly at sentence boundaries (no mid-sentence cutoffs).
   - Domain-specific forbidden terms for EV commercial fleet (e.g. `warranty`, `guaranteed savings`, `ROI`, `contract terms`, `free rent`) are rejected.
   - **Numeric Grounding Guard:** Hallucinated numbers not present in the facts automatically trigger replacement with a note directing the client to consult the sales representative.
5. **Human Controls:**
   - Reps can manually clear opt-out status or resume paused automations with explicit confirmation.
   - All manual overrides generate audit entries in the `signals` table.

---

## 11. Database Schema Summary

| Table | Purpose | Access Control |
|---|---|---|
| `whatsapp_messages` | Full log of outbound and inbound messages with delivery and processing status | service_role only |
| `whatsapp_slot_offers` | Active and historical pitch slot offers | service_role only |
| `whatsapp_reminders` | Scheduled viewing reminder queue | service_role only |
| `scheduled_viewings` | Confirmed bookings (`source='whatsapp_auto'`) | authenticated read, service_role write |
| `signals` | Rep notifications and audit log | authenticated read, service_role write |

> **Important - Adding new clients columns:** Due to column-level `GRANT SELECT` in `security_hardening.sql`, whenever a new column is added to `public.clients` that the frontend dashboard needs to read, it MUST be explicitly added to `GRANT SELECT (..., new_column) ON public.clients TO anon;`. Otherwise, dashboard queries selecting that column will fail or trigger fallbacks.

### Migration Order
Apply migrations in Supabase SQL Editor in the following sequence:
1. `backend/whatsapp_tables_migration.sql`
2. `backend/whatsapp_slot_offers_migration.sql`
3. `backend/whatsapp_reminders_migration.sql`
4. `backend/security_hardening.sql`
5. `backend/whatsapp_part4_migration.sql`

---

## 12. Testing with simulate_incoming

When `ENABLE_WA_SIMULATOR=true`, developers can inject inbound webhook payloads without calling Meta.

### Simulate Button Reply (Slot Booking)
```bash
curl -X POST http://localhost:8000/api/whatsapp/simulate_incoming \
  -H "Content-Type: application/json" \
  -d '{"from_number": "60109722730", "interactive_payload": "slot_pick:<offer_id>:1", "button_title": "Option 1"}'
```

### Simulate Reminder Confirm
```bash
curl -X POST http://localhost:8000/api/whatsapp/simulate_incoming \
  -H "Content-Type: application/json" \
  -d '{"from_number": "60109722730", "interactive_payload": "reminder:<viewing_id>:confirm", "button_title": "Confirm"}'
```

### Simulate Opt-Out
```bash
curl -X POST http://localhost:8000/api/whatsapp/simulate_incoming \
  -H "Content-Type: application/json" \
  -d '{"from_number": "60109722730", "message": "STOP"}'
```

---

## 13. Manual End-to-End Test Script

1. **Setup Allowlist:** Set `WHATSAPP_ALLOWED_TEST_NUMBERS=<your_mobile_number>` and `WHATSAPP_DRY_RUN=false`.
2. **Send Pitch:** In the Agent Dashboard, select a test client and send a pitch. You will receive an interactive WhatsApp message.
3. **Book Slot:** Tap "Option 1". Verify that booking confirmation text with calendar links is received and viewing appears on the Viewings Board.
4. **Calendar Import:** Tap the `.ics` link on your phone; verify native calendar event preview opens. Tap Google Calendar link; verify web event is populated.
5. **Reminder Action:** Wait for reminder (or advance send time). Tap "Confirm" to verify status changes to confirmed.
6. **Opt-Out & Rep Alert:** Reply "STOP". Verify that unsubscribe confirmation is received, pending reminders are cancelled, and a rep signal is generated if viewings exist.
7. **Rep Panel Control:** In the Rep Panel, view the opted-out conversation and click "Clear Opt-Out". Send a message to verify delivery resumes.

---

## 14. Known Limitations

- **3-Button Limit:** Meta interactive buttons support a maximum of 3 quick replies. More than 3 options automatically transition to an interactive list picker.
- **24-Hour Customer Window:** Outside the 24-hour customer window, free-form messages cannot be sent. Only approved Meta templates are permitted.
- **Quiet-Hours Postponement:** Automated dispatches between 21:00 and 08:00 MYT are queued and sent the next morning.
- **Single-Agent Binding:** Each pitch and viewing is bound to one assigned sales representative.

---

## 15. Production Checklist

- [ ] All 3 Meta templates (`viewing_slots_pitch`, `viewing_reminder`, `viewing_followup_nudge`) approved in Meta WhatsApp Manager.
- [ ] `SUPABASE_SERVICE_ROLE_KEY` stored exclusively in backend environment secrets.
- [ ] `PUBLIC_BASE_URL` and `CALENDAR_SIGNING_SECRET` configured in production environment.
- [ ] `WHATSAPP_DRY_RUN=false` and `ENFORCE_WA_SIGNATURE=true`.
- [ ] Migrations applied in required order (including `security_hardening.sql` and `whatsapp_part4_migration.sql`).
- [ ] APScheduler reminder worker active in background.
- [ ] Meta webhook URL verified with `WHATSAPP_VERIFY_TOKEN` and app secret configured.
- [ ] Rep panel tested across desktop and mobile browsers.
