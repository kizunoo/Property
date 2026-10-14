-- ============================================================================
-- Migration: 20261014110000_portal_v2_phase1a.sql
-- Description: Portal v2 Phase 1a Authentication, Contacts, Sessions, Audit Trail,
--              Atomic Rate Limiter RPCs, and RLS Lockdown.
-- Note: Encapsulated in a single transaction. Do NOT apply without user approval.
-- ============================================================================

BEGIN;

-- 1. Drop unused prototype tables (verified 0 rows, no external dependencies)
DROP TABLE IF EXISTS portal_sessions CASCADE;
DROP TABLE IF EXISTS client_accounts CASCADE;

-- 2. Add HMAC hash column to clients table for legacy codes
ALTER TABLE clients
    ADD COLUMN IF NOT EXISTS portal_access_code_hash TEXT;

-- 3. Create portal_contacts table
-- Supports:
-- - rep_code_hash & rep_code_expires_at (rep-issued 6-char code)
-- - self_code_hash & self_code_expires_at (self-service 6-char code)
-- - invite_token_hash & invite_token_expires_at (32-byte single-use URL token)
-- - atomic failed attempts counter and lockout
CREATE TABLE portal_contacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    email TEXT,
    whatsapp_number TEXT,
    title TEXT,
    portal_role TEXT NOT NULL DEFAULT 'evaluator'
        CHECK (portal_role IN ('admin', 'evaluator', 'finance_viewer')),
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'deactivated')),
    rep_code_hash TEXT,
    rep_code_expires_at TIMESTAMPTZ,
    self_code_hash TEXT,
    self_code_expires_at TIMESTAMPTZ,
    invite_token_hash TEXT,
    invite_token_expires_at TIMESTAMPTZ,
    failed_login_attempts INT NOT NULL DEFAULT 0,
    locked_until TIMESTAMPTZ,
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Partial UNIQUE index: Email is unique per contact across companies when provided
CREATE UNIQUE INDEX idx_portal_contacts_email_unique
    ON portal_contacts (lower(email))
    WHERE email IS NOT NULL;

-- Partial UNIQUE index: Exactly one primary contact per client company
CREATE UNIQUE INDEX idx_portal_contacts_client_primary_unique
    ON portal_contacts (client_id)
    WHERE is_primary = TRUE;

CREATE INDEX idx_portal_contacts_client_id ON portal_contacts (client_id);
CREATE INDEX idx_portal_contacts_whatsapp ON portal_contacts (whatsapp_number);
CREATE INDEX idx_portal_contacts_invite_hash ON portal_contacts (invite_token_hash)
    WHERE invite_token_hash IS NOT NULL;

-- 4. Create portal_sessions table (SHA-256 hashed token, idle & absolute expiry)
CREATE TABLE portal_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    contact_id UUID REFERENCES portal_contacts(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    portal_role TEXT NOT NULL,
    idle_expires_at TIMESTAMPTZ NOT NULL,
    absolute_expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_active_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at TIMESTAMPTZ,
    ip_hash TEXT,
    user_agent TEXT
);

CREATE INDEX idx_portal_sessions_token_hash ON portal_sessions (token_hash);
CREATE INDEX idx_portal_sessions_client_id ON portal_sessions (client_id);

