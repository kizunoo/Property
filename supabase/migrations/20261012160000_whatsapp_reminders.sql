-- Migration 16: WhatsApp Reminders and Locking Queue RPC
-- Idempotent, safe to re-run
BEGIN;

ALTER TABLE public.scheduled_viewings
  ADD COLUMN IF NOT EXISTS client_confirmed_at timestamptz;

ALTER TABLE public.scheduled_viewings
  ADD COLUMN IF NOT EXISTS confirmation_status text DEFAULT 'unconfirmed';

CREATE TABLE IF NOT EXISTS public.whatsapp_reminders (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  viewing_id          uuid NOT NULL REFERENCES public.scheduled_viewings(id) ON DELETE CASCADE,
  client_id           uuid REFERENCES public.clients(id) ON DELETE SET NULL,
  agent_id            uuid REFERENCES public.agents(id) ON DELETE SET NULL,
  phone_number        text NOT NULL,
  reminder_type       text NOT NULL CHECK (reminder_type IN ('24h', '2h')),
  scheduled_send_time timestamptz NOT NULL,
  status              text NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'processing', 'sent', 'cancelled', 'failed')),
  sent_at             timestamptz,
  wamid               text,
  error               text,
  created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_whatsapp_reminders_status_time
  ON public.whatsapp_reminders (status, scheduled_send_time);

CREATE INDEX IF NOT EXISTS idx_whatsapp_reminders_viewing_id
  ON public.whatsapp_reminders (viewing_id);

ALTER TABLE public.whatsapp_reminders ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE FUNCTION public.claim_and_lock_pending_reminders(batch_limit int DEFAULT 10)
RETURNS SETOF public.whatsapp_reminders
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
  RETURN QUERY
  WITH locked AS (
    SELECT id
    FROM public.whatsapp_reminders
    WHERE status = 'pending'
      AND scheduled_send_time <= now()
    ORDER BY scheduled_send_time ASC
    LIMIT batch_limit
    FOR UPDATE SKIP LOCKED
  )
  UPDATE public.whatsapp_reminders r
  SET status = 'processing'
  FROM locked
  WHERE r.id = locked.id
  RETURNING r.*;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.claim_and_lock_pending_reminders(int) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.claim_and_lock_pending_reminders(int) TO service_role;

COMMIT;
