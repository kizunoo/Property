-- supabase/migrations/20261016100000_portal_b2b_poc.sql
ALTER TABLE public.client_inquiries
  ADD COLUMN IF NOT EXISTS roi_scenario jsonb;

ALTER TABLE public.clients
  ADD COLUMN IF NOT EXISTS facility_profile jsonb NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE public.scheduled_viewings
  ADD COLUMN IF NOT EXISTS poc_criteria jsonb NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS poc_feedback jsonb,
  ADD COLUMN IF NOT EXISTS poc_outcome text
    CHECK (poc_outcome IN ('success','partial','failed'));
