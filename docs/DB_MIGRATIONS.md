# Database Migration Safety & Protocol Guide

This repository connects to a **single production Supabase project** (`tppzkfhhcnmdbwnamgqr`). There is no dev database copy. Safety and zero-downtime reliability are maintained strictly through process, automation guards, and immutable protocols.

---

## 1. Core Architecture & Migration Rules

1. **Every New Table Must Enable RLS & Revoke Public Access Immediately**:
   - Every `CREATE TABLE` statement must be followed in the same migration file by:
     ```sql
     ALTER TABLE public.<table_name> ENABLE ROW LEVEL SECURITY;
     REVOKE ALL ON public.<table_name> FROM anon, authenticated;
     ```
   - Lock down access to `service_role` unless the browser explicitly requires direct read access:
     ```sql
     CREATE POLICY "Service role full access on <table_name>"
       ON public.<table_name> FOR ALL TO service_role
       USING (true) WITH CHECK (true);
     ```
   - If the browser requires read access, add an explicit read-only policy for `anon` / `authenticated`:
     ```sql
     GRANT SELECT ON public.<table_name> TO anon, authenticated;
     CREATE POLICY "Allow public read on <table_name>"
       ON public.<table_name> FOR SELECT TO anon, authenticated
       USING (true);
     ```

2. **Column Whitelist on `public.clients`**:
   - Because table-level `SELECT` on `clients` is revoked from `anon` and `authenticated`, the browser relies on explicit column-level grants.
   - **Crucial**: Whenever you add a new column to `public.clients` that the frontend dashboard needs to read, you **must** update the column grant in that migration:
     ```sql
     GRANT SELECT (<existing_cols>, <new_column>) ON public.clients TO anon, authenticated;
     ```
   - Sensitive columns (`portal_access_code`, `whatsapp_number`) must **NEVER** be granted to `anon` or `authenticated`.

3. **Every Migration Must Be Idempotent and Transactional**:
   - Always wrap migrations in a transaction block:
     ```sql
     BEGIN;
     -- statements with IF EXISTS / IF NOT EXISTS
     COMMIT;
     ```
   - Statements that cannot run inside a transaction block (such as `CREATE INDEX CONCURRENTLY` or `VACUUM`) are prohibited. Use standard `CREATE INDEX IF NOT EXISTS`.

4. **Rollback Documentation Required**:
   - Every migration must include a companion rollback section or note in its header comments detailing the inverse DDL statements needed if reversal is required.

5. **Strict Prohibition on Destructive CLI Commands**:
   - **NEVER** run `npx supabase db reset` against the linked production project. It will wipe all production schemas and data permanently.
   - **NEVER** run `npx supabase db diff` or schema overrides without running `db:check` first.

---

## 2. Standard Migration Workflow

Follow this 5-stage lifecycle for every schema modification:

```
[1. Prepare Migration]
        │
        ▼
[2. npm run db:check] ──────► Scans for destructive patterns (DROP, TRUNCATE, REVOKE)
        │
        ▼
[3. npm run db:dry-run] ────► Simulates application with Supabase CLI
        │
        ▼
[4. Explicit Approval] ────► Run: npm run db:push -- --approve <migration_version>
        │
        ▼
[5. npm run db:verify] ─────► Read-only validation of RLS, grants & frontend queries
```

### Stage Details

1. **Prepare**:
   Create a new file in `supabase/migrations/` using timestamp naming:
   `YYYYMMDDHHMMSS_<descriptive_name>.sql`.
2. **Scan (`npm run db:check`)**:
   Lints pending migrations for destructive statements (`DROP TABLE/COLUMN/POLICY/FUNCTION`, `TRUNCATE`, `DELETE` without `WHERE`, `ALTER COLUMN TYPE`, `REVOKE`, `DISABLE ROW LEVEL SECURITY`).
3. **Dry Run (`npm run db:dry-run`)**:
   Runs safety checks and invokes `npx supabase db push --dry-run` to inspect remote differences before applying.
4. **Approve & Push (`npm run db:push -- --approve <version>`)**:
   The push wrapper will refuse to apply changes unless you supply `--approve <version>`.
5. **Verify (`npm run db:verify`)**:
   Executes non-destructive inspection of all tables, columns, RLS policies, column permissions, and the exact queries used by the dashboard.

---

## 3. Pre-Push Checklist

Before approving any database push to production:

- [ ] **Git Working Tree Committed**:
  Ensure all application and migration files are committed:
  ```bash
  git status
  git add supabase/migrations/
  git commit -m "feat(db): add <feature> migration"
  ```
