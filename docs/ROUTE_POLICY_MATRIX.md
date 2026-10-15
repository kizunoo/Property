# PIPELINE.EV Logic Engine — Route Security Policy Matrix

> Auto-generated from `backend/main.py:app.routes` by `scripts/generate_route_policy_matrix.py`.
> Every `/api` endpoint is strictly bound to one of five security tiers.

## Policy Definitions
- **`public`**: Unauthenticated public endpoints (e.g., Meta webhooks, health checks, OTP request/verify, signed calendar `.ics`).
- **`portal-session`**: Authenticated via Client Portal v2 session token (`portal_sessions`).
- **`any-agent`**: Authenticated active agent session token (`agent_sessions`). Scoped to agent's assigned clients where applicable.
- **`client-scoped`**: Authenticated active agent session token. Strictly scoped to agent's assigned client (`404 Not Found` for other agents).
- **`admin-only`**: Requires agent session with `role == 'admin'`. Applied to all global mutators, retraining, and system administration.
- **LLM Rate Limited**: Subject to per-agent sliding-window limiter (10 requests / minute) to prevent model exhaustion.

**Total Registered API Endpoints:** 102  
**Undeclared Policies:** 0

| Method | Path | Security Policy | LLM Rate Limit | Purpose / Security Description |
| :--- | :--- | :--- | :---: | :--- |
| `POST` | `/api/admin/agents/{agent_id}/issue-reset` | **`admin-only`** | - | Admin issue password reset code for agent |
| `POST` | `/api/admin/agents/{agent_id}/reactivate` | **`admin-only`** | - | Admin reactivate agent account |
| `POST` | `/api/admin/agents/{agent_id}/revoke-all-sessions` | **`admin-only`** | - | Admin revoke all active agent sessions |
| `POST` | `/api/admin/agents/{agent_id}/suspend` | **`admin-only`** | - | Admin suspend agent account |
| `POST` | `/api/admin/agents/{agent_id}/unlock` | **`admin-only`** | - | Admin unlock agent lockout |
| `GET` | `/api/agents` | **`admin-only`** | - | List all agency accounts and credentials |
| `GET` | `/api/model_status` | **`admin-only`** | - | Current model training status and feature weights |
| `GET` | `/api/prediction_accuracy` | **`admin-only`** | - | Machine learning model performance metrics |
| `PATCH` | `/api/properties/{property_id}` | **`admin-only`** | - | Mutate global property inventory |
| `POST` | `/api/retrain_model` | **`admin-only`** | - | Retrain machine learning model on global outcomes |
| `POST` | `/api/run_evaluations` | **`admin-only`** | - | Global pipeline evaluation recalculation |
| `POST` | `/api/simulate_market_day` | **`admin-only`** | - | Simulate market price shifts across properties |
| `POST` | `/api/simulate_price_change/{property_id}` | **`admin-only`** | - | Simulate price change for specific property |
| `POST` | `/api/whatsapp/process_reminders` | **`admin-only`** | - | Manual trigger for background WhatsApp reminder queue |
| `POST` | `/api/whatsapp/simulate_incoming` | **`admin-only`** | - | Simulate incoming WhatsApp webhook |
| `POST` | `/api/agent/logout` | **`any-agent`** | - | Agent session logout and revocation |
| `GET` | `/api/agent/me` | **`any-agent`** | - | Current agent account identity and permissions |
| `GET` | `/api/console/quotes/pending` | **`any-agent`** | Yes | List pending quote requests for rep |
| `GET` | `/api/daily_worklist` | **`any-agent`** | - | Daily prioritize tasks (scoped to agent) |
| `GET` | `/api/dashboard_briefing` | **`any-agent`** | Yes | Dashboard VIP narrative (LLM, scoped to agent) |
| `GET` | `/api/market_movements` | **`any-agent`** | - | Summary of active market movements across inventory |
| `GET` | `/api/pipeline_projection` | **`any-agent`** | - | Projected pipeline revenue (scoped to agent's assigned clients) |
| `GET` | `/api/property_price_history/{property_id}` | **`any-agent`** | - | Read historical pricing records for property |
| `GET` | `/api/scheduled_viewings` | **`any-agent`** | - | Scheduled viewings list (scoped to agent) |
| `GET` | `/api/shortlist/{property_id}` | **`any-agent`** | - | Shortlist matching clients for property (scoped to agent's clients) |
| `GET` | `/api/signals` | **`any-agent`** | - | Active market/tier signals (scoped to agent) |
| `POST` | `/api/signals/{signal_id}/dismiss` | **`any-agent`** | - | Dismiss market signal |
| `GET` | `/api/whatsapp/conversations` | **`any-agent`** | - | List active conversations (scoped to agent's assigned clients) |
| `GET` | `/api/whatsapp/messages` | **`any-agent`** | - | Read messages stream for active conversation |
| `GET` | `/api/whatsapp/pitch_template` | **`any-agent`** | - | Get preconfigured pitch template text |
| `GET` | `/api/whatsapp/reminder_template_config` | **`any-agent`** | - | Get reminder template config |
| `PATCH` | `/api/cancel_viewing/{viewing_id}` | **`client-scoped`** | - | Cancel scheduled viewing appointment |
| `PATCH` | `/api/clients/{client_id}` | **`client-scoped`** | - | Update client demographic or stage metadata |
| `POST` | `/api/clients/{client_id}/advance_stage` | **`client-scoped`** | - | Advance client relationship stage |
| `GET` | `/api/clients/{client_id}/purchases` | **`client-scoped`** | - | List purchases for assigned client |
| `POST` | `/api/clients/{client_id}/purchases` | **`client-scoped`** | - | Record purchase transaction for assigned client |
| `PATCH` | `/api/complete_viewing/{viewing_id}` | **`client-scoped`** | - | Complete viewing appointment and trigger evaluation |
| `PATCH` | `/api/confirm_demo/{viewing_id}` | **`client-scoped`** | - | Confirm viewing demo request |
| `POST` | `/api/console/clients/{client_id}/inquiries/{inquiry_id}/reply` | **`client-scoped`** | - | Rep reply to client inquiry |
| `GET` | `/api/console/clients/{client_id}/portal/audit-log` | **`client-scoped`** | - | View client portal audit trail |
| `GET` | `/api/console/clients/{client_id}/portal/contacts` | **`client-scoped`** | - | List portal contacts for assigned client |
| `POST` | `/api/console/clients/{client_id}/portal/contacts` | **`client-scoped`** | - | Provision new portal contact for client |
| `PATCH` | `/api/console/clients/{client_id}/portal/contacts/{contact_id}/deactivate` | **`client-scoped`** | - | Deactivate portal contact |
| `POST` | `/api/console/clients/{client_id}/portal/contacts/{contact_id}/issue-code` | **`client-scoped`** | - | Issue new access code for portal contact |
| `POST` | `/api/console/clients/{client_id}/portal/contacts/{contact_id}/revoke-code` | **`client-scoped`** | - | Revoke access code for portal contact |
| `POST` | `/api/console/clients/{client_id}/portal/contacts/{contact_id}/unlock` | **`client-scoped`** | - | Unlock locked portal contact |
| `GET` | `/api/console/clients/{client_id}/portal/profile-audit` | **`client-scoped`** | - | View client profile audit trail |
| `POST` | `/api/console/clients/{client_id}/portal/revoke-all-sessions` | **`client-scoped`** | - | Revoke all portal sessions for client |
| `POST` | `/api/console/clients/{client_id}/portal/rotate-legacy-code` | **`client-scoped`** | - | Rotate legacy access code for client |
| `GET` | `/api/console/clients/{client_id}/quotes` | **`client-scoped`** | - | List quotes for assigned client |
| `POST` | `/api/console/clients/{client_id}/quotes/{quote_id}/send` | **`client-scoped`** | - | Send quote to client |
| `POST` | `/api/generate_chart_insight` | **`client-scoped`** | Yes | Generate Groq LLM chart narrative |
| `POST` | `/api/generate_insight` | **`client-scoped`** | Yes | Generate Groq LLM client insight card |
| `POST` | `/api/generate_invite` | **`client-scoped`** | Yes | Generate Groq LLM personalized portal invitation copy |
| `POST` | `/api/generate_reasoning` | **`client-scoped`** | Yes | Generate Groq LLM deal reasoning narrative |
| `POST` | `/api/invite/mark_sent` | **`client-scoped`** | - | Mark invitation as dispatched to client |
| `POST` | `/api/log_viewing` | **`client-scoped`** | - | Log viewing session for client |
| `POST` | `/api/record_outcome` | **`client-scoped`** | - | Record closed-won or closed-lost deal outcome |
| `POST` | `/api/schedule_viewing` | **`client-scoped`** | - | Schedule new property viewing appointment |
| `POST` | `/api/whatsapp/clear_opt_out` | **`client-scoped`** | - | Clear opt-out status on explicit client request |
| `POST` | `/api/whatsapp/conversations/{conversation_id}/read` | **`client-scoped`** | - | Mark WhatsApp conversation messages as read |
| `POST` | `/api/whatsapp/nudge` | **`client-scoped`** | - | Trigger nudge message for stale client conversation |
| `POST` | `/api/whatsapp/resume_automation` | **`client-scoped`** | - | Resume automated follow-ups for client conversation |
| `POST` | `/api/whatsapp/send` | **`client-scoped`** | - | Send WhatsApp message to client |
| `POST` | `/api/whatsapp/send_message` | **`client-scoped`** | - | Direct WhatsApp outbound message |
| `POST` | `/api/whatsapp/send_pitch` | **`client-scoped`** | - | Send property pitch message to client |
| `POST` | `/api/whatsapp/suggest_reply` | **`client-scoped`** | Yes | Generate Groq LLM suggested reply for WhatsApp conversation |
| `GET` | `/api/whatsapp/window_status` | **`client-scoped`** | - | Check Meta 24-hour customer service window status |
| `POST` | `/api/portal/auth/logout` | **`portal-session`** | - | Portal session logout |
| `GET` | `/api/portal/auth/me` | **`portal-session`** | - | Portal current session identity |
| `GET` | `/api/portal/{client_id}/activity` | **`portal-session`** | - | Portal client activity stream |
| `GET` | `/api/portal/{client_id}/catalog` | **`portal-session`** | - | Portal client property catalog |
| `PUT` | `/api/portal/{client_id}/catalog/{property_id}/feedback` | **`portal-session`** | - | Portal client unit feedback |
| `GET` | `/api/portal/{client_id}/dashboard` | **`portal-session`** | - | Portal client dashboard stats |
| `GET` | `/api/portal/{client_id}/demos` | **`portal-session`** | - | Portal client scheduled demos list |
| `POST` | `/api/portal/{client_id}/demos/{demo_id}/cancel` | **`portal-session`** | - | Portal client cancel demo |
| `POST` | `/api/portal/{client_id}/demos/{demo_id}/confirm` | **`portal-session`** | - | Portal client confirm demo slot |
| `POST` | `/api/portal/{client_id}/demos/{demo_id}/reschedule` | **`portal-session`** | - | Portal client reschedule demo |
| `GET` | `/api/portal/{client_id}/inquiries` | **`portal-session`** | - | Portal client inquiries list |
| `POST` | `/api/portal/{client_id}/inquiries/{inquiry_id}/messages` | **`portal-session`** | - | Portal client submit inquiry message |
| `POST` | `/api/portal/{client_id}/inquiries/{inquiry_id}/read` | **`portal-session`** | - | Portal client mark inquiry messages read |
| `POST` | `/api/portal/{client_id}/inquiry` | **`portal-session`** | - | Portal client submit inquiry |
| `GET` | `/api/portal/{client_id}/my_viewings` | **`portal-session`** | - | Portal client scheduled viewings |
| `GET` | `/api/portal/{client_id}/preferences` | **`portal-session`** | - | Portal client preferences get |
| `PUT` | `/api/portal/{client_id}/preferences` | **`portal-session`** | - | Portal client preferences update |
| `GET` | `/api/portal/{client_id}/quotes` | **`portal-session`** | - | Portal client quotes list |
| `POST` | `/api/portal/{client_id}/quotes` | **`portal-session`** | - | Portal client request quote |
| `POST` | `/api/portal/{client_id}/quotes/{quote_id}/respond` | **`portal-session`** | - | Portal client respond to quote |
| `POST` | `/api/portal/{client_id}/request_demo` | **`portal-session`** | - | Portal client request viewing |
| `POST` | `/api/agent/enroll` | **`public`** | - | Agent one-time code enrollment |
| `POST` | `/api/agent/login` | **`public`** | - | Agent credential authentication |
| `POST` | `/api/agent/reset-password` | **`public`** | - | Agent password reset execution |
| `GET` | `/api/calendar/{viewing_id}` | **`public`** | - | Signed calendar invite subscription (without .ics extension) |
| `GET` | `/api/calendar/{viewing_id}.ics` | **`public`** | - | Signed calendar invite subscription |
| `GET` | `/api/health` | **`public`** | - | Health check probe |
| `POST` | `/api/portal/auth/legacy-login` | **`public`** | - | Portal legacy access code authentication |
| `POST` | `/api/portal/auth/request-code` | **`public`** | - | Portal OTP SMS/WA request |
| `POST` | `/api/portal/auth/verify-code` | **`public`** | - | Portal OTP verification |
| `POST` | `/api/portal/auth/verify-invite` | **`public`** | - | Portal invite token validation |
| `POST` | `/api/portal/login` | **`public`** | - | Portal legacy login endpoint |
| `GET` | `/api/whatsapp/webhook` | **`public`** | - | WhatsApp Meta webhook challenge verification |
| `POST` | `/api/whatsapp/webhook` | **`public`** | - | WhatsApp Meta signed incoming events |
