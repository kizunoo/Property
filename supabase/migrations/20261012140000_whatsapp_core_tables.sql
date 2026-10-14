-- Migration 14: WhatsApp Core Tables (Conversations and Messages)
-- Idempotent, safe to re-run
BEGIN;

CREATE TABLE IF NOT EXISTS public.whatsapp_conversations (
    id                uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    phone_number      text        NOT NULL,
    client_id         uuid        REFERENCES public.clients(id)  ON DELETE SET NULL,
    agent_id          uuid        REFERENCES public.agents(id)   ON DELETE SET NULL,
    client_name       text        DEFAULT 'Contact',
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    automation_paused boolean     NOT NULL DEFAULT false,
    CONSTRAINT uq_whatsapp_conv_phone_agent_client
        UNIQUE (phone_number, agent_id, client_id)
);

CREATE INDEX IF NOT EXISTS idx_whatsapp_conv_phone  ON public.whatsapp_conversations(phone_number);
CREATE INDEX IF NOT EXISTS idx_whatsapp_conv_client ON public.whatsapp_conversations(client_id);
CREATE INDEX IF NOT EXISTS idx_whatsapp_conv_agent  ON public.whatsapp_conversations(agent_id);

CREATE TABLE IF NOT EXISTS public.whatsapp_messages (
    id              text        PRIMARY KEY,
    conversation_id uuid        REFERENCES public.whatsapp_conversations(id) ON DELETE CASCADE,
    to_number       text        NOT NULL,
    client_id       uuid        REFERENCES public.clients(id)  ON DELETE SET NULL,
    agent_id        uuid        REFERENCES public.agents(id)   ON DELETE SET NULL,
    client_name     text        DEFAULT 'Contact',
    sender          text        NOT NULL,
    text            text        NOT NULL,
    status          text        NOT NULL DEFAULT 'sent',
    timestamp       timestamptz NOT NULL DEFAULT now(),
    raw_payload     jsonb
);

CREATE INDEX IF NOT EXISTS idx_whatsapp_msg_conv  ON public.whatsapp_messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_whatsapp_msg_agent ON public.whatsapp_messages(agent_id);
CREATE INDEX IF NOT EXISTS idx_whatsapp_msg_to    ON public.whatsapp_messages(to_number);
CREATE INDEX IF NOT EXISTS idx_whatsapp_msg_time  ON public.whatsapp_messages(timestamp DESC);

ALTER TABLE public.whatsapp_conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.whatsapp_messages ENABLE ROW LEVEL SECURITY;

COMMIT;
