-- ==============================================================================
-- Security Hardening Rollback Script for Supabase
-- Reverts all grants, revocations, and policies applied by security_hardening.sql.
-- SAFE TO RE-RUN: uses IF EXISTS guards throughout.
-- ==============================================================================

-- 1. Restore write / mutation privileges across all public tables
GRANT INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
  ON ALL TABLES IN SCHEMA public
  TO anon, authenticated;

-- 2. Rollback signals table
DROP POLICY IF EXISTS "Insert signals for service role" ON public.signals;
DROP POLICY IF EXISTS "Read signals for authenticated"   ON public.signals;

CREATE POLICY "Allow all for anon and authenticated"
  ON public.signals FOR ALL
  TO anon, authenticated
  USING (true) WITH CHECK (true);

-- 3. Rollback whatsapp_messages table
DROP POLICY IF EXISTS "Service role full access on whatsapp_messages" ON public.whatsapp_messages;

CREATE POLICY "Allow all for anon and authenticated"
  ON public.whatsapp_messages FOR ALL
  TO anon, authenticated
  USING (true) WITH CHECK (true);

-- 4. Rollback scheduled_viewings table
DROP POLICY IF EXISTS "Service role full access on scheduled_viewings" ON public.scheduled_viewings;

CREATE POLICY "Allow all for anon and authenticated"
  ON public.scheduled_viewings FOR ALL
  TO anon, authenticated
  USING (true) WITH CHECK (true);

-- 5. Rollback column-level revokes on clients table
-- Restore table-level SELECT for anon and authenticated
GRANT SELECT ON public.clients TO anon, authenticated;

-- 6. Rollback client_inquiries table
DROP POLICY IF EXISTS "Service role full access on client_inquiries" ON public.client_inquiries;

CREATE POLICY "Public insert on client_inquiries"
  ON public.client_inquiries FOR INSERT
  TO anon, authenticated
  WITH CHECK (true);

CREATE POLICY "Authenticated read on client_inquiries"
  ON public.client_inquiries FOR SELECT
  TO authenticated
  USING (true);

-- 7. Restore public execute on RPC functions
GRANT EXECUTE ON FUNCTION public.claim_and_lock_pending_reminders(int) TO anon, authenticated, public;
GRANT EXECUTE ON FUNCTION public.claim_and_book_slot_offer(uuid, int, uuid, uuid, timestamptz, uuid, text) TO anon, authenticated, public;

-- 8. Rollback helper functions
DROP FUNCTION IF EXISTS public.check_column_privilege(text, text, text, text);
DROP FUNCTION IF EXISTS public.get_role_table_privileges();
