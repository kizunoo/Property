-- ============================================================================
-- Migration: 20261014120000_agent_auth_d1.sql
-- Description: Part D Stage D1 - Internal Agent Authentication, Session Management,
--              Argon2id credentials, Atomic Lockout Functions, and Audit Logging.
-- Note: Encapsulated in a single transaction. Do NOT apply without user approval.
-- ============================================================================

BEGIN;

-- 1. Create agent_accounts table
CREATE TABLE IF NOT EXISTS agent_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID UNIQUE REFERENCES agents(id) ON DELETE SET NULL,
    email TEXT NOT NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'agent' CHECK (role IN ('admin', 'agent')),
    password_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending_enrollment'
        CHECK (status IN ('active', 'suspended', 'pending_enrollment')),
    failed_login_attempts INT NOT NULL DEFAULT 0,
    locked_until TIMESTAMPTZ,
    enrollment_code_hash TEXT,
    enrollment_code_expires_at TIMESTAMPTZ,
    reset_code_hash TEXT,
    reset_code_expires_at TIMESTAMPTZ,
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Case-insensitive unique index on agent email
CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_accounts_lower_email
    ON agent_accounts (lower(email));

CREATE INDEX IF NOT EXISTS idx_agent_accounts_agent_id ON agent_accounts (agent_id);

-- 2. Create agent_sessions table
CREATE TABLE IF NOT EXISTS agent_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID NOT NULL REFERENCES agent_accounts(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    idle_expires_at TIMESTAMPTZ NOT NULL,
    absolute_expires_at TIMESTAMPTZ NOT NULL,
    last_active_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at TIMESTAMPTZ,
    ip_hash TEXT,
    user_agent TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_sessions_token_hash ON agent_sessions (token_hash);
CREATE INDEX IF NOT EXISTS idx_agent_sessions_agent_id ON agent_sessions (agent_id);

-- 3. Create agent_audit_log table (singular, matching portal_audit_log)
CREATE TABLE IF NOT EXISTS agent_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID REFERENCES agent_accounts(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    object_type TEXT NOT NULL,
    object_id TEXT,
    details JSONB,
    ip_hash TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_audit_agent ON agent_audit_log (agent_id);
CREATE INDEX IF NOT EXISTS idx_agent_audit_created ON agent_audit_log (created_at DESC);

-- 4. Atomic SQL function: agent_record_failed_login
CREATE OR REPLACE FUNCTION agent_record_failed_login(
    p_agent_id UUID,
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
    v_acc agent_accounts%ROWTYPE;
    v_attempts INT;
    v_locked_until TIMESTAMPTZ := NULL;
BEGIN
    SELECT * INTO v_acc FROM agent_accounts WHERE agent_accounts.id = p_agent_id FOR UPDATE;
    IF NOT FOUND THEN
        RETURN;
    END IF;

    -- If existing lockout expired, reset attempts counter for new window
    IF v_acc.locked_until IS NOT NULL AND v_now >= v_acc.locked_until THEN
        v_attempts := 1;
        v_locked_until := NULL;
    ELSE
        v_attempts := COALESCE(v_acc.failed_login_attempts, 0) + 1;
        IF v_attempts >= p_max_attempts THEN
            v_locked_until := v_now + (p_lockout_seconds || ' seconds')::INTERVAL;
        ELSE
            v_locked_until := v_acc.locked_until;
        END IF;
    END IF;

    UPDATE agent_accounts
    SET failed_login_attempts = v_attempts,
        locked_until = v_locked_until
    WHERE agent_accounts.id = p_agent_id;

    RETURN QUERY SELECT v_attempts, (v_locked_until IS NOT NULL AND v_locked_until > v_now), v_locked_until;
END;
$$;

-- 5. Atomic SQL function: agent_reset_login_lockout
CREATE OR REPLACE FUNCTION agent_reset_login_lockout(p_agent_id UUID)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
    UPDATE agent_accounts
    SET failed_login_attempts = 0,
        locked_until = NULL
    WHERE agent_accounts.id = p_agent_id;
END;
$$;

-- 6. Function Grants
REVOKE ALL ON FUNCTION agent_record_failed_login(UUID, INT, INT) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agent_record_failed_login(UUID, INT, INT) TO service_role;

REVOKE ALL ON FUNCTION agent_reset_login_lockout(UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agent_reset_login_lockout(UUID) TO service_role;

-- 7. Enable RLS and Lock Down Public Grants
ALTER TABLE agent_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_audit_log ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE agent_accounts FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE agent_sessions FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE agent_audit_log FROM PUBLIC, anon, authenticated;

GRANT ALL ON TABLE agent_accounts TO service_role;
GRANT ALL ON TABLE agent_sessions TO service_role;
GRANT ALL ON TABLE agent_audit_log TO service_role;

COMMIT;
