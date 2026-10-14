-- Step 1 — Database schema update for Real ML Model
-- Run this in the Supabase SQL Editor:
-- https://supabase.com/dashboard/project/tppzkfhhcnmdbwnamgqr/sql/new

alter table pipeline_evaluations add column if not exists ml_probability numeric;

create table if not exists model_training_runs (
  id uuid primary key default gen_random_uuid(),
  trained_at timestamptz not null default now(),
  real_outcome_count integer not null,
  synthetic_outcome_count integer not null,
  train_accuracy numeric,
  test_accuracy numeric,
  test_auc numeric,
  notes text
);
