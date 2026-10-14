-- ============================================================
-- Rich Profiles Migration — PIPELINE.EV
-- Run this in the Supabase SQL Editor:
-- https://supabase.com/dashboard/project/tppzkfhhcnmdbwnamgqr/sql/new
-- ============================================================

-- ── Properties: real listing specs ──────────────────────────

alter table properties add column if not exists bedrooms       integer;
alter table properties add column if not exists bathrooms      integer;
alter table properties add column if not exists sqft           integer;
alter table properties add column if not exists property_type  text
  check (property_type in ('condo','terrace','semi-d','bungalow','serviced_apt'));
alter table properties add column if not exists furnishing     text
  check (furnishing in ('fully','partially','unfurnished'));
alter table properties add column if not exists tenure         text
  check (tenure in ('freehold','leasehold'));

-- ── Clients: rich buyer requirements ────────────────────────

alter table clients add column if not exists financing_status        text
  check (financing_status in ('cash','pre-approved','in-progress','unspecified'));
alter table clients add column if not exists move_in_timeline        text
  check (move_in_timeline in ('< 3 months','3-6 months','6-12 months','flexible'));
alter table clients add column if not exists property_type_preference text
  check (property_type_preference in ('condo','terrace','semi-d','bungalow','serviced_apt','any'));
alter table clients add column if not exists secondary_neighborhood   text;
alter table clients add column if not exists agent_notes             text;

-- ── Indexes for neighborhood lookups ────────────────────────

create index if not exists idx_clients_secondary_nbhd
  on clients (secondary_neighborhood);

create index if not exists idx_properties_type
  on properties (property_type);
