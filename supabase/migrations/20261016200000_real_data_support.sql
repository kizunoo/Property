-- Real-data support: mark seed vs real rows, add robot-catalog columns to properties and clients.
-- Existing rows become 'seed' automatically (DEFAULT), so they can be purged safely.

ALTER TABLE public.properties
  ADD COLUMN IF NOT EXISTS data_source  text  NOT NULL DEFAULT 'seed',
  ADD COLUMN IF NOT EXISTS sku_code     text,
  ADD COLUMN IF NOT EXISTS manufacturer text,
  ADD COLUMN IF NOT EXISTS specs        jsonb NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE public.clients
  ADD COLUMN IF NOT EXISTS data_source text NOT NULL DEFAULT 'seed',
  ADD COLUMN IF NOT EXISTS website     text,
  ADD COLUMN IF NOT EXISTS source_url  text,
  ADD COLUMN IF NOT EXISTS phone       text;

-- Relax legacy consumer fields and provide defaults for B2B company rows
ALTER TABLE public.clients
  ALTER COLUMN stated_budget SET DEFAULT 0,
  ALTER COLUMN preferred_neighborhood SET DEFAULT '';

DO $$
BEGIN
  ALTER TABLE public.clients ALTER COLUMN stated_budget DROP NOT NULL;
  ALTER TABLE public.clients ALTER COLUMN preferred_neighborhood DROP NOT NULL;
EXCEPTION WHEN OTHERS THEN
  NULL;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'properties_data_source_chk'
  ) THEN
    ALTER TABLE public.properties
      ADD CONSTRAINT properties_data_source_chk CHECK (data_source IN ('seed','real'));
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'clients_data_source_chk'
  ) THEN
    ALTER TABLE public.clients
      ADD CONSTRAINT clients_data_source_chk CHECK (data_source IN ('seed','real'));
  END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS properties_sku_code_uq
  ON public.properties (sku_code) WHERE sku_code IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS clients_real_name_uq
  ON public.clients (lower(name)) WHERE data_source = 'real';

-- Grant SELECT on properties.sku_code, manufacturer, specs, and clients.website, source_url, phone
-- to anon and authenticated roles so rep console can read them via PostgREST
GRANT SELECT (data_source, sku_code, manufacturer, specs) ON public.properties TO anon, authenticated;
GRANT SELECT (data_source, website, source_url, phone) ON public.clients TO anon, authenticated;
