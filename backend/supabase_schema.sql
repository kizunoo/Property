-- PIPELINE.EV Supabase schema (run in Supabase SQL Editor)

create table if not exists properties (
  id uuid primary key default gen_random_uuid(),
  address text not null,
  neighborhood text not null,
  property_value numeric not null,
  image_url text
);

alter table properties add column if not exists image_url text;

create table if not exists clients (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  stated_budget numeric not null,
  preferred_neighborhood text not null,
  past_viewings integer not null default 0
);

create table if not exists pipeline_evaluations (
  id uuid primary key default gen_random_uuid(),
  client_id uuid not null references clients(id) on delete cascade,
  property_id uuid not null references properties(id) on delete cascade,
  ai_probability numeric not null,
  expected_value numeric not null,
  segment_tier text not null check (segment_tier in ('TIER_1', 'TIER_2', 'TIER_3')),
  unique (client_id, property_id)
);

-- Sample KL-area seed data
insert into properties (address, neighborhood, property_value) values
  ('Unit 12A, Kiara 163', 'Mont Kiara', 1850000),
  ('8 Jalan Bangsar Utama', 'Bangsar', 2400000),
  ('Penthouse 3, The Troika', 'KLCC', 5200000);

-- Signals table and client tier tracking
create table if not exists signals (
  id uuid primary key default gen_random_uuid(),
  type text not null, -- 'tier_upgrade' | 'first_vip' | 'viewing_auto_cancelled'
  client_id uuid references clients(id) on delete cascade,
  property_id uuid references properties(id) on delete set null,
  message text not null,
  dismissed boolean not null default false,
  created_at timestamptz not null default now()
);

alter table clients add column if not exists last_known_tier text;

