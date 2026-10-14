-- --- Agents table --------------------------------------------------------------
create table if not exists agents (
  id         uuid primary key default gen_random_uuid(),
  name       text not null,
  initials   text not null,
  role       text default 'Agent',
  created_at timestamptz not null default now()
);

-- Seed three agents (idempotent — skip if already present)
insert into agents (name, initials, role) values
  ('R. Delgado', 'RD', 'Senior Agent'),
  ('S. Yusof',   'SY', 'Agent'),
  ('A. Rahman',  'AR', 'Agent')
on conflict do nothing;

-- --- Add assigned_agent_id FK to properties ------------------------------------
alter table properties
  add column if not exists assigned_agent_id uuid references agents(id);

-- --- Add assigned_agent_id FK to clients --------------------------------------
alter table clients
  add column if not exists assigned_agent_id uuid references agents(id);