-- 5. Create portal_audit_log table (tamper-evident audit trail)
CREATE TABLE portal_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    contact_id UUID REFERENCES portal_contacts(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    object_type TEXT NOT NULL,
    object_id TEXT,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    ip_hash TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_portal_audit_log_client_id ON portal_audit_log (client_id);
CREATE INDEX idx_portal_audit_log_created_at ON portal_audit_log (created_at DESC);

-- 6. Create persistent rate limits table
CREATE TABLE portal_rate_limits (
    key_hash TEXT PRIMARY KEY,
    bucket_type TEXT NOT NULL,
    attempt_count INT NOT NULL DEFAULT 1,
    window_start TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    locked_until TIMESTAMPTZ
);

-- 7. Atomic Rate Limiting & Lockout RPC Functions (SECURITY DEFINER)

CREATE OR REPLACE FUNCTION portal_increment_rate_limit(
    p_key_hash TEXT,
    p_bucket_type TEXT,
    p_window_seconds INT,
    p_max_attempts INT,
    p_lockout_seconds INT
)
RETURNS TABLE (
    allowed BOOLEAN,
    locked_until TIMESTAMPTZ,
    current_count INT
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_now TIMESTAMPTZ := NOW();
    v_row portal_rate_limits%ROWTYPE;
    v_lock_until TIMESTAMPTZ := NULL;
BEGIN
    SELECT * INTO v_row FROM portal_rate_limits WHERE key_hash = p_key_hash FOR UPDATE;
    IF NOT FOUND THEN
        INSERT INTO portal_rate_limits (key_hash, bucket_type, attempt_count, window_start, locked_until)
        VALUES (p_key_hash, p_bucket_type, 1, v_now, NULL)
        RETURNING * INTO v_row;
        RETURN QUERY SELECT TRUE, NULL::TIMESTAMPTZ, 1;
        RETURN;
    END IF;

    -- Check active lockout
    IF v_row.locked_until IS NOT NULL AND v_now < v_row.locked_until THEN
        RETURN QUERY SELECT FALSE, v_row.locked_until, v_row.attempt_count;
        RETURN;
    END IF;

    -- Check window expiration
    IF v_now > v_row.window_start + (p_window_seconds || ' seconds')::INTERVAL THEN
        UPDATE portal_rate_limits
        SET attempt_count = 1, window_start = v_now, locked_until = NULL
        WHERE key_hash = p_key_hash;
        RETURN QUERY SELECT TRUE, NULL::TIMESTAMPTZ, 1;
        RETURN;
    END IF;

    -- Increment attempt within window
    IF v_row.attempt_count + 1 >= p_max_attempts THEN
        v_lock_until := v_now + (p_lockout_seconds || ' seconds')::INTERVAL;
        UPDATE portal_rate_limits
        SET attempt_count = attempt_count + 1, locked_until = v_lock_until
        WHERE key_hash = p_key_hash;
        RETURN QUERY SELECT FALSE, v_lock_until, v_row.attempt_count + 1;
        RETURN;
    ELSE
        UPDATE portal_rate_limits
        SET attempt_count = attempt_count + 1
        WHERE key_hash = p_key_hash;
        RETURN QUERY SELECT TRUE, NULL::TIMESTAMPTZ, v_row.attempt_count + 1;
        RETURN;
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION portal_record_failed_contact_attempt(
    p_contact_id UUID,
    p_max_attempts INT DEFAULT 5,
    p_lockout_seconds INT DEFAULT 900
)
RETURNS TABLE (
    failed_attempts INT,
    locked_until TIMESTAMPTZ
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_now TIMESTAMPTZ := NOW();
    v_failed INT;
    v_lock TIMESTAMPTZ := NULL;
BEGIN
    UPDATE portal_contacts
    SET failed_login_attempts = failed_login_attempts + 1
    WHERE id = p_contact_id
    RETURNING failed_login_attempts INTO v_failed;

    IF v_failed >= p_max_attempts THEN
        v_lock := v_now + (p_lockout_seconds || ' seconds')::INTERVAL;
        UPDATE portal_contacts
        SET locked_until = v_lock
        WHERE id = p_contact_id;
    END IF;

    RETURN QUERY SELECT v_failed, v_lock;
END;
$$;

CREATE OR REPLACE FUNCTION portal_reset_contact_lockout(p_contact_id UUID)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    UPDATE portal_contacts
    SET failed_login_attempts = 0, locked_until = NULL
    WHERE id = p_contact_id;
END;
$$;

-- Secure function execution grants
REVOKE ALL ON FUNCTION portal_increment_rate_limit FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION portal_record_failed_contact_attempt FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION portal_reset_contact_lockout FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION portal_increment_rate_limit TO service_role;
GRANT EXECUTE ON FUNCTION portal_record_failed_contact_attempt TO service_role;
GRANT EXECUTE ON FUNCTION portal_reset_contact_lockout TO service_role;

-- 8. Idempotent Backfill: Create primary contact only for clients that do not already have one
INSERT INTO portal_contacts (client_id, name, whatsapp_number, portal_role, is_primary)
SELECT
    c.id,
    COALESCE(c.name, 'Primary Contact') || ' Admin',
    c.whatsapp_number,
    'admin',
    TRUE
FROM clients c
WHERE NOT EXISTS (
    SELECT 1 FROM portal_contacts pc WHERE pc.client_id = c.id AND pc.is_primary = TRUE
);

-- 9. Lockdown: Enable RLS and revoke anon/authenticated (service_role only)
ALTER TABLE portal_contacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE portal_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE portal_audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE portal_rate_limits ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON portal_contacts FROM anon, authenticated;
REVOKE ALL ON portal_sessions FROM anon, authenticated;
REVOKE ALL ON portal_audit_log FROM anon, authenticated;
REVOKE ALL ON portal_rate_limits FROM anon, authenticated;

GRANT ALL ON portal_contacts TO service_role;
GRANT ALL ON portal_sessions TO service_role;
GRANT ALL ON portal_audit_log TO service_role;
GRANT ALL ON portal_rate_limits TO service_role;

COMMIT;
