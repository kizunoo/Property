-- Migration 17: Add WhatsApp Number to Clients
-- Idempotent, safe to re-run
BEGIN;

ALTER TABLE public.clients ADD COLUMN IF NOT EXISTS whatsapp_number text;

COMMIT;
