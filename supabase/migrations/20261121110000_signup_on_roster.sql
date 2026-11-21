-- A signup gets an athlete row, and the coach roster can read every signup.

create sequence if not exists private.athlete_local_id_seq;

create or replace function private.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  athlete_name text;
begin
  athlete_name := coalesce(
    nullif(new.raw_user_meta_data ->> 'display_name', ''),
    split_part(coalesce(new.email, 'athlete'), '@', 1)
  );
  insert into public.profiles (id, display_name, email, role)
  values (new.id, athlete_name, new.email, 'athlete');
  insert into public.athletes (coach_id, user_id, local_id, display_name)
  values (new.id, new.id, nextval('private.athlete_local_id_seq'), athlete_name);
  update auth.users
  set raw_app_meta_data = coalesce(raw_app_meta_data, '{}'::jsonb) || jsonb_build_object('role', 'athlete')
  where id = new.id;
  return new;
end;
$$;

revoke all on function private.handle_new_user() from public, anon, authenticated;

insert into public.athletes (coach_id, user_id, local_id, display_name)
select profile.id, profile.id, nextval('private.athlete_local_id_seq'), profile.display_name
from public.profiles profile
where not exists (
  select 1 from public.athletes athlete where athlete.user_id = profile.id
);

create or replace function public.roster_athletes()
returns table (
  id bigint,
  local_id bigint,
  display_name text,
  target_time text
)
language sql
stable
security definer
set search_path = ''
as $$
  select athlete.id, athlete.local_id, athlete.display_name, athlete.target_time
  from public.athletes athlete
  order by athlete.display_name;
$$;

revoke all on function public.roster_athletes() from public;
grant execute on function public.roster_athletes() to anon, authenticated;
