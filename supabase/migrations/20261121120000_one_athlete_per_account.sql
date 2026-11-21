-- One account links to one athlete. Extra links were making sign-in fail.

with ranked as (
  select
    id,
    row_number() over (
      partition by user_id
      order by (coach_id = user_id) desc, id desc
    ) as n
  from public.athletes
  where user_id is not null
)
update public.athletes as athlete
set user_id = null, updated_at = now()
from ranked
where athlete.id = ranked.id
  and ranked.n > 1;

create unique index if not exists athletes_user_id_key
  on public.athletes (user_id)
  where user_id is not null;