- [ ] **Data Backup Verified** (Options):
  - **Option A (Supabase Dashboard)**: Go to Database &rarr; Backups &rarr; Scheduled or Download Backup.
  - **Option B (CLI Schema & Data Dump)**:
    ```bash
    # Dump production data to local backup file (requires DB password)
    npx supabase db dump --data-only -f backup_data_$(date +%Y%m%d).sql
    ```
- [ ] **API & Backend Parity**:
  Verify if Next.js route handlers or FastAPI backend services require deployment simultaneously to handle schema changes.
- [ ] **Column Whitelist Checked**:
  If adding columns to `clients`, confirm they are included in `GRANT SELECT (...)`.

---

## 4. Migration History Baseline Reference

| Timestamp Version | Migration Name | Applied In Prod |
| :--- | :--- | :---: |
| `20261012010000` | `base_schema.sql` | Yes |
| `20261012020000` | `rich_profiles.sql` | Yes |
| `20261012030000` | `agents.sql` | Yes |
| `20261012040000` | `outcome_columns.sql` | Yes |
| `20261012050000` | `scheduled_viewings.sql` | Yes |
| `20261012060000` | `portal_phase1.sql` | Yes |
| `20261012070000` | `portal_phase2.sql` | Yes |
| `20261012080000` | `relationship_stages.sql` | Yes |
| `20261012090000` | `client_past_purchases.sql` | Yes |
| `20261012100000` | `property_price_history.sql` | Yes |
| `20261012110000` | `ml_model_tables.sql` | Yes |
| `20261012120000` | `chart_insight_cache.sql` | Yes |
| `20261012130000` | `daily_worklist_cache.sql` | Yes |
| `20261012140000` | `whatsapp_core_tables.sql` | Yes |
| `20261012150000` | `whatsapp_slot_offers.sql` | Yes |
| `20261012160000` | `whatsapp_reminders.sql` | Yes |
| `20261012170000` | `add_whatsapp_number.sql` | Yes |
| `20261012180000` | `whatsapp_part4_inbox_compliance.sql` | Yes |
| `20261012190000` | `security_hardening.sql` | Yes |
| `20261014110000` | `portal_v2_phase1a.sql` | **Pending Approval (Dry-Run Validated)** |
| `20261014120000` | `agent_auth_d1.sql` | **Pending Approval (Dry-Run Validated)** |

---

## 5. Part D Stage D1 Migrations: Manual Walkthrough & Verification

> **IMPORTANT**: Migrations are strictly dry-run validated and MUST NOT be applied automatically. The engineer applies these via the Supabase SQL Editor or `npm run db:push -- --approve <version>` once approved.

### A. Pre-Flight Validation Checks
Before applying, run the automated schema and code usage validation:
```bash
# 1. Verify schema columns match backend usage 100%
python scripts/check_schema_usage.py

# 2. Run backend test suite (assert 140+ passing)
backend/venv/Scripts/python.exe -m pytest backend/tests

# 3. Run live Next.js proxy gate test
python scripts/test_nextjs_gate_live.py
```

### B. Applying Migrations (SQL Editor or CLI)
1. **Migration 1 (Portal v2 Phase 1a)**:
   File: `supabase/migrations/20261014110000_portal_v2_phase1a.sql`
   - Drops obsolete prototype tables (`portal_sessions`, `client_accounts`).
   - Adds `clients.portal_access_code_hash`.
   - Creates `portal_contacts` with case-insensitive unique email index and primary contact per client.
   - Automatically backfills existing clients with a primary contact row.
   - Creates `portal_sessions` with `token_hash`, `idle_expires_at`, `absolute_expires_at`, and `user_agent`.
   - Creates `portal_audit_log` and `portal_rate_limits`.
   - Creates atomic PL/pgSQL functions: `portal_increment_rate_limit`, `portal_record_failed_login`.
   - Locks down all tables with RLS (`REVOKE ALL FROM anon, authenticated`).

2. **Migration 2 (Agent Authentication D1)**:
   File: `supabase/migrations/20261014120000_agent_auth_d1.sql`
   - Creates `agent_accounts` with `status IN ('pending_enrollment', 'active', 'suspended', 'deactivated')`.
   - `password_hash` is nullable until enrollment, enforced by `CHECK (status != 'active' OR password_hash IS NOT NULL)`.
   - Unique case-insensitive index on `lower(email)`.
   - Creates `agent_sessions` with 256-bit token hashes and sliding window idle timeout.
   - Creates `agent_audit_log` table.
   - Creates atomic PL/pgSQL functions: `agent_record_failed_login`, `agent_reset_failed_login`.
   - Locks down all tables with RLS (`REVOKE ALL FROM anon, authenticated`).

