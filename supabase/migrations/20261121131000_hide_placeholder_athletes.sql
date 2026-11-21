-- Signup rows named Athlete are not roster members. They were listed twice.

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
  where athlete.display_name <> 'Athlete'
    and athlete.display_name <> 'New Garmin Athlete'
  order by athlete.display_name;
$$;

revoke all on function public.roster_athletes() from public;
grant execute on function public.roster_athletes() to anon, authenticated;
