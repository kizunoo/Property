-- Migration 4: Pipeline outcome columns
-- Idempotent, safe to re-run
BEGIN;

ALTER TABLE public.pipeline_evaluations ADD COLUMN IF NOT EXISTS outcome text DEFAULT 'pending';
ALTER TABLE public.pipeline_evaluations ADD COLUMN IF NOT EXISTS outcome_recorded_at timestamptz;

COMMIT;
