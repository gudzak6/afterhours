-- The public coach page reads race goals and the week's plan without a coach login.

grant select on table public.training_goals to anon, authenticated;
grant select on table public.scheduled_workouts to anon, authenticated;

drop policy if exists training_goals_public_read on public.training_goals;
create policy training_goals_public_read on public.training_goals
  for select to anon
  using (true);

drop policy if exists scheduled_workouts_public_read on public.scheduled_workouts;
create policy scheduled_workouts_public_read on public.scheduled_workouts
  for select to anon
  using (true);
