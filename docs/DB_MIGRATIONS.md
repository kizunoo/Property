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
| `20261012200000` | `security_hardening_phase2.sql` | **Pending Approval** |
