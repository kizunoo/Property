-- ============================================================
-- Client Portal Phase 1 — Database Migration
-- Run this in the Supabase SQL editor
-- ============================================================

-- 1. Add portal access code column to clients
alter table clients
  add column if not exists portal_access_code text unique;

-- 2. Backfill a random 8-char access code for all existing clients
update clients
  set portal_access_code = upper(substr(md5(random()::text), 1, 8))
  where portal_access_code is null;

-- 3. Client-facing reasoning cache (separate from agent-internal reasoning_cache)
create table if not exists client_facing_reasoning_cache (
  id          uuid primary key default gen_random_uuid(),
  client_id   uuid not null references clients(id) on delete cascade,
  property_id uuid not null references properties(id) on delete cascade,
  reasoning   text not null,
  created_at  timestamptz not null default now(),
  unique (client_id, property_id)
);

-- 4. Verify results
select id, name, portal_access_code from clients limit 10;