### C. Post-Application Transactional Verification Script
Run the following self-contained transactional verification script in the Supabase SQL Editor. It creates temporary rows, verifies every PL/pgSQL function and lockout semantics (including non-extension of active locks and 15-minute windowing), raises an exception on any failure, and rolls back cleanly with zero changes persisted:

```sql
BEGIN;

DO $$
DECLARE
  v_client_id uuid;
  v_contact_id uuid;
  v_account_id uuid;
  v_rec record;
  v_locked_until_orig timestamptz;
BEGIN
  -- 1. Create temporary test client
  INSERT INTO public.clients (name, portal_access_code_hash)
  VALUES ('__TEST_VERIFY_CLIENT__', 'dummy_hash')
  RETURNING id INTO v_client_id;

  -- 2. Create temporary test contact
  INSERT INTO public.portal_contacts (client_id, name, email, is_primary)
  VALUES (v_client_id, 'Test Contact', 'test_verify_contact@example.com', true)
  RETURNING id INTO v_contact_id;

  -- 3. Create temporary test agent account
  INSERT INTO public.agent_accounts (email, name, role, status)
  VALUES ('test_verify_agent@example.com', 'Test Agent', 'agent', 'active')
  RETURNING id INTO v_account_id;

  -- 4. Test portal_increment_rate_limit
  SELECT * INTO v_rec FROM public.portal_increment_rate_limit('__test_ip_probe__', 900);
  IF v_rec.out_attempts != 1 THEN
    RAISE EXCEPTION 'portal_increment_rate_limit initial attempt failed: got %', v_rec.out_attempts;
  END IF;

  SELECT * INTO v_rec FROM public.portal_increment_rate_limit('__test_ip_probe__', 900);
  IF v_rec.out_attempts != 2 THEN
    RAISE EXCEPTION 'portal_increment_rate_limit second attempt failed: got %', v_rec.out_attempts;
  END IF;

  -- 5. Test portal_record_failed_login: max 3 attempts, 900s lockout, 900s window
  -- Attempt 1
  SELECT * INTO v_rec FROM public.portal_record_failed_login(v_contact_id, 3, 900, 900);
  IF v_rec.out_failed_attempts != 1 OR v_rec.out_is_locked = TRUE THEN
    RAISE EXCEPTION 'portal_record_failed_login attempt 1 failed: %', v_rec;
  END IF;

  -- Attempt 2
  SELECT * INTO v_rec FROM public.portal_record_failed_login(v_contact_id, 3, 900, 900);
  IF v_rec.out_failed_attempts != 2 OR v_rec.out_is_locked = TRUE THEN
    RAISE EXCEPTION 'portal_record_failed_login attempt 2 failed: %', v_rec;
  END IF;

  -- Attempt 3 (triggers lock)
  SELECT * INTO v_rec FROM public.portal_record_failed_login(v_contact_id, 3, 900, 900);
  IF v_rec.out_failed_attempts != 3 OR v_rec.out_is_locked = FALSE OR v_rec.out_locked_until IS NULL THEN
    RAISE EXCEPTION 'portal_record_failed_login attempt 3 lockout failed: %', v_rec;
  END IF;

  -- Attempt 4 while locked (MUST NOT EXTEND OR RESTART LOCK)
  v_locked_until_orig := v_rec.out_locked_until;
  SELECT * INTO v_rec FROM public.portal_record_failed_login(v_contact_id, 3, 900, 900);
  IF v_rec.out_locked_until != v_locked_until_orig THEN
    RAISE EXCEPTION 'portal_record_failed_login extended lock unexpectedly: % != %', v_rec.out_locked_until, v_locked_until_orig;
  END IF;

  -- Test portal_reset_contact_lockout
  PERFORM public.portal_reset_contact_lockout(v_contact_id);
  SELECT failed_attempts, locked_until INTO v_rec FROM public.portal_contacts WHERE id = v_contact_id;
  IF v_rec.failed_attempts != 0 OR v_rec.locked_until IS NOT NULL THEN
    RAISE EXCEPTION 'portal_reset_contact_lockout failed: %', v_rec;
  END IF;

  -- 6. Test agent_record_failed_login: max 5 attempts, 900s lockout, 900s window
  -- Attempt 1
  SELECT * INTO v_rec FROM public.agent_record_failed_login(v_account_id, 5, 900, 900);
  IF v_rec.out_failed_attempts != 1 OR v_rec.out_is_locked = TRUE THEN
    RAISE EXCEPTION 'agent_record_failed_login attempt 1 failed: %', v_rec;
  END IF;

  -- Reset agent failed login
  PERFORM public.agent_reset_failed_login(v_account_id);
  SELECT failed_login_attempts, locked_until INTO v_rec FROM public.agent_accounts WHERE id = v_account_id;
  IF v_rec.failed_login_attempts != 0 OR v_rec.locked_until IS NOT NULL THEN
    RAISE EXCEPTION 'agent_reset_failed_login failed: %', v_rec;
  END IF;

  RAISE NOTICE 'ALL MIGRATION FUNCTIONS AND LOCKOUT BEHAVIORS VERIFIED SUCCESSFULLY!';
END $$;

ROLLBACK;
```

