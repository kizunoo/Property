-- Migration 9: Property status and Client Past Purchases track record
-- Idempotent, safe to re-run
BEGIN;

ALTER TABLE public.properties
  ADD COLUMN IF NOT EXISTS status text DEFAULT 'LISTED'
    CHECK (status IN ('LISTED', 'PENDING', 'UNDER OFFER', 'CLOSED')),
  ADD COLUMN IF NOT EXISTS owner_client_id uuid REFERENCES public.clients(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS closed_at timestamptz DEFAULT null;

CREATE INDEX IF NOT EXISTS idx_properties_status ON public.properties(status);
CREATE INDEX IF NOT EXISTS idx_properties_owner_client_id ON public.properties(owner_client_id);

CREATE TABLE IF NOT EXISTS public.client_past_purchases (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id      uuid NOT NULL REFERENCES public.clients(id) ON DELETE CASCADE,
  property_id    uuid REFERENCES public.properties(id) ON DELETE SET NULL,
  property_name  text NOT NULL,
  neighborhood   text NOT NULL,
  property_type  text NOT NULL
    CHECK (property_type IN ('condo','terrace','semi-d','bungalow','serviced_apt')),
  purchase_price numeric NOT NULL,
  purchase_year  integer
    CHECK (purchase_year >= 1990 AND purchase_year <= 2030),
  purpose        text DEFAULT 'own_stay'
    CHECK (purpose IN ('own_stay','investment','holiday_home')),
  notes          text,
  created_at     timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_client_past_purchases_client_id ON public.client_past_purchases(client_id);
CREATE INDEX IF NOT EXISTS idx_client_past_purchases_property_id ON public.client_past_purchases(property_id);
CREATE INDEX IF NOT EXISTS idx_client_past_purchases_neighborhood ON public.client_past_purchases(neighborhood);

COMMIT;
