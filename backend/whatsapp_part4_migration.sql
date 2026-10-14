-- ==============================================================================
-- WhatsApp Scheduling Migration — Part 4 (Rep Inbox & Compliance)
-- Safe to re-run: uses IF NOT EXISTS / IF EXISTS guards throughout.
-- Run in Supabase SQL Editor → New Query.
-- ==============================================================================

-- ────────────────────────────────────────────────────────────────────────────
-- 1. whatsapp_contact_state — Compliance & Automation State keyed by phone
-- ────────────────────────────────────────────────────────────────────────────
create table if not exists public.whatsapp_contact_state (
    phone_number              text        primary key,
    client_id                 uuid        references public.clients(id) on delete set null,
    opted_out                 boolean     not null default false,
    opted_out_at              timestamptz,
    opt_out_phrase            text,
    automation_paused         boolean     not null default false,
    automation_paused_reason  text,
    snoozed_until             timestamptz,
    last_nudged_at            timestamptz,
    nudge_count               integer     not null default 0,
    created_at                timestamptz not null default now(),
    updated_at                timestamptz not null default now()
);

create index if not exists idx_wa_contact_client on public.whatsapp_contact_state(client_id);
create index if not exists idx_wa_contact_optout on public.whatsapp_contact_state(opted_out);

-- Lock down RLS: Service-role only (no anon or public read/write)
alter table public.whatsapp_contact_state enable row level security;
drop policy if exists "Service role full access on whatsapp_contact_state" on public.whatsapp_contact_state;
create policy "Service role full access on whatsapp_contact_state"
    on public.whatsapp_contact_state for all to service_role
    using (true) with check (true);


-- ────────────────────────────────────────────────────────────────────────────
-- 2. Deduplication & processing status on whatsapp_messages: wamid unique index
-- ────────────────────────────────────────────────────────────────────────────
alter table if exists public.whatsapp_messages 
    add column if not exists wamid text;

alter table if exists public.whatsapp_messages 
    add column if not exists processing_status text default 'received';

alter table if exists public.whatsapp_messages 
    add column if not exists error_code integer;

alter table if exists public.whatsapp_messages 
    add column if not exists error_message text;

-- Backfill wamid from id when id is Meta wamid format
update public.whatsapp_messages
    set wamid = id
    where wamid is null and id like 'wamid.%';

create unique index if not exists idx_whatsapp_messages_wamid 
    on public.whatsapp_messages(wamid) 
    where wamid is not null;


-- ────────────────────────────────────────────────────────────────────────────
-- 3. whatsapp_conversations — Read tracking & Inbox State
-- ────────────────────────────────────────────────────────────────────────────
alter table if exists public.whatsapp_conversations
    add column if not exists last_read_at timestamptz default now();

alter table if exists public.whatsapp_conversations
    add column if not exists unread_count integer default 0;

alter table if exists public.whatsapp_conversations
    add column if not exists status_bucket text default 'cold';
