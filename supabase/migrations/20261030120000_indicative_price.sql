alter table public.properties add column if not exists indicative_price_myr numeric;
alter table public.properties add column if not exists indicative_price_note text;

do $$ begin
  if not exists (select 1 from pg_constraint where conname = 'properties_indicative_price_positive') then
    alter table public.properties
      add constraint properties_indicative_price_positive
      check (indicative_price_myr is null or indicative_price_myr > 0);
  end if;
end $$;

comment on column public.properties.indicative_price_myr is
  'Internal estimate in MYR. Not a supplier quote. Never used in scoring, EV, AI replies or the company portal.';

