-- Backfill script: populate bedrooms, bathrooms, and sqft for properties based on property_value.
-- Heuristics:
--   sqft: property_value / (2000 to 3000), rounded to nearest 50
--   bedrooms: 2-3 (<RM3M), 3-4 (RM3M-6M), 4-5 (>RM6M)
--   bathrooms: bedrooms minus 0 or 1
-- Deterministic using hash of property id.

update properties
set
  sqft = greatest(
    600,
    round(
      (property_value / (2000.0 + (('x' || substr(md5(id::text || 'sqft'), 1, 6))::bit(24)::bigint % 1000))) / 50.0
    ) * 50
  ),
  bedrooms = case
    when property_value < 3000000 then 2 + (('x' || substr(md5(id::text || 'bed'), 1, 6))::bit(24)::bigint % 2)
    when property_value <= 6000000 then 3 + (('x' || substr(md5(id::text || 'bed'), 1, 6))::bit(24)::bigint % 2)
    else 4 + (('x' || substr(md5(id::text || 'bed'), 1, 6))::bit(24)::bigint % 2)
  end,
  bathrooms = greatest(
    1,
    (
      case
        when property_value < 3000000 then 2 + (('x' || substr(md5(id::text || 'bed'), 1, 6))::bit(24)::bigint % 2)
        when property_value <= 6000000 then 3 + (('x' || substr(md5(id::text || 'bed'), 1, 6))::bit(24)::bigint % 2)
        else 4 + (('x' || substr(md5(id::text || 'bed'), 1, 6))::bit(24)::bigint % 2)
      end
    ) - (('x' || substr(md5(id::text || 'bath'), 1, 6))::bit(24)::bigint % 2)
  )
where bedrooms is null or bathrooms is null or sqft is null;

-- Verification query:
-- SELECT count(*) FROM properties WHERE bedrooms IS NULL OR bathrooms IS NULL OR sqft IS NULL;
