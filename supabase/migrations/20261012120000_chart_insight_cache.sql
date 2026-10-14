-- Migration 12: Chart Insight Cache Table
-- Idempotent, safe to re-run
BEGIN;

CREATE TABLE IF NOT EXISTS public.chart_insight_cache (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  cache_key text UNIQUE NOT NULL,
  insight text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.chart_insight_cache ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Allow all on chart_insight_cache" ON public.chart_insight_cache;
CREATE POLICY "Allow all on chart_insight_cache"
  ON public.chart_insight_cache
  FOR ALL
  TO anon, authenticated
  USING (true)
  WITH CHECK (true);

COMMIT;
