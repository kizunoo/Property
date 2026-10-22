-- Inquiry resolution + company history. New columns only: the existing `status` column (and any CHECK on
-- it) is left untouched. An inquiry is "open" while resolved_at IS NULL. Rep-side only, never shown to companies.
ALTER TABLE public.client_inquiries
  ADD COLUMN IF NOT EXISTS resolved_at     timestamptz,
  ADD COLUMN IF NOT EXISTS resolved_by     text,
  ADD COLUMN IF NOT EXISTS resolution_note text;

CREATE INDEX IF NOT EXISTS client_inquiries_client_created_idx
  ON public.client_inquiries (client_id, created_at DESC);
CREATE INDEX IF NOT EXISTS client_inquiries_unresolved_idx
  ON public.client_inquiries (client_id) WHERE resolved_at IS NULL;
-- Do NOT grant these columns to anon/authenticated (client_inquiries is service_role-only via RLS).
