-- ==============================================================================
-- Migration: 20261016210000_stated_budget_null_and_whatsapp_optin.sql
-- Purpose:
--   1. Change clients.stated_budget default from 0 to NULL
--   2. Set stated_budget = NULL for all clients where data_source = 'real'
--   3. Add explicit opted_in column to whatsapp_contact_state with default false
-- ==============================================================================

-- 1. Alter stated_budget default to NULL
ALTER TABLE public.clients
  ALTER COLUMN stated_budget DROP DEFAULT,
  ALTER COLUMN stated_budget SET DEFAULT NULL;

-- 2. Set stated_budget = NULL for real companies
UPDATE public.clients
  SET stated_budget = NULL
  WHERE data_source = 'real';

-- 3. Add explicit opt-in column to whatsapp_contact_state (default-deny)
ALTER TABLE public.whatsapp_contact_state
  ADD COLUMN IF NOT EXISTS opted_in boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS opted_in_at timestamptz,
  ADD COLUMN IF NOT EXISTS opt_in_method text;

CREATE INDEX IF NOT EXISTS idx_wa_contact_optin ON public.whatsapp_contact_state(opted_in);
