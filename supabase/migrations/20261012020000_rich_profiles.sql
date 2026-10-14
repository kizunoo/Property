-- Migration 2: Rich Profiles (Clients & Properties)
-- Idempotent, safe to re-run
BEGIN;

ALTER TABLE public.clients ADD COLUMN IF NOT EXISTS source text;
ALTER TABLE public.clients ADD COLUMN IF NOT EXISTS secondary_neighborhoods text[] DEFAULT '{}';
ALTER TABLE public.clients ADD COLUMN IF NOT EXISTS move_in_days integer;
ALTER TABLE public.clients ADD COLUMN IF NOT EXISTS financing_status text
  CHECK (financing_status IS NULL OR financing_status IN ('cash', 'mortgage', 'pre_approved', 'unknown'));
ALTER TABLE public.clients ADD COLUMN IF NOT EXISTS min_bedrooms integer;
ALTER TABLE public.clients ADD COLUMN IF NOT EXISTS property_type_preference text
  CHECK (property_type_preference IS NULL OR property_type_preference IN ('condo', 'landed', 'any'));
ALTER TABLE public.clients ADD COLUMN IF NOT EXISTS agent_notes text;
ALTER TABLE public.clients ADD COLUMN IF NOT EXISTS move_in_timeline text;
ALTER TABLE public.clients ADD COLUMN IF NOT EXISTS secondary_neighborhood text;

ALTER TABLE public.properties ADD COLUMN IF NOT EXISTS bedrooms integer;
ALTER TABLE public.properties ADD COLUMN IF NOT EXISTS bathrooms integer;
ALTER TABLE public.properties ADD COLUMN IF NOT EXISTS sqft integer;
ALTER TABLE public.properties ADD COLUMN IF NOT EXISTS property_type text
  CHECK (property_type IS NULL OR property_type IN ('condo', 'landed', 'terrace'));
ALTER TABLE public.properties ADD COLUMN IF NOT EXISTS listing_status text DEFAULT 'LISTED'
  CHECK (listing_status IS NULL OR listing_status IN ('LISTED', 'PENDING', 'UNDER OFFER'));
ALTER TABLE public.properties ADD COLUMN IF NOT EXISTS is_new boolean DEFAULT false;
ALTER TABLE public.properties ADD COLUMN IF NOT EXISTS furnishing text;
ALTER TABLE public.properties ADD COLUMN IF NOT EXISTS tenure text;

COMMIT;
