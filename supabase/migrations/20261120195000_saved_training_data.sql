-- Account-owned training data. Login identity stays in auth.users.
-- Sign-up creates an athlete. That athlete owns rows keyed by the local roster id.

create schema if not exists private;

create table public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  role text not null default 'athlete' check (role in ('coach', 'athlete')),
  display_name text not null,
  email text,
  timezone text not null default 'America/New_York',
  email_notifications_enabled boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.athletes (
  id bigint generated always as identity primary key,
  coach_id uuid not null references public.profiles (id) on delete cascade,
  user_id uuid references public.profiles (id) on delete set null,
  local_id bigint not null,
  display_name text not null,
  target_time text,
  coach_notes text,
  running_experience text,
  typical_weekly_mileage double precision,
  preferred_training_days jsonb not null default '[]'::jsonb,
  pace_zones jsonb not null default '[]'::jsonb,
  heart_rate_zones jsonb not null default '[]'::jsonb,
  max_heart_rate_bpm double precision,
  intake jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint athletes_coach_local_key unique (coach_id, local_id)
);

create index athletes_user_id_idx on public.athletes (user_id);

create table public.training_goals (
  id bigint generated always as identity primary key,
  athlete_id bigint not null unique references public.athletes (id) on delete cascade,
  primary_race_goal text,
  goal_race_date date,
  notes text,
  updated_at timestamptz not null default now()
);

create table public.races (
  id bigint generated always as identity primary key,
  athlete_id bigint not null references public.athletes (id) on delete cascade,
  name text not null,
  race_date date,
  distance_label text,
  distance_meters double precision,
  goal_time text,
  result_time text,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index races_athlete_id_idx on public.races (athlete_id);

create table public.athlete_thresholds (
  id bigint generated always as identity primary key,
  athlete_id bigint not null references public.athletes (id) on delete cascade,
  name text not null,
  pace_seconds_per_mile double precision,
  heart_rate_bpm double precision,
  source text not null default 'user',
  updated_at timestamptz not null default now(),
  constraint athlete_thresholds_name_key unique (athlete_id, name)
);

create table public.scheduled_workouts (
  id bigint generated always as identity primary key,
  athlete_id bigint not null references public.athletes (id) on delete cascade,
  source_key text,
  scheduled_date date not null,
  title text not null,
  details text,
  workout_type text,
  distance_miles double precision,
  warmup text,
  cooldown text,
  repetitions integer,
  rep_distance_miles double precision,
  recovery_seconds double precision,
  target_pace text,
  intensity text,
  coach_notes text,
  original_prescription jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint scheduled_workouts_source_key unique (athlete_id, source_key)
);

create index scheduled_workouts_athlete_date_idx
  on public.scheduled_workouts (athlete_id, scheduled_date);

create table public.plan_revisions (
  id bigint generated always as identity primary key,
  scheduled_workout_id bigint not null references public.scheduled_workouts (id) on delete cascade,
  prescription jsonb not null,
  created_at timestamptz not null default now()
);

create index plan_revisions_workout_id_idx
  on public.plan_revisions (scheduled_workout_id);

alter table public.profiles enable row level security;
alter table public.athletes enable row level security;
alter table public.training_goals enable row level security;
alter table public.races enable row level security;
alter table public.athlete_thresholds enable row level security;
alter table public.scheduled_workouts enable row level security;
alter table public.plan_revisions enable row level security;

create or replace function private.owned_athlete_ids()
returns setof bigint
language sql
stable
security definer
set search_path = ''
as $$
  select athlete.id
  from public.athletes athlete
  where athlete.coach_id = (select auth.uid())
     or athlete.user_id = (select auth.uid())
$$;

revoke all on function private.owned_athlete_ids() from public, anon;
grant usage on schema private to authenticated;
grant execute on function private.owned_athlete_ids() to authenticated;

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

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function private.handle_new_user();

create policy profiles_select on public.profiles
  for select to authenticated
  using (id = (select auth.uid()));

create policy profiles_insert on public.profiles
  for insert to authenticated
  with check (id = (select auth.uid()));

create policy profiles_update on public.profiles
  for update to authenticated
  using (id = (select auth.uid()))
  with check (id = (select auth.uid()));

create policy athletes_select on public.athletes
  for select to authenticated
  using (
    coach_id = (select auth.uid())
    or user_id = (select auth.uid())
  );

create policy athletes_insert on public.athletes
  for insert to authenticated
  with check (
    coach_id = (select auth.uid())
    and (user_id is null or user_id = (select auth.uid()))
  );

create policy athletes_update on public.athletes
  for update to authenticated
  using (coach_id = (select auth.uid()) or user_id = (select auth.uid()))
  with check (
    coach_id = (select auth.uid())
    and (user_id is null or user_id = (select auth.uid()))
  );

create policy athletes_delete on public.athletes
  for delete to authenticated
  using (coach_id = (select auth.uid()));

create policy training_goals_all on public.training_goals
  for all to authenticated
  using (athlete_id in (select private.owned_athlete_ids()))
  with check (athlete_id in (select private.owned_athlete_ids()));

create policy races_all on public.races
  for all to authenticated
  using (athlete_id in (select private.owned_athlete_ids()))
  with check (athlete_id in (select private.owned_athlete_ids()));

create policy athlete_thresholds_all on public.athlete_thresholds
  for all to authenticated
  using (athlete_id in (select private.owned_athlete_ids()))
  with check (athlete_id in (select private.owned_athlete_ids()));

create policy scheduled_workouts_all on public.scheduled_workouts
  for all to authenticated
  using (athlete_id in (select private.owned_athlete_ids()))
  with check (athlete_id in (select private.owned_athlete_ids()));

create policy plan_revisions_all on public.plan_revisions
  for all to authenticated
  using (
    exists (
      select 1
      from public.scheduled_workouts workout
      where workout.id = plan_revisions.scheduled_workout_id
        and workout.athlete_id in (select private.owned_athlete_ids())
    )
  )
  with check (
    exists (
      select 1
      from public.scheduled_workouts workout
      where workout.id = scheduled_workout_id
        and workout.athlete_id in (select private.owned_athlete_ids())
    )
  );

revoke all on table
  public.profiles,
  public.athletes,
  public.training_goals,
  public.races,
  public.athlete_thresholds,
  public.scheduled_workouts,
  public.plan_revisions
from anon, public;

grant select, insert, update on table public.profiles to authenticated;
grant select, insert, update, delete on table
  public.athletes,
  public.training_goals,
  public.races,
  public.athlete_thresholds,
  public.scheduled_workouts,
  public.plan_revisions
to authenticated;
