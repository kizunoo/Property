-- Backfill rich profile data for existing seed rows.
-- Safe to re-run: only updates rows where new columns are still null.

-- ─── Property specs (derived from value bands) ────────────────────────────────
update properties set
  bedrooms      = case
    when property_value >= 5000000 then 4 + (floor(property_value / 1000000)::int % 2)
    when property_value >= 2500000 then 3 + (floor(property_value / 500000)::int % 2)
    when property_value >= 1200000 then 2 + (floor(property_value / 400000)::int % 2)
    else 2
  end,
  bathrooms     = case
    when property_value >= 5000000 then 4
    when property_value >= 2500000 then 3
    when property_value >= 1200000 then 2
    else 2
  end,
  sqft          = case
    when property_value >= 5000000 then 3200 + (floor(property_value / 200000)::int % 8) * 150
    when property_value >= 2500000 then 1800 + (floor(property_value / 150000)::int % 10) * 100
    when property_value >= 1200000 then 1100 + (floor(property_value / 100000)::int % 12) * 80
    else 850 + (floor(property_value / 50000)::int % 10) * 60
  end,
  property_type = case
    when neighborhood in ('Mont Kiara', 'KLCC', 'Damansara Heights') and property_value >= 2000000 then 'condo'
    when property_value >= 4500000 then 'landed'
    when property_value >= 1500000 then 'terrace'
    else 'condo'
  end,
  listing_status = 'LISTED',
  is_new         = property_value >= 3000000 and neighborhood in ('KLCC', 'Desa ParkCity')
where bedrooms is null;

-- ─── Client profiles ──────────────────────────────────────────────────────────
update clients set
  source = case (abs(hashtext(name)) % 5)
    when 0 then 'referral'
    when 1 then 'portal'
    when 2 then 'walk_in'
    when 3 then 'referral'
    else 'agent_network'
  end,
  secondary_neighborhoods = case preferred_neighborhood
    when 'Mont Kiara' then array['Bangsar', 'Damansara Heights']
    when 'Bangsar' then array['Mont Kiara', 'Damansara Heights']
    when 'KLCC' then array['Bangsar', 'Mont Kiara']
    when 'Damansara Heights' then array['Bangsar', 'Mont Kiara']
    when 'Desa ParkCity' then array['Mont Kiara', 'Bandar Sri Damansara']
    when 'Taman Desa' then array['Bangsar', 'Bandar Sri Damansara']
    when 'Bandar Sri Damansara' then array['Desa ParkCity', 'Mont Kiara']
    else array[]::text[]
  end,
  move_in_days = 30 + (abs(hashtext(name)) % 150),
  financing_status = case (abs(hashtext(name)) % 4)
    when 0 then 'cash'
    when 1 then 'pre_approved'
    when 2 then 'mortgage'
    else 'unknown'
  end,
  min_bedrooms = case
    when stated_budget >= 5000000 then 4
    when stated_budget >= 2500000 then 3
    when stated_budget >= 1200000 then 2
    else 2
  end,
  property_type_preference = case (abs(hashtext(name)) % 3)
    when 0 then 'condo'
    when 1 then 'landed'
    else 'any'
  end
where source is null;
