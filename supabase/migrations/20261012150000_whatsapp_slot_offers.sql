-- Migration 15: WhatsApp Slot Offers and Transactional Booking RPC
-- Idempotent, safe to re-run
BEGIN;

ALTER TABLE public.scheduled_viewings ADD COLUMN IF NOT EXISTS source text DEFAULT 'manual';
ALTER TABLE public.scheduled_viewings ADD COLUMN IF NOT EXISTS agent_id uuid REFERENCES public.agents(id) ON DELETE SET NULL;

CREATE TABLE IF NOT EXISTS public.whatsapp_slot_offers (
    id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id           uuid        NOT NULL REFERENCES public.clients(id) ON DELETE CASCADE,
    property_id         uuid        NOT NULL REFERENCES public.properties(id) ON DELETE CASCADE,
    agent_id            uuid        REFERENCES public.agents(id) ON DELETE SET NULL,
    slots               jsonb       NOT NULL,
    status              text        NOT NULL DEFAULT 'open',
    created_at          timestamptz NOT NULL DEFAULT now(),
    expires_at          timestamptz NOT NULL DEFAULT (now() + interval '72 hours'),
    pitch_wamid         text,
    pitch_message_id    text,
    phone_number        text,
    booked_slot_index   int,
    booked_at           timestamptz,
    reoffer_count       int         NOT NULL DEFAULT 0,
    CONSTRAINT chk_slot_offer_status CHECK (status IN ('open', 'booked', 'expired', 'declined', 'cancelled'))
);

CREATE INDEX IF NOT EXISTS idx_whatsapp_slot_offers_client ON public.whatsapp_slot_offers(client_id, status);
CREATE INDEX IF NOT EXISTS idx_whatsapp_slot_offers_agent  ON public.whatsapp_slot_offers(agent_id);
CREATE INDEX IF NOT EXISTS idx_whatsapp_slot_offers_phone  ON public.whatsapp_slot_offers(phone_number, status);
CREATE INDEX IF NOT EXISTS idx_whatsapp_slot_offers_wamid  ON public.whatsapp_slot_offers(pitch_wamid);
CREATE INDEX IF NOT EXISTS idx_whatsapp_slot_offers_concurrency ON public.whatsapp_slot_offers(id, status);

CREATE UNIQUE INDEX IF NOT EXISTS idx_scheduled_viewings_agent_slot
  ON public.scheduled_viewings (agent_id, scheduled_at)
  WHERE status = 'upcoming' AND agent_id IS NOT NULL;

ALTER TABLE public.whatsapp_slot_offers ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE FUNCTION public.claim_and_book_slot_offer(
    p_offer_id      uuid,
    p_slot_index    int,
    p_client_id     uuid,
    p_property_id   uuid,
    p_scheduled_at  timestamptz,
    p_agent_id      uuid    DEFAULT NULL,
    p_wamid         text    DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_offer public.whatsapp_slot_offers%ROWTYPE;
    v_viewing_id uuid;
    v_conflict_count int;
BEGIN
    SELECT * INTO v_offer
    FROM public.whatsapp_slot_offers
    WHERE id = p_offer_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'error', 'Offer not found');
    END IF;

    IF v_offer.status = 'booked' THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Offer has already been booked',
            'already_booked', true
        );
    END IF;

    IF v_offer.status != 'open' THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Offer is no longer available (' || v_offer.status || ')'
        );
    END IF;

    IF v_offer.expires_at < now() THEN
        UPDATE public.whatsapp_slot_offers
        SET status = 'expired'
        WHERE id = p_offer_id;

        RETURN jsonb_build_object('success', false, 'error', 'Offer expired');
    END IF;

    IF p_agent_id IS NOT NULL THEN
        SELECT COUNT(*) INTO v_conflict_count
        FROM public.scheduled_viewings
        WHERE agent_id = p_agent_id
          AND scheduled_at = p_scheduled_at
          AND status = 'upcoming';

        IF v_conflict_count > 0 THEN
            RETURN jsonb_build_object(
                'success', false,
                'error', 'Agent has an overlapping upcoming viewing at this slot',
                'agent_conflict', true
            );
        END IF;
    END IF;

    INSERT INTO public.scheduled_viewings (
        client_id,
        property_id,
        scheduled_at,
        status,
        agent_id,
        source
    )
    VALUES (
        p_client_id,
        p_property_id,
        p_scheduled_at,
        'upcoming',
        p_agent_id,
        'whatsapp'
    )
    RETURNING id INTO v_viewing_id;

    UPDATE public.whatsapp_slot_offers
    SET
        status            = 'booked',
        booked_slot_index = p_slot_index,
        booked_at         = now()
    WHERE id = p_offer_id;

    RETURN jsonb_build_object(
        'success',          true,
        'viewing_id',       v_viewing_id,
        'offer_id',         p_offer_id,
        'scheduled_at',     p_scheduled_at,
        'booked_slot_index', p_slot_index
    );
END;
$$;

REVOKE EXECUTE ON FUNCTION public.claim_and_book_slot_offer(uuid, int, uuid, uuid, timestamptz, uuid, text) FROM public, anon;
GRANT EXECUTE ON FUNCTION public.claim_and_book_slot_offer(uuid, int, uuid, uuid, timestamptz, uuid, text) TO service_role;

COMMIT;
