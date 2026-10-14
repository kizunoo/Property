-- ============================================================
-- Client Portal Phase 2 — Additional Schema
-- Run in Supabase SQL Editor
-- ============================================================

-- 1. Add estimated_annual_savings to properties
--    This is a pre-computed per-robot-category figure (not LLM-invented).
--    Used to compute payback_months = (property_value / estimated_annual_savings) * 12
alter table properties
  add column if not exists estimated_annual_savings numeric;

-- 2. Backfill sensible savings estimates per environment/category
--    These are conservative industry estimates for the Malaysian market.
--    Logistics/Warehousing AMRs: ~RM 80K/yr labour offset (2 FTE)
--    Manufacturing welding cobots: ~RM 60K/yr (1 skilled FTE + rework reduction)
--    Cold-chain runners: ~RM 55K/yr (temperature compliance + 1 FTE)
--    Outdoor patrol units: ~RM 40K/yr (security FTE replacement)
--    General/default: ~RM 45K/yr
update properties
  set estimated_annual_savings = case
    when lower(neighborhood) like '%logistics%' or lower(neighborhood) like '%warehousing%'   then 80000
    when lower(neighborhood) like '%manufactur%' and lower(address) like '%weld%'              then 60000
    when lower(neighborhood) like '%manufactur%'                                               then 65000
    when lower(neighborhood) like '%cold%' or lower(address) like '%cold%'
      or lower(address) like '%thermo%'                                                        then 55000
    when lower(neighborhood) like '%outdoor%' or lower(address) like '%patrol%'
      or lower(address) like '%scout%' or lower(address) like '%security%'                     then 40000
    else 45000
  end
where estimated_annual_savings is null;

-- 3. Create client_inquiries table
--    Lightweight "ask a question" messages from clients, visible to agents.
create table if not exists client_inquiries (
  id          uuid primary key default gen_random_uuid(),
  client_id   uuid not null references clients(id) on delete cascade,
  property_id uuid not null references properties(id) on delete cascade,
  message     text not null,
  status      text not null default 'open',   -- 'open' | 'replied' | 'closed'
  agent_reply text,
  created_at  timestamptz not null default now(),
  replied_at  timestamptz
);

create index if not exists client_inquiries_client_id_idx on client_inquiries(client_id);
create index if not exists client_inquiries_property_id_idx on client_inquiries(property_id);

-- 4. Verify
select id, address, neighborhood, property_value, estimated_annual_savings,
       round((property_value / estimated_annual_savings) * 12) as payback_months
from properties
order by payback_months
limit 15;
