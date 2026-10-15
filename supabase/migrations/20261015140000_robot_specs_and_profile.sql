-- Migration 20261015140000: Robot Specifications and Client Profile Columns
-- Idempotent, safe to re-run

BEGIN;

ALTER TABLE public.properties
  ADD COLUMN IF NOT EXISTS sku text,
  ADD COLUMN IF NOT EXISTS manufacturer text,
  ADD COLUMN IF NOT EXISTS category text,
  ADD COLUMN IF NOT EXISTS specs jsonb NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS lead_time_weeks integer,
  ADD COLUMN IF NOT EXISTS stock_status text,
  ADD COLUMN IF NOT EXISTS spec_sheet_url text,
  ADD COLUMN IF NOT EXISTS image_url text,
  ADD COLUMN IF NOT EXISTS currency text NOT NULL DEFAULT 'MYR';

ALTER TABLE public.clients
  ADD COLUMN IF NOT EXISTS industry text,
  ADD COLUMN IF NOT EXISTS facility_type text,
  ADD COLUMN IF NOT EXISTS facility_size_sqm integer,
  ADD COLUMN IF NOT EXISTS use_case text,
  ADD COLUMN IF NOT EXISTS purchase_timeline text,
  ADD COLUMN IF NOT EXISTS existing_automation text,
  ADD COLUMN IF NOT EXISTS profile_updated_at timestamptz;

-- Backfill specs from legacy seed mapping (bedrooms -> payload_kg, bathrooms -> sensors, sqft -> range)
-- Only where specs is empty
UPDATE public.properties
SET specs = jsonb_build_object(
  'payload_kg', bedrooms,
  'sensors', bathrooms,
  'range', sqft
)
WHERE specs = '{}'::jsonb
  AND (bedrooms IS NOT NULL OR bathrooms IS NOT NULL OR sqft IS NOT NULL);

COMMIT;
