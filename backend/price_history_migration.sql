-- Run this in the Supabase SQL Editor before using the price simulation feature.

create table if not exists property_price_history (
  id          uuid primary key default gen_random_uuid(),
  property_id uuid not null references properties(id) on delete cascade,
  old_value   numeric not null,
  new_value   numeric not null,
  change_pct  numeric not null,
  changed_at  timestamptz not null default now()
);

-- Index for fast per-property history lookups (used by the graph)
create index if not exists idx_property_price_history_property_id
  on property_price_history(property_id, changed_at asc);

-- Denormalized convenience columns on properties so cards can show a
-- "recently moved" badge without a join per card.
alter table properties
  add column if not exists last_price_change_at  timestamptz,
  add column if not exists last_price_change_pct numeric;
