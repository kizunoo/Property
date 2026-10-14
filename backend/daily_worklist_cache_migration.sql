-- Migration: Daily Worklist Cache Table
-- Run in Supabase SQL Editor:
-- https://supabase.com/dashboard/project/tppzkfhhcnmdbwnamgqr/sql/new

create table if not exists daily_worklist_cache (
  id uuid primary key default gen_random_uuid(),
  worklist_date date not null unique,
  entries jsonb not null,
  generated_at timestamptz not null default now()
);

-- Enable RLS and grant read/write permissions
alter table daily_worklist_cache enable row level security;

create policy "Allow public read access to daily_worklist_cache"
  on daily_worklist_cache for select using (true);

create policy "Allow all access to daily_worklist_cache"
  on daily_worklist_cache for all using (true) with check (true);
