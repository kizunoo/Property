-- ============================================================================
-- Migration: 20261015160000_auth_corrections.sql
-- Description: Corrective migration that supersedes edits that were incorrectly
--              applied to the already-deployed migrations:
--                * 20261012190000_security_hardening.sql
--                * 20261014110000_portal_v2_phase1a.sql
--                * 20261014120000_agent_auth_d1.sql
--
--  Changes included here:
--  1.  portal_contacts        - ADD COLUMN last_failed_at
--  2.  portal_sessions        - ADD COLUMN user_agent
--  3.  agent_accounts         - password_hash made nullable (pending_enrollment row)
--                              - status CHECK extended with 'deactivated'
--                              - ADD COLUMN last_failed_at
--                              - ADD CONSTRAINT chk_agent_accounts_active_password
--  4.  agent_sessions         - rename FK column agent_id -> account_id
--  5.  agent_audit_log        - rename FK column agent_id -> account_id
--  6.  portal_record_failed_login
--       - replaces portal_record_failed_contact_attempt:
--         sliding window, early-return when already locked, tracks last_failed_at
--  7.  portal_reset_contact_lockout - clears last_failed_at on reset
--  8.  agent_record_failed_login
--       - new 4-argument signature (p_account_id rename + p_window_seconds)
--         with sliding window logic and early-return when already locked
--  9.  agent_reset_failed_login - replaces agent_reset_login_lockout
-- 10.  check_column_privilege  - DROP + re-CREATE to ensure clean state
-- 11.  claim_due_whatsapp_reminders - alias for claim_and_lock_pending_reminders
-- 12.  Corrective REVOKE / GRANT for every affected function signature
-- 13.  ALTER DEFAULT PRIVILEGES to lock down future public function grants
-- 14.  Corrective REVOKE on legacy functions that lacked explicit PUBLIC revoke
-- ============================================================================

BEGIN;

-- ===========================================================================
-- 1. portal_contacts - add last_failed_at column (idempotent)
-- ===========================================================================
ALTER TABLE portal_contacts
    ADD COLUMN IF NOT EXISTS last_failed_at TIMESTAMPTZ;

-- ===========================================================================
-- 2. portal_sessions - add user_agent column (idempotent)
-- ===========================================================================
ALTER TABLE portal_sessions
    ADD COLUMN IF NOT EXISTS user_agent TEXT;

-- ===========================================================================
-- 3. agent_accounts - column/constraint corrections
-- ===========================================================================

-- 3a. Make password_hash nullable (required for pending_enrollment rows)
ALTER TABLE agent_accounts
    ALTER COLUMN password_hash DROP NOT NULL;

-- 3b. Extend status CHECK to include 'deactivated'
--     Drop ALL check constraints whose definition mentions 'status' (handles any
--     auto-generated name the original migration may have used).
DO $$
DECLARE c record;
BEGIN
  FOR c IN
    SELECT conname FROM pg_constraint
    WHERE conrelid = 'public.agent_accounts'::regclass
      AND contype = 'c'
      AND pg_get_constraintdef(oid) ILIKE '%status%'
  LOOP
    EXECUTE format('ALTER TABLE public.agent_accounts DROP CONSTRAINT %I', c.conname);
  END LOOP;
END $$;
ALTER TABLE public.agent_accounts
  ADD CONSTRAINT agent_accounts_status_check
  CHECK (status IN ('pending_enrollment','active','suspended','deactivated'));

-- 3c. Add last_failed_at column (idempotent)
ALTER TABLE agent_accounts
    ADD COLUMN IF NOT EXISTS last_failed_at TIMESTAMPTZ;

-- 3d. Add constraint: active accounts must have a password_hash
ALTER TABLE agent_accounts
    DROP CONSTRAINT IF EXISTS chk_agent_accounts_active_password;
ALTER TABLE agent_accounts
    ADD CONSTRAINT chk_agent_accounts_active_password
        CHECK (status != 'active' OR password_hash IS NOT NULL);

-- ===========================================================================
-- 4. agent_sessions - rename FK column agent_id -> account_id
--    (idempotent: only rename when old name still exists)
-- ===========================================================================
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name   = 'agent_sessions'
          AND column_name  = 'agent_id'
    ) THEN
        ALTER TABLE agent_sessions RENAME COLUMN agent_id TO account_id;
        DROP INDEX IF EXISTS idx_agent_sessions_agent_id;
        CREATE INDEX IF NOT EXISTS idx_agent_sessions_account_id ON agent_sessions (account_id);
    END IF;
END $$;

-- ===========================================================================
-- 5. agent_audit_log - rename FK column agent_id -> account_id
-- ===========================================================================
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name   = 'agent_audit_log'
          AND column_name  = 'agent_id'
    ) THEN
        ALTER TABLE agent_audit_log RENAME COLUMN agent_id TO account_id;
        DROP INDEX IF EXISTS idx_agent_audit_agent;
        CREATE INDEX IF NOT EXISTS idx_agent_audit_account ON agent_audit_log (account_id);
    END IF;
