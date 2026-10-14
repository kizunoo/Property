-- Phase 2: Staged Relationship Pipeline & "Mark as Sent" Close-the-Loop Migration

-- 1. Add relationship_stage column to clients table
alter table clients add column if not exists relationship_stage text default 'new'
  check (relationship_stage in ('new', 'contacted', 'viewing', 'negotiation', 'closed_won', 'closed_lost'));

-- 2. Add sent_at timestamp to invite_drafts table
alter table invite_drafts add column if not exists sent_at timestamptz;

-- 3. Backfill existing clients based on what's already true about them, so this doesn't
-- reset everyone to 'new' and lose the real state that already exists in the data.
update clients c
set relationship_stage = case
  when exists (select 1 from pipeline_evaluations pe where pe.client_id = c.id and pe.outcome = 'won') then 'closed_won'
  when exists (select 1 from pipeline_evaluations pe where pe.client_id = c.id and pe.outcome = 'lost') then 'closed_lost'
  when exists (select 1 from scheduled_viewings sv where sv.client_id = c.id) then 'viewing'
  when exists (select 1 from invite_drafts idr where idr.client_id = c.id) then 'contacted'
  else 'new'
end
where relationship_stage = 'new'; -- only backfill rows still at the default, don't overwrite manual changes made after this migration
