create table if not exists public.telemetrie (
    horodatage        timestamptz      primary key,
    statut_occupation boolean          not null,
    poids             double precision not null check (poids between 0 and 300),
    temperature       double precision not null check (temperature between -20 and 80)
);

comment on table public.telemetrie is 'Mesures envoyées par la chaise connectée simulée';

revoke all on table public.telemetrie from anon, authenticated;
grant select, insert on table public.telemetrie to anon;

alter table public.telemetrie enable row level security;

drop policy if exists "lecture_publique" on public.telemetrie;
create policy "lecture_publique"
    on public.telemetrie
    for select
    to anon
    using (true);

drop policy if exists "insertion_capteur" on public.telemetrie;
create policy "insertion_capteur"
    on public.telemetrie
    for insert
    to anon
    with check (
        horodatage between now() - interval '24 hours'
                       and now() + interval '1 minute'
    );

create or replace function public.telemetrie_historique(p_heures integer default 6)
returns table (
    horodatage          timestamptz,
    taux_occupation     double precision,
    poids_moyen         double precision,
    temperature_moyenne double precision
)
language sql
stable
security invoker
set search_path = ''
as $$
    with parametres as (
        select least(greatest(p_heures, 1), 168) as heures
    )
    select
        date_bin(
            make_interval(secs => p.heures * 12),
            t.horodatage,
            timestamptz '2000-01-01 00:00:00+00'
        ) as horodatage,
        avg(case when t.statut_occupation then 1.0 else 0.0 end)::double precision,
        coalesce(avg(t.poids) filter (where t.statut_occupation), 0)::double precision,
        avg(t.temperature)::double precision
    from public.telemetrie t
    cross join parametres p
    where t.horodatage >= now() - make_interval(hours => p.heures)
    group by 1
    order by 1;
$$;

revoke all on function public.telemetrie_historique(integer) from public, anon, authenticated;
grant execute on function public.telemetrie_historique(integer) to anon;

notify pgrst, 'reload schema';
