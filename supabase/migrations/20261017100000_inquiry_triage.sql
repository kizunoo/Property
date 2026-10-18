-- Inquiry triage: AI/rules priority labels on company inquiries (rep-side only, never shown to the company).
ALTER TABLE public.client_inquiries
  ADD COLUMN IF NOT EXISTS triage_status   text    NOT NULL DEFAULT 'rules'
      CHECK (triage_status IN ('rules','ai','failed')),
  ADD COLUMN IF NOT EXISTS triage_priority text
      CHECK (triage_priority IN ('urgent','high','normal','low')),
  ADD COLUMN IF NOT EXISTS triage_category text
      CHECK (triage_category IN ('pricing_quote','demo_request','technical_question',
                                 'complaint_issue','general','unclear')),
  ADD COLUMN IF NOT EXISTS triage_summary  text,
  ADD COLUMN IF NOT EXISTS triage_reasons  jsonb   NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS triage_alerted  boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS triaged_at      timestamptz;

CREATE INDEX IF NOT EXISTS client_inquiries_triage_idx
  ON public.client_inquiries (triage_priority, created_at DESC);
-- NOTE for Antigravity: confirm with scripts/db_verify.py that anon/authenticated cannot read
-- these columns (client_inquiries is service_role-only via RLS). Do NOT grant them to anyone.