END $$;

-- ===========================================================================
-- 6. portal_record_failed_login
--    Replaces portal_record_failed_contact_attempt with:
--     - Renamed function
--     - 4th parameter p_window_seconds for sliding-window expiry
--     - Early return when account is already locked (no re-lock extension)
--     - Tracks last_failed_at for sliding window
-- ===========================================================================
CREATE OR REPLACE FUNCTION portal_record_failed_login(
    p_contact_id      UUID,
    p_max_attempts    INT DEFAULT 5,
    p_lockout_seconds INT DEFAULT 900,
    p_window_seconds  INT DEFAULT 900
)
RETURNS TABLE(out_failed_attempts INT, out_is_locked BOOLEAN, out_locked_until TIMESTAMPTZ)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_now          TIMESTAMPTZ := clock_timestamp();
    v_contact      portal_contacts%ROWTYPE;
    v_attempts     INT;
    v_locked_until TIMESTAMPTZ := NULL;
BEGIN
    SELECT * INTO v_contact FROM portal_contacts
    WHERE portal_contacts.id = p_contact_id FOR UPDATE;
    IF NOT FOUND THEN
        RETURN;
    END IF;

    -- If currently locked, return existing lock without extending
    IF v_contact.locked_until IS NOT NULL AND v_now < v_contact.locked_until THEN
        RETURN QUERY SELECT v_contact.failed_login_attempts, TRUE, v_contact.locked_until;
        RETURN;
    END IF;

    -- Sliding window: attempts older than window do not count
    IF v_contact.last_failed_at IS NOT NULL
       AND (v_now - v_contact.last_failed_at) > (p_window_seconds || ' seconds')::INTERVAL THEN
        v_attempts := 1;
    ELSIF v_contact.locked_until IS NOT NULL AND v_now >= v_contact.locked_until THEN
        v_attempts := 1;
    ELSE
        v_attempts := COALESCE(v_contact.failed_login_attempts, 0) + 1;
    END IF;

    IF v_attempts >= p_max_attempts THEN
        v_locked_until := v_now + (p_lockout_seconds || ' seconds')::INTERVAL;
    ELSE
        v_locked_until := NULL;
    END IF;

    UPDATE portal_contacts
    SET failed_login_attempts = v_attempts,
        locked_until          = v_locked_until,
        last_failed_at        = v_now
    WHERE portal_contacts.id = p_contact_id;

    RETURN QUERY SELECT v_attempts, (v_locked_until IS NOT NULL AND v_locked_until > v_now), v_locked_until;
END;
$$;

-- ===========================================================================
-- 7. portal_reset_contact_lockout - also clears last_failed_at
-- ===========================================================================
CREATE OR REPLACE FUNCTION portal_reset_contact_lockout(p_contact_id UUID)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
    UPDATE portal_contacts
    SET failed_login_attempts = 0,
        locked_until          = NULL,
        last_failed_at        = NULL
    WHERE portal_contacts.id = p_contact_id;
END;
$$;

-- ===========================================================================
-- 8. agent_record_failed_login - updated 4-arg signature
--    Old function had 3 args (p_agent_id, p_max_attempts, p_lockout_seconds).
--    New function uses p_account_id and adds p_window_seconds sliding window.
-- ===========================================================================

-- Drop old 3-arg variant if it still exists
DROP FUNCTION IF EXISTS agent_record_failed_login(UUID, INT, INT);

CREATE OR REPLACE FUNCTION agent_record_failed_login(
    p_account_id      UUID,
    p_max_attempts    INT DEFAULT 5,
    p_lockout_seconds INT DEFAULT 900,
    p_window_seconds  INT DEFAULT 900
)
RETURNS TABLE(out_failed_attempts INT, out_is_locked BOOLEAN, out_locked_until TIMESTAMPTZ)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_now          TIMESTAMPTZ := clock_timestamp();
    v_acc          agent_accounts%ROWTYPE;
    v_attempts     INT;
    v_locked_until TIMESTAMPTZ := NULL;
BEGIN
    SELECT * INTO v_acc FROM agent_accounts
    WHERE agent_accounts.id = p_account_id FOR UPDATE;
    IF NOT FOUND THEN
        RETURN;
    END IF;

    -- If currently locked, return existing lock without extending
    IF v_acc.locked_until IS NOT NULL AND v_now < v_acc.locked_until THEN
        RETURN QUERY SELECT v_acc.failed_login_attempts, TRUE, v_acc.locked_until;
        RETURN;
    END IF;

    -- Sliding window: attempts older than window do not count
    IF v_acc.last_failed_at IS NOT NULL
       AND (v_now - v_acc.last_failed_at) > (p_window_seconds || ' seconds')::INTERVAL THEN
        v_attempts := 1;
    ELSIF v_acc.locked_until IS NOT NULL AND v_now >= v_acc.locked_until THEN
        v_attempts := 1;
    ELSE
        v_attempts := COALESCE(v_acc.failed_login_attempts, 0) + 1;
    END IF;

    IF v_attempts >= p_max_attempts THEN
        v_locked_until := v_now + (p_lockout_seconds || ' seconds')::INTERVAL;
    ELSE
        v_locked_until := NULL;
    END IF;

    UPDATE agent_accounts
    SET failed_login_attempts = v_attempts,
        locked_until          = v_locked_until,
        last_failed_at        = v_now
    WHERE agent_accounts.id = p_account_id;

    RETURN QUERY SELECT v_attempts, (v_locked_until IS NOT NULL AND v_locked_until > v_now), v_locked_until;
