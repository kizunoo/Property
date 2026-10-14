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
CREATE TABLE IF NOT EXISTS portal_contacts (
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
CREATE UNIQUE INDEX IF NOT EXISTS uq_portal_contacts_lower_email
    ON portal_contacts (lower(email))
    WHERE email IS NOT NULL;

-- Partial UNIQUE index: Exactly one primary contact per client company
CREATE UNIQUE INDEX IF NOT EXISTS uq_portal_contacts_client_primary
    ON portal_contacts (client_id)
    WHERE is_primary = TRUE;

CREATE INDEX IF NOT EXISTS idx_portal_contacts_client_id ON portal_contacts (client_id);
CREATE INDEX IF NOT EXISTS idx_portal_contacts_whatsapp ON portal_contacts (whatsapp_number);

-- 4. Idempotent Primary Contact Backfill for existing clients
INSERT INTO portal_contacts (client_id, name, whatsapp_number, title, is_primary, portal_role, status)
SELECT c.id, c.name, c.whatsapp_number, 'Primary Contact', TRUE, 'admin', 'active'
FROM clients c
WHERE NOT EXISTS (
    SELECT 1 FROM portal_contacts pc WHERE pc.client_id = c.id AND pc.is_primary = TRUE
)
ON CONFLICT (client_id) WHERE is_primary = TRUE DO NOTHING;

-- 5. Create portal_sessions table (opaque 32-byte session tokens stored hashed)
CREATE TABLE IF NOT EXISTS portal_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    contact_id UUID REFERENCES portal_contacts(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    portal_role TEXT NOT NULL DEFAULT 'evaluator',
    idle_expires_at TIMESTAMPTZ NOT NULL,
    absolute_expires_at TIMESTAMPTZ NOT NULL,
    last_active_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at TIMESTAMPTZ,
    ip_hash TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_portal_sessions_token_hash ON portal_sessions (token_hash);
CREATE INDEX IF NOT EXISTS idx_portal_sessions_client_id ON portal_sessions (client_id);
CREATE INDEX IF NOT EXISTS idx_portal_sessions_contact_id ON portal_sessions (contact_id);

-- 6. Create portal_audit_log table
CREATE TABLE IF NOT EXISTS portal_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    contact_id UUID REFERENCES portal_contacts(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    object_type TEXT NOT NULL,
    object_id TEXT,
    details JSONB,
    ip_hash TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_portal_audit_client ON portal_audit_log (client_id);
CREATE INDEX IF NOT EXISTS idx_portal_audit_contact ON portal_audit_log (contact_id);
CREATE INDEX IF NOT EXISTS idx_portal_audit_created ON portal_audit_log (created_at DESC);

-- 7. Create portal_rate_limits table (supports key column for atomic increments)
CREATE TABLE IF NOT EXISTS portal_rate_limits (
    key TEXT PRIMARY KEY,
    attempts INT NOT NULL DEFAULT 1,
    window_start TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reset_at TIMESTAMPTZ NOT NULL,
    locked_until TIMESTAMPTZ
);

-- 8. Atomic SQL function: portal_increment_rate_limit
CREATE OR REPLACE FUNCTION portal_increment_rate_limit(
    p_key TEXT,
    p_window_seconds INT DEFAULT 900
)
RETURNS TABLE(out_attempts INT, out_reset_at TIMESTAMPTZ)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_now TIMESTAMPTZ := clock_timestamp();
    v_reset_at TIMESTAMPTZ := v_now + (p_window_seconds || ' seconds')::INTERVAL;
    v_attempts INT;
BEGIN
    INSERT INTO portal_rate_limits (key, attempts, window_start, reset_at)
    VALUES (p_key, 1, v_now, v_reset_at)
    ON CONFLICT (key) DO UPDATE
    SET attempts = CASE 
            WHEN portal_rate_limits.reset_at <= v_now THEN 1 
            ELSE portal_rate_limits.attempts + 1 
        END,
        window_start = CASE 
            WHEN portal_rate_limits.reset_at <= v_now THEN v_now 
            ELSE portal_rate_limits.window_start 
        END,
        reset_at = CASE 
            WHEN portal_rate_limits.reset_at <= v_now THEN v_reset_at 
            ELSE portal_rate_limits.reset_at 
        END
    RETURNING portal_rate_limits.attempts, portal_rate_limits.reset_at INTO v_attempts, v_reset_at;

    RETURN QUERY SELECT v_attempts, v_reset_at;
END;
$$;

-- 9. Atomic SQL function: portal_record_failed_contact_attempt
CREATE OR REPLACE FUNCTION portal_record_failed_contact_attempt(
    p_contact_id UUID,
    p_max_attempts INT DEFAULT 5,
    p_lockout_seconds INT DEFAULT 900
)
RETURNS TABLE(out_failed_attempts INT, out_is_locked BOOLEAN, out_locked_until TIMESTAMPTZ)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_now TIMESTAMPTZ := clock_timestamp();
    v_contact portal_contacts%ROWTYPE;
    v_attempts INT;
    v_locked_until TIMESTAMPTZ := NULL;
BEGIN
    SELECT * INTO v_contact FROM portal_contacts WHERE portal_contacts.id = p_contact_id FOR UPDATE;
    IF NOT FOUND THEN
        RETURN;
    END IF;

    -- If existing lockout expired, reset attempts counter for new window
    IF v_contact.locked_until IS NOT NULL AND v_now >= v_contact.locked_until THEN
        v_attempts := 1;
        v_locked_until := NULL;
    ELSE
        v_attempts := COALESCE(v_contact.failed_login_attempts, 0) + 1;
        IF v_attempts >= p_max_attempts THEN
            v_locked_until := v_now + (p_lockout_seconds || ' seconds')::INTERVAL;
        ELSE
            v_locked_until := v_contact.locked_until;
        END IF;
    END IF;

    UPDATE portal_contacts
    SET failed_login_attempts = v_attempts,
        locked_until = v_locked_until
    WHERE portal_contacts.id = p_contact_id;

    RETURN QUERY SELECT v_attempts, (v_locked_until IS NOT NULL AND v_locked_until > v_now), v_locked_until;
END;
$$;

-- 10. Atomic SQL function: portal_reset_contact_lockout
CREATE OR REPLACE FUNCTION portal_reset_contact_lockout(p_contact_id UUID)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
    UPDATE portal_contacts
    SET failed_login_attempts = 0,
        locked_until = NULL
    WHERE portal_contacts.id = p_contact_id;
END;
$$;

-- 11. Security Grants on Functions
REVOKE ALL ON FUNCTION portal_increment_rate_limit(TEXT, INT) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION portal_increment_rate_limit(TEXT, INT) TO service_role;

REVOKE ALL ON FUNCTION portal_record_failed_contact_attempt(UUID, INT, INT) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION portal_record_failed_contact_attempt(UUID, INT, INT) TO service_role;

REVOKE ALL ON FUNCTION portal_reset_contact_lockout(UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION portal_reset_contact_lockout(UUID) TO service_role;

-- 12. Enable RLS and Lock Down Public Grants
ALTER TABLE portal_contacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE portal_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE portal_audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE portal_rate_limits ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE portal_contacts FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE portal_sessions FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE portal_audit_log FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE portal_rate_limits FROM PUBLIC, anon, authenticated;

GRANT ALL ON TABLE portal_contacts TO service_role;
GRANT ALL ON TABLE portal_sessions TO service_role;
GRANT ALL ON TABLE portal_audit_log TO service_role;
GRANT ALL ON TABLE portal_rate_limits TO service_role;

COMMIT;
