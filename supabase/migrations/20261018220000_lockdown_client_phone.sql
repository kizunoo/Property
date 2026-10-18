-- Lock down clients.phone (and clients.email if present) from anon and authenticated
REVOKE SELECT (phone) ON public.clients FROM anon, authenticated;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'clients' AND column_name = 'email'
  ) THEN
    EXECUTE 'REVOKE SELECT (email) ON public.clients FROM anon, authenticated';
  END IF;
END $$;
