-- Chart insight cache table
-- Run this in Supabase SQL Editor (Dashboard → SQL Editor → New Query)

create table if not exists chart_insight_cache (
  id uuid primary key default gen_random_uuid(),
  cache_key text unique not null,
  insight text not null,
  created_at timestamptz not null default now()
);

alter table chart_insight_cache enable row level security;

drop policy if exists "Allow all on chart_insight_cache" on chart_insight_cache;
create policy "Allow all on chart_insight_cache"
  on chart_insight_cache
  for all
  to anon, authenticated
  using (true)
  with check (true);
