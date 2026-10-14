-- ==============================================================================
-- PART 1: TABLES, COLUMNS, INDEXES & ROW LEVEL SECURITY
-- Run this block first in Supabase SQL Editor
-- ==============================================================================

-- 1. Ensure scheduled_viewings has source marker and direct agent_id columns
alter table scheduled_viewings add column if not exists source text default 'manual';
alter table scheduled_viewings add column if not exists agent_id uuid references agents(id) on delete set null;

-- 2. Create whatsapp_slot_offers table
create table if not exists whatsapp_slot_offers (
    id                  uuid        primary key default gen_random_uuid(),
    client_id           uuid        not null references clients(id) on delete cascade,
    property_id         uuid        not null references properties(id) on delete cascade,
    agent_id            uuid        references agents(id) on delete set null,
    slots               jsonb       not null, -- Array of slot objects: [{"index": 1, "slot_iso": "...", "label": "Thu 10 Oct, 2:00 PM"}, ...]
    status              text        not null default 'open', -- 'open' | 'booked' | 'expired' | 'declined' | 'cancelled'
    created_at          timestamptz not null default now(),
    expires_at          timestamptz not null default (now() + interval '72 hours'),
    pitch_wamid         text,       -- WhatsApp message id (wamid) of the pitch
    pitch_message_id    text,       -- Internal message ID of the pitch
    phone_number        text,       -- Recipient phone number for fast indexing / fallback
    booked_slot_index   int,        -- Which slot was chosen when booked (1, 2, 3...)
    booked_at           timestamptz, -- Exact timestamp when the booking was confirmed
    reoffer_count       int         not null default 0, -- Capped at 3 re-offers
    constraint chk_slot_offer_status check (status in ('open', 'booked', 'expired', 'declined', 'cancelled'))
);

create index if not exists idx_whatsapp_slot_offers_client on whatsapp_slot_offers(client_id, status);
create index if not exists idx_whatsapp_slot_offers_agent  on whatsapp_slot_offers(agent_id);
create index if not exists idx_whatsapp_slot_offers_phone  on whatsapp_slot_offers(phone_number, status);
create index if not exists idx_whatsapp_slot_offers_wamid  on whatsapp_slot_offers(pitch_wamid);
create index if not exists idx_whatsapp_slot_offers_concurrency on whatsapp_slot_offers(id, status);

-- DB-level guard against double-booking the same agent for overlapping upcoming times
create unique index if not exists idx_scheduled_viewings_agent_slot
  on scheduled_viewings (agent_id, scheduled_at)
  where status = 'upcoming' and agent_id is not null;

-- 3. Strictly enable Row Level Security (RLS) with no public policies
alter table whatsapp_slot_offers enable row level security;


-- ==============================================================================
-- PART 2: TRANSACTIONAL RPC FUNCTION & PERMISSIONS
-- Run this block second in Supabase SQL Editor
-- ==============================================================================

-- Drop legacy 5-argument version if exists
drop function if exists claim_and_book_slot_offer(uuid, int, uuid, uuid, timestamptz);
drop function if exists claim_and_book_slot_offer(uuid, int);

create or replace function claim_and_book_slot_offer(
    p_offer_id uuid,
    p_slot_index int
) returns jsonb language plpgsql security definer
set search_path = public as $$
declare
    v_offer whatsapp_slot_offers%rowtype;
    v_slot_iso text;
    v_slot_label text;
    v_scheduled_at timestamptz;
    v_viewing_id uuid;
    v_elem jsonb;
begin
    -- 1. Lock and read offer row: must be open and unexpired
    select * into v_offer
    from whatsapp_slot_offers
    where id = p_offer_id
      and status = 'open'
      and expires_at > now()
    for update;

    if not found then
        return jsonb_build_object('success', false, 'error', 'Offer not available or expired');
    end if;

    -- 2. Extract selected slot from offer jsonb array
    for v_elem in select * from jsonb_array_elements(v_offer.slots)
    loop
        if (v_elem->>'index')::int = p_slot_index then
            v_slot_iso := v_elem->>'slot_iso';
            v_slot_label := v_elem->>'label';
            exit;
        end if;
    end loop;

    if v_slot_iso is null then
        return jsonb_build_object('success', false, 'error', 'Slot index not found in offer');
    end if;

    v_scheduled_at := v_slot_iso::timestamptz;

    -- 3. Verify slot time is strictly in the future
    if v_scheduled_at <= now() then
        return jsonb_build_object('success', false, 'error', 'Slot time is in the past');
    end if;

    -- 4. Re-check agent schedule conflicts inside transaction (45 min buffer)
    if v_offer.agent_id is not null then
        if exists (
            select 1
            from scheduled_viewings sv
            left join clients c on c.id = sv.client_id
            where sv.status = 'upcoming'
              and (sv.agent_id = v_offer.agent_id or (sv.agent_id is null and c.assigned_agent_id = v_offer.agent_id))
              and sv.scheduled_at >= (v_scheduled_at - interval '45 minutes')
              and sv.scheduled_at <= (v_scheduled_at + interval '45 minutes')
        ) then
            -- Conflict detected: leave offer open (do NOT book)
            return jsonb_build_object(
                'success', false,
                'conflict', true,
                'error', 'Agent has a conflicting viewing within 45 minute buffer'
            );
        end if;
    end if;

    -- 5. Atomic state transition: mark offer booked
    update whatsapp_slot_offers
    set status = 'booked',
        booked_slot_index = p_slot_index,
        booked_at = now()
    where id = p_offer_id;

    -- 6. Insert viewing with real columns, status='upcoming' and source='whatsapp_auto'
    insert into scheduled_viewings (
        client_id,
        property_id,
        agent_id,
        scheduled_at,
        status,
        source
    )
    values (
        v_offer.client_id,
        v_offer.property_id,
        v_offer.agent_id,
        v_scheduled_at,
        'upcoming',
        'whatsapp_auto'
    )
    returning id into v_viewing_id;

    return jsonb_build_object(
        'success', true,
        'viewing_id', v_viewing_id,
        'offer_id', v_offer.id,
        'client_id', v_offer.client_id,
        'property_id', v_offer.property_id,
        'agent_id', v_offer.agent_id,
        'scheduled_at', v_slot_iso,
        'slot_label', coalesce(v_slot_label, 'the selected time'),
        'status', 'booked'
    );
exception when others then
    raise exception 'Booking transaction failed: %', sqlerrm;
end;
$$;

-- Security hardening: strictly revoke execution from public/anon/authenticated and grant to service_role
revoke execute on function claim_and_book_slot_offer(uuid, int) from public, anon, authenticated;
grant execute on function claim_and_book_slot_offer(uuid, int) to service_role;
