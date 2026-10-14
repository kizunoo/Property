-- ================================================================
-- Migration: Client Owned Properties & Past Purchase Track Record
-- Run this in your Supabase SQL Editor.
-- ================================================================

-- ── 1. Enhance properties table with status and owner tracking ───

alter table properties
  add column if not exists status text default 'LISTED'
    check (status in ('LISTED', 'PENDING', 'UNDER OFFER', 'CLOSED')),
  add column if not exists owner_client_id uuid references clients(id) on delete set null,
  add column if not exists closed_at timestamptz default null;

create index if not exists idx_properties_status
  on properties (status);

create index if not exists idx_properties_owner_client_id
  on properties (owner_client_id);

-- ── 2. Create client_past_purchases table ───────────────────────

create table if not exists client_past_purchases (
  id             uuid primary key default gen_random_uuid(),
  client_id      uuid not null references clients(id) on delete cascade,
  property_id    uuid references properties(id) on delete set null,
  property_name  text not null,          -- e.g. "Sunway Vivaldi, Block C"
  neighborhood   text not null,          -- e.g. "Mont Kiara"
  property_type  text not null
    check (property_type in ('condo','terrace','semi-d','bungalow','serviced_apt')),
  purchase_price numeric not null,       -- RM transaction price
  purchase_year  integer                 -- e.g. 2022
    check (purchase_year >= 1990 and purchase_year <= 2026),
  purpose        text default 'own_stay' -- 'own_stay' | 'investment' | 'holiday_home'
    check (purpose in ('own_stay','investment','holiday_home')),
  notes          text,                   -- optional notes
  created_at     timestamptz default now()
);

alter table client_past_purchases
  add column if not exists property_id uuid references properties(id) on delete set null;

create index if not exists idx_client_past_purchases_client_id
  on client_past_purchases (client_id);

create index if not exists idx_client_past_purchases_property_id
  on client_past_purchases (property_id);

create index if not exists idx_client_past_purchases_neighborhood
  on client_past_purchases (neighborhood);

-- ── 3. Link existing database properties to clients as closed deals ──

do $$
declare
  -- Clients
  v_benjamin uuid;
  v_chung    uuid;
  v_alvin    uuid;
  v_devi     uuid;
  v_anita    uuid;
  v_nadia    uuid;
  v_bernard  uuid;
  v_stephanie uuid;

  -- Real Properties currently in DB
  v_prop_vivaldi  uuid;
  v_prop_res22    uuid;
  v_prop_suria    uuid;
  v_prop_westside uuid;
  v_prop_desagrn  uuid;
  v_prop_damcty   uuid;
