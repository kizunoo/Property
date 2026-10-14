-- Migration 11: ML Model Tracking Tables
-- Idempotent, safe to re-run
BEGIN;

ALTER TABLE public.pipeline_evaluations ADD COLUMN IF NOT EXISTS ml_probability numeric;

CREATE TABLE IF NOT EXISTS public.model_training_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  trained_at timestamptz NOT NULL DEFAULT now(),
  real_outcome_count integer NOT NULL,
  synthetic_outcome_count integer NOT NULL,
  train_accuracy numeric,
  test_accuracy numeric,
  test_auc numeric,
  notes text
);

COMMIT;
