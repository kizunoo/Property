-- Backfill script: assign properties and clients round-robin across the 3 seeded agents.
-- Deterministic (ordered by created_at) and idempotent (WHERE assigned_agent_id IS NULL).
-- Run once after agents_migration.sql.

-- --- Assign properties ---------------------------------------------------------
with numbered_properties as (
  select id, row_number() over (order by created_at) as rn
  from properties
  where assigned_agent_id is null
),
agent_list as (
  select id, row_number() over (order by created_at) as rn
  from agents
)
update properties p
set assigned_agent_id = a.id
from numbered_properties np
join agent_list a on a.rn = ((np.rn - 1) % (select count(*) from agents)) + 1
where p.id = np.id;

-- --- Assign clients -----------------------------------------------------------
with numbered_clients as (
  select id, row_number() over (order by created_at) as rn
  from clients
  where assigned_agent_id is null
),
agent_list as (
  select id, row_number() over (order by created_at) as rn
  from agents
)
update clients c
set assigned_agent_id = a.id
from numbered_clients nc
join agent_list a on a.rn = ((nc.rn - 1) % (select count(*) from agents)) + 1
where c.id = nc.id;
