-- =============================================================================
-- WhatsApp Reminders Migration (Part 2)
-- =============================================================================
-- Run this migration in Supabase SQL Editor (Dashboard -> SQL Editor -> New Query).
-- It can be run in two clearly marked parts:
-- Part A: Table schema, indexes, and scheduled_viewings confirmation columns.
-- Part B: Row Level Security (RLS) policies and atomic claim RPC function.
-- =============================================================================

-- =============================================================================
-- PART A: Columns and Tables
-- =============================================================================

-- 1. Add confirmation tracking columns to scheduled_viewings
alter table public.scheduled_viewings
  add column if not exists client_confirmed_at timestamptz;

alter table public.scheduled_viewings
  add column if not exists confirmation_status text default 'unconfirmed';

-- 2. Create whatsapp_reminders table
create table if not exists public.whatsapp_reminders (
  id                  uuid primary key default gen_random_uuid(),
  viewing_id          uuid not null references public.scheduled_viewings(id) on delete cascade,
  client_id           uuid references public.clients(id) on delete set null,
  agent_id            uuid references public.agents(id) on delete set null,
  phone_number        text not null,
  reminder_type       text not null check (reminder_type in ('24h', '2h')),
  scheduled_send_time timestamptz not null,
  status              text not null default 'pending'
                        check (status in ('pending', 'processing', 'sent', 'cancelled', 'failed')),
  sent_at             timestamptz,
  wamid               text,
  error               text,
  created_at          timestamptz not null default now()
);

-- 3. Indexes for fast queue processing and viewing lookups
create index if not exists idx_whatsapp_reminders_status_time
  on public.whatsapp_reminders (status, scheduled_send_time);

create index if not exists idx_whatsapp_reminders_viewing_id
  on public.whatsapp_reminders (viewing_id);


-- =============================================================================
-- PART B: Security (RLS) and Atomic Claim RPC
-- =============================================================================

-- 1. Enable Row Level Security (Service Role only, no public access)
alter table public.whatsapp_reminders enable row level security;

-- Revoke any direct public/anon access
revoke all on public.whatsapp_reminders from public, anon, authenticated;

-- Allow service_role full access (Supabase service role automatically bypasses RLS,
-- but this policy makes permissions explicit):
drop policy if exists "Service role full access on whatsapp_reminders" on public.whatsapp_reminders;
create policy "Service role full access on whatsapp_reminders"
  on public.whatsapp_reminders
  for all
  to service_role
  using (true)
  with check (true);

-- 2. Transactional Atomic Claim RPC
-- Uses FOR UPDATE SKIP LOCKED to guarantee that concurrent workers never double-claim
-- or double-send the same due reminder.
create or replace function public.claim_due_whatsapp_reminders(p_limit int default 10)
returns setof public.whatsapp_reminders
language plpgsql
security definer
set search_path = public
as $$
begin
  return query
  update public.whatsapp_reminders
  set status = 'processing'
  where id in (
    select id
    from public.whatsapp_reminders
    where status = 'pending'
      and scheduled_send_time <= now()
    order by scheduled_send_time asc
    for update skip locked
    limit p_limit
  )
  returning *;
end;
$$;

-- Secure the RPC function: Service role only
revoke execute on function public.claim_due_whatsapp_reminders(int) from public, anon, authenticated;
grant execute on function public.claim_due_whatsapp_reminders(int) to service_role;