### D. Agent Seeding Commands
Once migrations are applied, seed the initial accounts via CLI:
```bash
# Seed default accounts matched against public.agents table
backend/venv/Scripts/python.exe scripts/seed_agent_accounts.py --seed-defaults --csv agents_roster.csv

# Seed a custom administrator account (not linked to an agents representative row)
backend/venv/Scripts/python.exe scripts/seed_agent_accounts.py --email admin@pipeline-ev.com --name "System Administrator" --role admin

# Seed an agent representative linked by ID
backend/venv/Scripts/python.exe scripts/seed_agent_accounts.py --email agent1@pipeline-ev.com --name "Ahmad Zaki" --role agent --match-name "Ahmad Zaki"
```
The CLI prints a one-time single-use enrollment code (e.g. `K9W3-X7P2-M4Q8`). The agent accesses `http://localhost:3000/login`, switches to the **Activate Account** tab, enters the code, and sets their Argon2id password (>= 12 characters).

---

## 6. Development vs Production Environment Behavior Matrix

| Feature / Behavior | Development (`ENVIRONMENT=development`) | Production (`ENVIRONMENT=production`) |
| :--- | :--- | :--- |
| **Origin / Host Verification** | Allows `localhost:3000`, `127.0.0.1:3000`, `localhost:8000`, `127.0.0.1:8000` | Strict match against `ALLOWED_ORIGINS` & incoming `Host` |
| **Simulation Endpoints** (`/api/simulate_*`) | Enabled (requires admin session) | **Blocked immediately with HTTP 404** |
| **Dev Preview Page** (`/preview/*`) | Accessible (requires agent session) | **Blocked with HTTP 404** |
| **API Docs & Swagger** (`/docs`, `/redoc`) | Enabled for interactive testing | Stripped / disabled |
| **WhatsApp Webhook Signature** | Signature enforcement defaults to `true`. When using tunnel (ngrok) in development, set `ENFORCE_WA_SIGNATURE=true` explicitly to validate real Meta HMAC signatures. Set `ENFORCE_WA_SIGNATURE=false` only with `WHATSAPP_TEST_MODE=true` for local synthetic payload tests. | **Mandatory HMAC-SHA256 signature** (`ENFORCE_WA_SIGNATURE=true`) |
| **Missing Secrets at Boot** | Logs warnings; permits non-dependent startup | **Fails immediately with fatal `RuntimeError`** |
| **Proxy / Tunnel Requests** | Allowed for local ngrok debugging | Blocked unless fully authenticated through Next.js proxy |

---

## 7. Environment Variables Distribution Reference

> `BFF_INTERNAL_SECRET` is the shared symmetric token between the Next.js frontend proxy and the FastAPI logic engine. **Its value must match exactly in both files.**

### Backend Secrets: `backend/.env`
- `ENVIRONMENT` (`development` | `production`)
- `PORTAL_CODE_PEPPER` (Cryptographic salt for 6-char OTPs and portal session tokens)
- `BFF_INTERNAL_SECRET` (Shared secret verifying trusted Next.js proxy requests)
- `CALENDAR_SIGNING_SECRET` (HMAC key for signed `.ics` calendar subscriptions)
- `WHATSAPP_APP_SECRET` (Meta App Secret for webhook HMAC verification, >= 16 chars)
- `ENFORCE_WA_SIGNATURE` (Defaults to `true`)
- `SUPABASE_URL` (Supabase project API endpoint)
- `SUPABASE_SERVICE_ROLE_KEY` (Supabase service role secret key)
- `GROQ_API_KEY` (Groq LLM API key)
- `AGENT_SESSION_SECRET` (Optional extra HMAC pepper; defaults to `PORTAL_CODE_PEPPER`)

### Frontend Secrets: `.env.local`
- `ENVIRONMENT` (`development` | `production`)
- `BFF_INTERNAL_SECRET` (Shared secret forwarded in `X-BFF-Internal-Secret` header)
- `NEXT_PUBLIC_SUPABASE_URL` (Public Supabase URL)
- `NEXT_PUBLIC_SUPABASE_ANON_KEY` (Public Supabase anonymous key)
- `FASTAPI_URL` (Internal loopback address to FastAPI, e.g. `http://127.0.0.1:8000`)
- `ALLOWED_ORIGINS` (Comma-separated hostnames allowed to submit state-changing browser requests)