begin
  -- Fetch Clients
  select id into v_benjamin  from clients where name = 'Benjamin Lee' limit 1;
  select id into v_chung     from clients where name = 'Chung Wei Ming' limit 1;
  select id into v_alvin     from clients where name = 'Alvin Teoh' limit 1;
  select id into v_devi      from clients where name = 'Devi Subramaniam' limit 1;
  select id into v_anita     from clients where name = 'Anita Raj' limit 1;
  select id into v_nadia     from clients where name = 'Nadia Kamal' limit 1;
  select id into v_bernard   from clients where name = 'Bernard Heng' limit 1;
  select id into v_stephanie from clients where name = 'Stephanie Yap' limit 1;

  -- Fetch Properties by address
  select id into v_prop_vivaldi  from properties where address ilike '%Sunway Vivaldi%' limit 1;
  select id into v_prop_res22    from properties where address ilike '%Residensi 22%' limit 1;
  select id into v_prop_suria    from properties where address ilike '%Suria KLCC%' limit 1;
  select id into v_prop_westside from properties where address ilike '%Westside III%' limit 1;
  select id into v_prop_desagrn  from properties where address ilike '%Desa Green%' limit 1;
  select id into v_prop_damcty   from properties where address ilike '%Damansara City Residences%' limit 1;

  -- ── 1. Sunway Vivaldi, Block C -> Owned by Benjamin Lee (Closed Oct 2022) ──
  if v_benjamin is not null and v_prop_vivaldi is not null then
    update properties
      set status = 'CLOSED', owner_client_id = v_benjamin, closed_at = '2022-10-15 10:00:00+08'
      where id = v_prop_vivaldi;

    insert into client_past_purchases (client_id, property_id, property_name, neighborhood, property_type, purchase_price, purchase_year, purpose, notes)
    values (v_benjamin, v_prop_vivaldi, 'Sunway Vivaldi, Block C', 'Mont Kiara', 'condo', 3068000, 2022, 'own_stay', 'Primary family residence; renovated')
    on conflict do nothing;

    update pipeline_evaluations set outcome = 'won'
      where client_id = v_benjamin and property_id = v_prop_vivaldi;
  end if;

  -- ── 2. Residensi 22, Unit 18-3 -> Owned by Chung Wei Ming (Closed May 2021) ──
  if v_chung is not null and v_prop_res22 is not null then
    update properties
      set status = 'CLOSED', owner_client_id = v_chung, closed_at = '2021-05-20 14:30:00+08'
      where id = v_prop_res22;

    insert into client_past_purchases (client_id, property_id, property_name, neighborhood, property_type, purchase_price, purchase_year, purpose, notes)
    values (v_chung, v_prop_res22, 'Residensi 22, Unit 18-3', 'Mont Kiara', 'condo', 1727000, 2021, 'own_stay', 'Acquired off-market; verified owner')
    on conflict do nothing;

    update pipeline_evaluations set outcome = 'won'
      where client_id = v_chung and property_id = v_prop_res22;
  end if;

  -- ── 3. Suria KLCC Serviced Suites -> Owned by Alvin Teoh (Closed Jan 2023) ──
  if v_alvin is not null and v_prop_suria is not null then
    update properties
      set status = 'CLOSED', owner_client_id = v_alvin, closed_at = '2023-01-18 11:00:00+08'
      where id = v_prop_suria;

    insert into client_past_purchases (client_id, property_id, property_name, neighborhood, property_type, purchase_price, purchase_year, purpose, notes)
    values (v_alvin, v_prop_suria, 'Suria KLCC Serviced Suites', 'KLCC', 'serviced_apt', 2374000, 2023, 'investment', 'Tenanted to corporate expat; rental yield 5.8%')
    on conflict do nothing;

    update pipeline_evaluations set outcome = 'won'
      where client_id = v_alvin and property_id = v_prop_suria;
  end if;

  -- ── 4. The Westside III, Unit 25-1 -> Owned by Devi Subramaniam (Closed Aug 2023) ──
  if v_devi is not null and v_prop_westside is not null then
    update properties
      set status = 'CLOSED', owner_client_id = v_devi, closed_at = '2023-08-10 16:00:00+08'
      where id = v_prop_westside;

    insert into client_past_purchases (client_id, property_id, property_name, neighborhood, property_type, purchase_price, purchase_year, purpose, notes)
    values (v_devi, v_prop_westside, 'The Westside III, Unit 25-1', 'Desa ParkCity', 'condo', 1650000, 2023, 'own_stay', 'Lakefront park view unit')
    on conflict do nothing;

    update pipeline_evaluations set outcome = 'won'
      where client_id = v_devi and property_id = v_prop_westside;
  end if;

  -- ── 5. Desa Green, Block A-12 -> Owned by Anita Raj (Closed Nov 2020) ──
  if v_anita is not null and v_prop_desagrn is not null then
    update properties
      set status = 'CLOSED', owner_client_id = v_anita, closed_at = '2020-11-05 09:30:00+08'
      where id = v_prop_desagrn;

    insert into client_past_purchases (client_id, property_id, property_name, neighborhood, property_type, purchase_price, purchase_year, purpose, notes)
    values (v_anita, v_prop_desagrn, 'Desa Green, Block A-12', 'Taman Desa', 'condo', 744000, 2020, 'own_stay', 'Starter home purchase')
    on conflict do nothing;

    update pipeline_evaluations set outcome = 'won'
      where client_id = v_anita and property_id = v_prop_desagrn;
  end if;

  -- ── 6. Damansara City Residences, Tower B -> Owned by Nadia Kamal (Closed Mar 2022) ──
  if v_nadia is not null and v_prop_damcty is not null then
    update properties
      set status = 'CLOSED', owner_client_id = v_nadia, closed_at = '2022-03-28 15:15:00+08'
      where id = v_prop_damcty;

    insert into client_past_purchases (client_id, property_id, property_name, neighborhood, property_type, purchase_price, purchase_year, purpose, notes)
    values (v_nadia, v_prop_damcty, 'Damansara City Residences, Tower B', 'Damansara Heights', 'condo', 2800000, 2022, 'investment', 'High floor corner unit; tenanted')
    on conflict do nothing;

    update pipeline_evaluations set outcome = 'won'
      where client_id = v_nadia and property_id = v_prop_damcty;
  end if;

  -- ── Additional portfolio records for key high-tier clients ──
  if v_bernard is not null then
    insert into client_past_purchases (client_id, property_name, neighborhood, property_type, purchase_price, purchase_year, purpose, notes)
    values (v_bernard, 'Bukit Damansara Bungalow', 'Damansara Heights', 'bungalow', 5800000, 2019, 'own_stay', 'Primary luxury residence')
    on conflict do nothing;
  end if;

  if v_stephanie is not null then
    insert into client_past_purchases (client_id, property_name, neighborhood, property_type, purchase_price, purchase_year, purpose, notes)
    values (v_stephanie, 'The Troika, Unit 18-2', 'KLCC', 'condo', 3800000, 2021, 'investment', 'Prime park view unit')
    on conflict do nothing;
  end if;

end $$;
