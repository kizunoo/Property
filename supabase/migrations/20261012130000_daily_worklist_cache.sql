-- Migration 13: Daily Worklist Cache Table
-- Idempotent, safe to re-run
BEGIN;

CREATE TABLE IF NOT EXISTS public.daily_worklist_cache (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  worklist_date date NOT NULL UNIQUE,
  entries jsonb NOT NULL,
  generated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.daily_worklist_cache ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Allow public read access to daily_worklist_cache" ON public.daily_worklist_cache;
CREATE POLICY "Allow public read access to daily_worklist_cache"
  ON public.daily_worklist_cache FOR SELECT USING (true);

DROP POLICY IF EXISTS "Allow all access to daily_worklist_cache" ON public.daily_worklist_cache;
CREATE POLICY "Allow all access to daily_worklist_cache"
  ON public.daily_worklist_cache FOR ALL USING (true) WITH CHECK (true);

COMMIT;