END;
$$;

-- ===========================================================================
-- 9. agent_reset_failed_login
--    Replaces agent_reset_login_lockout; also clears last_failed_at.
-- ===========================================================================

-- Drop old function under previous name if still present
DROP FUNCTION IF EXISTS agent_reset_login_lockout(UUID);

CREATE OR REPLACE FUNCTION agent_reset_failed_login(p_account_id UUID)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
    UPDATE agent_accounts
    SET failed_login_attempts = 0,
        locked_until          = NULL,
        last_failed_at        = NULL
    WHERE agent_accounts.id = p_account_id;
END;
$$;

-- ===========================================================================
-- 10. check_column_privilege - DROP + re-CREATE (ensures clean state)
-- ===========================================================================
DROP FUNCTION IF EXISTS public.check_column_privilege(TEXT, TEXT, TEXT, TEXT);
CREATE OR REPLACE FUNCTION public.check_column_privilege(
    p_role      TEXT,
    p_table     TEXT,
    p_column    TEXT,
    p_privilege TEXT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    RETURN has_column_privilege(p_role, 'public.' || quote_ident(p_table), p_column, p_privilege);
EXCEPTION
    WHEN undefined_column THEN RETURN FALSE;
    WHEN undefined_table  THEN RETURN FALSE;
    WHEN others           THEN RETURN FALSE;
END;
$$;

-- ===========================================================================
-- 11. claim_due_whatsapp_reminders - alias for claim_and_lock_pending_reminders
--     Created only if the function does not already exist (never overwrites).
--     Signature of callee: claim_and_lock_pending_reminders(batch_limit int DEFAULT 10)
--     Return type: SETOF public.whatsapp_reminders
-- ===========================================================================
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'public' AND p.proname = 'claim_due_whatsapp_reminders'
  ) THEN
    EXECUTE $f$
      CREATE FUNCTION public.claim_due_whatsapp_reminders(p_limit INT DEFAULT 10)
      RETURNS SETOF public.whatsapp_reminders
      LANGUAGE plpgsql SECURITY DEFINER
      SET search_path = public, pg_temp
      AS $b$
      BEGIN
        RETURN QUERY SELECT * FROM public.claim_and_lock_pending_reminders(p_limit);
      END;
      $b$
    $f$;
  END IF;
END $$;

-- ===========================================================================
-- 12. Function Grants (exact signatures; service_role only)
-- ===========================================================================

REVOKE ALL ON FUNCTION portal_record_failed_login(UUID, INT, INT, INT)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION portal_record_failed_login(UUID, INT, INT, INT)
    TO service_role;

REVOKE ALL ON FUNCTION portal_reset_contact_lockout(UUID)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION portal_reset_contact_lockout(UUID)
    TO service_role;

REVOKE ALL ON FUNCTION agent_record_failed_login(UUID, INT, INT, INT)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agent_record_failed_login(UUID, INT, INT, INT)
    TO service_role;

REVOKE ALL ON FUNCTION agent_reset_failed_login(UUID)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agent_reset_failed_login(UUID)
    TO service_role;

REVOKE ALL ON FUNCTION public.check_column_privilege(TEXT, TEXT, TEXT, TEXT)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.check_column_privilege(TEXT, TEXT, TEXT, TEXT)
    TO service_role;

-- claim_due_whatsapp_reminders grants are handled in section 14 loop below

-- ===========================================================================
-- 13. Default Function Privileges Lockdown
--     Prevent future functions from being executable by anon/authenticated.
-- ===========================================================================
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC, anon, authenticated;

-- ===========================================================================
-- 14. Corrective REVOKE on legacy functions lacking explicit PUBLIC revoke
-- ===========================================================================
DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN (
        SELECT p.oid::regprocedure AS func_sig, p.proname
        FROM pg_proc p
        JOIN pg_namespace n ON p.pronamespace = n.oid
        WHERE n.nspname = 'public'
          AND p.proname IN (
              'claim_and_book_slot_offer',
              'claim_and_lock_pending_reminders',
              'claim_due_whatsapp_reminders',
              'get_role_table_privileges',
              'set_updated_at'
          )
    ) LOOP
        EXECUTE 'REVOKE ALL ON FUNCTION ' || r.func_sig || ' FROM PUBLIC, anon, authenticated;';
        IF r.proname NOT IN ('set_updated_at') THEN
            EXECUTE 'GRANT EXECUTE ON FUNCTION ' || r.func_sig || ' TO service_role;';
        END IF;
    END LOOP;
END $$;

COMMIT;
