-- Rich client & property profiles for PIPELINE.EV
-- Run in Supabase SQL Editor after base schema migrations.

-- ─── Client profile columns ───────────────────────────────────────────────────
alter table clients add column if not exists source text;
alter table clients add column if not exists secondary_neighborhoods text[] default '{}';
alter table clients add column if not exists move_in_days integer;
alter table clients add column if not exists financing_status text
  check (financing_status is null or financing_status in ('cash', 'mortgage', 'pre_approved', 'unknown'));
alter table clients add column if not exists min_bedrooms integer;
alter table clients add column if not exists property_type_preference text
  check (property_type_preference is null or property_type_preference in ('condo', 'landed', 'any'));
alter table clients add column if not exists agent_notes text;

-- ─── Property listing columns ─────────────────────────────────────────────────
alter table properties add column if not exists bedrooms integer;
alter table properties add column if not exists bathrooms integer;
alter table properties add column if not exists sqft integer;
alter table properties add column if not exists property_type text
  check (property_type is null or property_type in ('condo', 'landed', 'terrace'));
alter table properties add column if not exists listing_status text default 'LISTED'
  check (listing_status is null or listing_status in ('LISTED', 'PENDING', 'UNDER OFFER'));
alter table properties add column if not exists is_new boolean default false;
