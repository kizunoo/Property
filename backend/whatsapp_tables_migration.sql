-- ============================================================
-- WhatsApp Messaging Schema: Conversations & Messages
-- Run in Supabase SQL Editor
-- ============================================================

-- 1. whatsapp_conversations
--    Unique key: (phone_number, agent_id, client_id) so that:
--      - Agent A → ClientX and Agent A → ClientY at the same phone number
--        are two separate threads.
--      - Agent A and Agent B → same client at same number are separate threads.
create table if not exists whatsapp_conversations (
    id                uuid        primary key default gen_random_uuid(),
    phone_number      text        not null,
    client_id         uuid        references clients(id)  on delete set null,
    agent_id          uuid        references agents(id)   on delete set null,
    client_name       text        default 'Contact',
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now(),
    automation_paused boolean     not null default false, -- Set true after human handoff
    constraint uq_whatsapp_conv_phone_agent_client
        unique (phone_number, agent_id, client_id)
);

create index if not exists idx_whatsapp_conv_phone  on whatsapp_conversations(phone_number);
create index if not exists idx_whatsapp_conv_client on whatsapp_conversations(client_id);
create index if not exists idx_whatsapp_conv_agent  on whatsapp_conversations(agent_id);

-- 2. whatsapp_messages
create table if not exists whatsapp_messages (
    id              text        primary key,
    conversation_id uuid        references whatsapp_conversations(id) on delete cascade,
    to_number       text        not null,
    client_id       uuid        references clients(id)  on delete set null,
    agent_id        uuid        references agents(id)   on delete set null,
    client_name     text        default 'Contact',
    sender          text        not null,   -- 'agent' | 'client' | 'system'
    text            text        not null,
    status          text        not null default 'sent',
    timestamp       timestamptz not null default now(),
    raw_payload     jsonb
);

create index if not exists idx_whatsapp_msg_conv  on whatsapp_messages(conversation_id);
create index if not exists idx_whatsapp_msg_agent on whatsapp_messages(agent_id);
create index if not exists idx_whatsapp_msg_to    on whatsapp_messages(to_number);
create index if not exists idx_whatsapp_msg_time  on whatsapp_messages(timestamp desc);

-- ── Enable Row Level Security (RLS) ──────────────────────────
-- Strictly enable RLS with no public policies, locking down access to service-role keys.
alter table whatsapp_conversations enable row level security;
alter table whatsapp_messages enable row level security;
