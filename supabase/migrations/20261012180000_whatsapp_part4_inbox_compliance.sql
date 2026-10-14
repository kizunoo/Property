-- Migration 18: WhatsApp Part 4 Inbox & Compliance
-- Idempotent, safe to re-run
BEGIN;

CREATE TABLE IF NOT EXISTS public.whatsapp_contact_state (
    phone_number              text        PRIMARY KEY,
    client_id                 uuid        REFERENCES public.clients(id) ON DELETE SET NULL,
    opted_out                 boolean     NOT NULL DEFAULT false,
    opted_out_at              timestamptz,
    opt_out_phrase            text,
    automation_paused         boolean     NOT NULL DEFAULT false,
    automation_paused_reason  text,
    snoozed_until             timestamptz,
    last_nudged_at            timestamptz,
    nudge_count               integer     NOT NULL DEFAULT 0,
    created_at                timestamptz NOT NULL DEFAULT now(),
    updated_at                timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_wa_contact_client ON public.whatsapp_contact_state(client_id);
CREATE INDEX IF NOT EXISTS idx_wa_contact_optout ON public.whatsapp_contact_state(opted_out);

ALTER TABLE public.whatsapp_contact_state ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Service role full access on whatsapp_contact_state" ON public.whatsapp_contact_state;
CREATE POLICY "Service role full access on whatsapp_contact_state"
    ON public.whatsapp_contact_state FOR ALL TO service_role
    USING (true) WITH CHECK (true);

ALTER TABLE IF EXISTS public.whatsapp_messages 
    ADD COLUMN IF NOT EXISTS wamid text;

ALTER TABLE IF EXISTS public.whatsapp_messages 
    ADD COLUMN IF NOT EXISTS processing_status text DEFAULT 'received';

ALTER TABLE IF EXISTS public.whatsapp_messages 
    ADD COLUMN IF NOT EXISTS error_code integer;

ALTER TABLE IF EXISTS public.whatsapp_messages 
    ADD COLUMN IF NOT EXISTS error_message text;

UPDATE public.whatsapp_messages
SET wamid = id
WHERE wamid IS NULL AND id LIKE 'wamid.%';

CREATE UNIQUE INDEX IF NOT EXISTS idx_whatsapp_messages_wamid
    ON public.whatsapp_messages (wamid)
    WHERE wamid IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_whatsapp_messages_proc_status
    ON public.whatsapp_messages (processing_status);

ALTER TABLE IF EXISTS public.whatsapp_conversations
    ADD COLUMN IF NOT EXISTS status_bucket text DEFAULT 'needs_attention';

ALTER TABLE IF EXISTS public.whatsapp_conversations
    ADD COLUMN IF NOT EXISTS needs_rep_attention boolean DEFAULT false;

CREATE INDEX IF NOT EXISTS idx_whatsapp_conv_status_bucket
    ON public.whatsapp_conversations (status_bucket);

COMMIT;
