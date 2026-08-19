-- Run this in the Supabase SQL Editor:
-- https://supabase.com/dashboard/project/tppzkfhhcnmdbwnamgqr/sql/new

alter table pipeline_evaluations add column if not exists outcome text default 'pending';
-- outcome: 'pending' | 'won' | 'lost'
alter table pipeline_evaluations add column if not exists outcome_recorded_at timestamptz;
