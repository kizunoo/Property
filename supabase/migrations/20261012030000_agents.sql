-- Migration 3: Agents table and assignments
-- Idempotent, safe to re-run
BEGIN;

CREATE TABLE IF NOT EXISTS public.agents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  initials text NOT NULL,
  role text DEFAULT 'Agent',
  created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.properties
  ADD COLUMN IF NOT EXISTS assigned_agent_id uuid REFERENCES public.agents(id) ON DELETE SET NULL;

ALTER TABLE public.clients
  ADD COLUMN IF NOT EXISTS assigned_agent_id uuid REFERENCES public.agents(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_properties_assigned_agent ON public.properties(assigned_agent_id);
CREATE INDEX IF NOT EXISTS idx_clients_assigned_agent ON public.clients(assigned_agent_id);

COMMIT;
