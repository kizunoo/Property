# Automated Route & Security Audit Report
Generated from FastAPI and Next.js route introspection. Total routes analyzed: 64.

| Route Path | Method(s) | Reachability | Current Auth | Backend Service | Risk Level | Required Action |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `/api/whatsapp/simulate_incoming` | `POST` | **Browser (via Next.js BFF)** | None (Public Webhook / Simulation) | Meta Cloud API (graph.facebook.com) | **CRITICAL HIGH RISK** | Disable in production; admin-only in development |
| `/api/clients/{client_id}` | `PATCH` | **Direct FastAPI Only** | None | Supabase PostgreSQL | **HIGH RISK** | Require agent authentication |
| `/api/clients/{client_id}/advance_stage` | `POST` | **Direct FastAPI Only** | None | Supabase PostgreSQL | **HIGH RISK** | Require agent authentication |
| `/api/clients/{client_id}/purchases` | `POST` | **Direct FastAPI Only** | None | Supabase PostgreSQL | **HIGH RISK** | Require agent authentication |
| `/api/confirm_demo/{viewing_id}` | `PATCH` | **Direct FastAPI Only** | None (Removed from Portal UI) | Supabase PostgreSQL | **HIGH RISK** | Require agent session or portal session |
| `/api/simulate_market_day` | `POST` | **Browser (via Next.js BFF)** | None | Market Simulation Engine | **HIGH RISK** | Disable in production; admin-only in development |
| `/api/simulate_price_change/{property_id}` | `POST` | **Direct FastAPI Only** | None | Market Simulation Engine | **HIGH RISK** | Disable in production; admin-only in development |
| `/api/whatsapp/nudge` | `POST` | **Browser (via Next.js BFF)** | None | Meta Cloud API (graph.facebook.com) | **HIGH RISK** | Require agent authentication |
| `/api/whatsapp/send_message` | `POST` | **Browser (via Next.js BFF)** | None | Meta Cloud API (graph.facebook.com) | **HIGH RISK** | Require agent authentication |
| `/api/whatsapp/send_pitch` | `POST` | **Browser (via Next.js BFF)** | None | Meta Cloud API (graph.facebook.com) | **HIGH RISK** | Require agent authentication |
| `/` | `GET` | **Direct FastAPI Only** | None (Internal Console Read) | Supabase PostgreSQL | **MEDIUM RISK** | Move behind agent authentication |
| `/api/agents` | `GET` | **Browser (via Next.js BFF)** | None (Internal Console Read) | Supabase PostgreSQL | **MEDIUM RISK** | Move behind agent authentication |
| `/api/calendar/{viewing_id}` | `GET` | **Direct FastAPI Only** | None (Internal Console Read) | Supabase PostgreSQL | **MEDIUM RISK** | Move behind agent authentication |
| `/api/calendar/{viewing_id}.ics` | `GET` | **Direct FastAPI Only** | None (Internal Console Read) | Supabase PostgreSQL | **MEDIUM RISK** | Move behind agent authentication |
| `/api/cancel_viewing/{viewing_id}` | `PATCH` | **Direct FastAPI Only** | None (Internal Console Read) | Supabase PostgreSQL | **MEDIUM RISK** | Move behind agent authentication |
| `/api/clients/{client_id}/purchases` | `GET` | **Direct FastAPI Only** | None (Internal Console Read) | Supabase PostgreSQL | **MEDIUM RISK** | Move behind agent authentication |
| `/api/complete_viewing/{viewing_id}` | `PATCH` | **Direct FastAPI Only** | None (Internal Console Read) | Supabase PostgreSQL | **MEDIUM RISK** | Move behind agent authentication |
| `/api/daily_worklist` | `GET` | **Browser (via Next.js BFF)** | None (Internal Console Read) | Supabase PostgreSQL | **MEDIUM RISK** | Move behind agent authentication |
| `/api/dashboard_briefing` | `GET` | **Browser (via Next.js BFF)** | None (Internal Console Read) | Supabase PostgreSQL | **MEDIUM RISK** | Move behind agent authentication |
| `/api/generate_chart_insight` | `POST` | **Direct FastAPI Only** | None (Internal Console Read) | Supabase PostgreSQL | **MEDIUM RISK** | Move behind agent authentication |
| `/api/generate_insight` | `POST` | **Direct FastAPI Only** | None (Internal Console Read) | Supabase PostgreSQL | **MEDIUM RISK** | Move behind agent authentication |
| `/api/generate_invite` | `POST` | **Direct FastAPI Only** | None (Internal Console Read) | Supabase PostgreSQL | **MEDIUM RISK** | Move behind agent authentication |
| `/api/generate_reasoning` | `POST` | **Direct FastAPI Only** | None (Internal Console Read) | Supabase PostgreSQL | **MEDIUM RISK** | Move behind agent authentication |
| `/api/health` | `GET` | **Direct FastAPI Only** | None (Internal Console Read) | Supabase PostgreSQL | **MEDIUM RISK** | Move behind agent authentication |
| `/api/invite/mark_sent` | `POST` | **Browser (via Next.js BFF)** | None (Internal Console Read) | Supabase PostgreSQL | **MEDIUM RISK** | Move behind agent authentication |
| `/api/log_viewing` | `POST` | **Browser (via Next.js BFF)** | None (Internal Console Read) | Supabase PostgreSQL | **MEDIUM RISK** | Move behind agent authentication |
| `/api/market_movements` | `GET` | **Browser (via Next.js BFF)** | None (Internal Console Read) | Market Simulation Engine | **MEDIUM RISK** | Move behind agent authentication |
| `/api/model_status` | `GET` | **Browser (via Next.js BFF)** | None (Internal Console Read) | ML Engine (scikit-learn) | **MEDIUM RISK** | Move behind agent authentication |
| `/api/pipeline_projection` | `GET` | **Browser (via Next.js BFF)** | None (Internal Console Read) | Supabase PostgreSQL | **MEDIUM RISK** | Move behind agent authentication |
| `/api/prediction_accuracy` | `GET` | **Browser (via Next.js BFF)** | None (Internal Console Read) | Supabase PostgreSQL | **MEDIUM RISK** | Move behind agent authentication |
| `/api/properties/{property_id}` | `PATCH` | **Direct FastAPI Only** | None (Internal Console Read) | Supabase PostgreSQL | **MEDIUM RISK** | Move behind agent authentication |
| `/api/property_price_history/{property_id}` | `GET` | **Direct FastAPI Only** | None (Internal Console Read) | Market Simulation Engine | **MEDIUM RISK** | Move behind agent authentication |
| `/api/record_outcome` | `POST` | **Browser (via Next.js BFF)** | None (Internal Console Read) | Supabase PostgreSQL | **MEDIUM RISK** | Move behind agent authentication |
| `/api/retrain_model` | `POST` | **Browser (via Next.js BFF)** | None (Internal Console Read) | ML Engine (scikit-learn) | **MEDIUM RISK** | Move behind agent authentication |
| `/api/run_evaluations` | `POST` | **Direct FastAPI Only** | None (Internal Console Read) | Supabase PostgreSQL | **MEDIUM RISK** | Move behind agent authentication |
| `/api/schedule_viewing` | `POST` | **Browser (via Next.js BFF)** | None (Internal Console Read) | Supabase PostgreSQL | **MEDIUM RISK** | Move behind agent authentication |
| `/api/scheduled_viewings` | `GET` | **Browser (via Next.js BFF)** | None (Internal Console Read) | Supabase PostgreSQL | **MEDIUM RISK** | Move behind agent authentication |
| `/api/shortlist/{property_id}` | `GET` | **Direct FastAPI Only** | None (Internal Console Read) | Supabase PostgreSQL | **MEDIUM RISK** | Move behind agent authentication |
| `/api/signals` | `GET` | **Browser (via Next.js BFF)** | None (Internal Console Read) | Supabase PostgreSQL | **MEDIUM RISK** | Move behind agent authentication |
| `/api/signals/{signal_id}/dismiss` | `POST` | **Browser (via Next.js BFF)** | None (Internal Console Read) | Supabase PostgreSQL | **MEDIUM RISK** | Move behind agent authentication |
| `/api/whatsapp/clear_opt_out` | `POST` | **Browser (via Next.js BFF)** | None (Internal Console Read) | Meta Cloud API (graph.facebook.com) | **MEDIUM RISK** | Move behind agent authentication |
| `/api/whatsapp/conversations` | `GET` | **Browser (via Next.js BFF)** | None (Internal Console Read) | Meta Cloud API (graph.facebook.com) | **MEDIUM RISK** | Move behind agent authentication |
| `/api/whatsapp/conversations/{conversation_id}/read` | `POST` | **Browser (via Next.js BFF)** | None (Internal Console Read) | Meta Cloud API (graph.facebook.com) | **MEDIUM RISK** | Move behind agent authentication |
| `/api/whatsapp/messages` | `GET` | **Browser (via Next.js BFF)** | None (Internal Console Read) | Meta Cloud API (graph.facebook.com) | **MEDIUM RISK** | Move behind agent authentication |
| `/api/whatsapp/pitch_template` | `GET` | **Direct FastAPI Only** | None (Internal Console Read) | Meta Cloud API (graph.facebook.com) | **MEDIUM RISK** | Move behind agent authentication |
| `/api/whatsapp/process_reminders` | `POST` | **Direct FastAPI Only** | None (Internal Console Read) | Meta Cloud API (graph.facebook.com) | **MEDIUM RISK** | Move behind agent authentication |
| `/api/whatsapp/reminder_template_config` | `GET` | **Direct FastAPI Only** | None (Internal Console Read) | Meta Cloud API (graph.facebook.com) | **MEDIUM RISK** | Move behind agent authentication |
| `/api/whatsapp/resume_automation` | `POST` | **Browser (via Next.js BFF)** | None (Internal Console Read) | Meta Cloud API (graph.facebook.com) | **MEDIUM RISK** | Move behind agent authentication |
| `/api/whatsapp/resume_automation` | `POST` | **Browser (via Next.js BFF)** | None (Internal Console Read) | Meta Cloud API (graph.facebook.com) | **MEDIUM RISK** | Move behind agent authentication |
| `/api/whatsapp/send` | `POST` | **Browser (via Next.js BFF)** | None (Internal Console Read) | Meta Cloud API (graph.facebook.com) | **MEDIUM RISK** | Move behind agent authentication |
| `/api/whatsapp/suggest_reply` | `POST` | **Browser (via Next.js BFF)** | None (Internal Console Read) | Meta Cloud API (graph.facebook.com) | **MEDIUM RISK** | Move behind agent authentication |
| `/api/whatsapp/window_status` | `GET` | **Browser (via Next.js BFF)** | None (Internal Console Read) | Meta Cloud API (graph.facebook.com) | **MEDIUM RISK** | Move behind agent authentication |
| `/api/whatsapp/webhook` | `GET` | **Browser (via Next.js BFF)** | Meta Verify Token / Secret | Meta Cloud API (graph.facebook.com) | **LOW (External Webhook)** | Signature verified |
| `/api/whatsapp/webhook` | `POST` | **Browser (via Next.js BFF)** | Meta Verify Token / Secret | Meta Cloud API (graph.facebook.com) | **LOW (External Webhook)** | Signature verified |
| `/api/portal/login` | `POST` | **Browser (via Next.js BFF)** | Opaque Session Cookie (HMAC) | Portal v2 Auth / PostgreSQL | **SECURE (Authenticated Portal)** | Company-scoped; validated against portal_sessions |
| `/api/portal/{client_id}/activity` | `GET` | **Direct FastAPI Only** | Opaque Session Cookie (HMAC) | Portal v2 Auth / PostgreSQL | **SECURE (Authenticated Portal)** | Company-scoped; validated against portal_sessions |
| `/api/portal/{client_id}/catalog` | `GET` | **Direct FastAPI Only** | Opaque Session Cookie (HMAC) | Portal v2 Auth / PostgreSQL | **SECURE (Authenticated Portal)** | Company-scoped; validated against portal_sessions |
| `/api/portal/{client_id}/dashboard` | `GET` | **Direct FastAPI Only** | Opaque Session Cookie (HMAC) | Portal v2 Auth / PostgreSQL | **SECURE (Authenticated Portal)** | Company-scoped; validated against portal_sessions |
| `/api/portal/{client_id}/inquiries` | `GET` | **Direct FastAPI Only** | Opaque Session Cookie (HMAC) | Portal v2 Auth / PostgreSQL | **SECURE (Authenticated Portal)** | Company-scoped; validated against portal_sessions |
| `/api/portal/{client_id}/inquiry` | `POST` | **Direct FastAPI Only** | Opaque Session Cookie (HMAC) | Portal v2 Auth / PostgreSQL | **SECURE (Authenticated Portal)** | Company-scoped; validated against portal_sessions |
| `/api/portal/{client_id}/my_viewings` | `GET` | **Direct FastAPI Only** | Opaque Session Cookie (HMAC) | Portal v2 Auth / PostgreSQL | **SECURE (Authenticated Portal)** | Company-scoped; validated against portal_sessions |
| `/api/portal/{client_id}/preferences` | `GET` | **Direct FastAPI Only** | Opaque Session Cookie (HMAC) | Portal v2 Auth / PostgreSQL | **SECURE (Authenticated Portal)** | Company-scoped; validated against portal_sessions |
| `/api/portal/{client_id}/preferences` | `PUT` | **Direct FastAPI Only** | Opaque Session Cookie (HMAC) | Portal v2 Auth / PostgreSQL | **SECURE (Authenticated Portal)** | Company-scoped; validated against portal_sessions |
| `/api/portal/{client_id}/request_demo` | `POST` | **Direct FastAPI Only** | Opaque Session Cookie (HMAC) | Portal v2 Auth / PostgreSQL | **SECURE (Authenticated Portal)** | Company-scoped; validated against portal_sessions |
