-- Sign-up creates an athlete. Correct accounts created while the default was coach.

alter table public.profiles alter column role set default 'athlete';

update public.profiles
set role = 'athlete', updated_at = now()
where role = 'coach';

update auth.users
set raw_app_meta_data = coalesce(raw_app_meta_data, '{}'::jsonb) || jsonb_build_object('role', 'athlete')
where coalesce(raw_app_meta_data ->> 'role', 'coach') = 'coach';

create or replace function private.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.profiles (id, display_name, email, role)
  values (
    new.id,
    coalesce(nullif(new.raw_user_meta_data ->> 'display_name', ''), split_part(coalesce(new.email, 'athlete'), '@', 1)),
    new.email,
    'athlete'
  );
  update auth.users
  set raw_app_meta_data = coalesce(raw_app_meta_data, '{}'::jsonb) || jsonb_build_object('role', 'athlete')
  where id = new.id;
  return new;
end;
$$;

revoke all on function private.handle_new_user() from public, anon, authenticated;
