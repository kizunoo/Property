-- ─────────────────────────────────────────────────────────────────────────────
-- scheduled_viewings table
-- Run this in Supabase SQL Editor (Dashboard → SQL Editor → New Query)
-- ─────────────────────────────────────────────────────────────────────────────

create table if not exists scheduled_viewings (
  id            uuid primary key default gen_random_uuid(),
  client_id     uuid not null references clients(id) on delete cascade,
  property_id   uuid not null references properties(id) on delete cascade,
  scheduled_at  timestamptz not null,
  status        text not null default 'upcoming'
                  check (status in ('upcoming', 'completed', 'cancelled')),
  cancellation_reason text,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

alter table scheduled_viewings add column if not exists cancellation_reason text;


-- Index for fast lookup by status (Kanban board queries)
create index if not exists idx_scheduled_viewings_status
  on scheduled_viewings (status);

-- Index for client-level lookup
create index if not exists idx_scheduled_viewings_client_id
  on scheduled_viewings (client_id);

-- Auto-update updated_at on row change
create or replace function set_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

drop trigger if exists trg_scheduled_viewings_updated_at on scheduled_viewings;
create trigger trg_scheduled_viewings_updated_at
  before update on scheduled_viewings
  for each row execute function set_updated_at();

-- Enable Row Level Security (or disable for simple dev setup without auth)
alter table scheduled_viewings enable row level security;

-- Permissive policy for anon + authenticated users
drop policy if exists "Allow all for authenticated" on scheduled_viewings;
drop policy if exists "Allow all for anon and authenticated" on scheduled_viewings;

create policy "Allow all for anon and authenticated"
  on scheduled_viewings
  for all
  to anon, authenticated
  using (true)
  with check (true);

-- Alternatively, to disable RLS completely:
-- alter table scheduled_viewings disable row level security;

