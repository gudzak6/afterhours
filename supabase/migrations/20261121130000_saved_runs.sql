-- Saved runs for the public coach page. The coaching database keeps the roster;
-- these rows are the activity summaries the local coach database already stored.

create table public.activities (
  id bigint generated always as identity primary key,
  athlete_id bigint not null references public.athletes (id) on delete cascade,
  garmin_activity_id bigint not null,
  name text,
  start_time_local text,
  distance_meters double precision,
  duration_seconds double precision,
  average_speed_mps double precision,
  location_name text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint activities_athlete_garmin_key unique (athlete_id, garmin_activity_id)
);

create index activities_athlete_start_idx
  on public.activities (athlete_id, start_time_local);

alter table public.activities enable row level security;

create policy activities_public_read on public.activities
  for select
  to anon, authenticated
  using (true);

create policy activities_insert on public.activities
  for insert
  to authenticated
  with check (athlete_id in (select private.owned_athlete_ids()));

create policy activities_update on public.activities
  for update
  to authenticated
  using (athlete_id in (select private.owned_athlete_ids()))
  with check (athlete_id in (select private.owned_athlete_ids()));

create policy activities_delete on public.activities
  for delete
  to authenticated
  using (athlete_id in (select private.owned_athlete_ids()));

grant select on table public.activities to anon, authenticated;
grant insert, update, delete on table public.activities to authenticated;

insert into public.activities (
  athlete_id,
  garmin_activity_id,
  name,
  start_time_local,
  distance_meters,
  duration_seconds,
  average_speed_mps,
  location_name
)
select
  athlete.id,
  src.garmin_activity_id,
  src.name,
  src.start_time_local,
  src.distance_meters,
  src.duration_seconds,
  src.average_speed_mps,
  src.location_name
from (
  values
    (4::bigint, 24074456269::bigint, 'New York Running'::text, '2026-08-22 08:35:17'::text, 32711.0::double precision, 8581.658203125::double precision, 3.8120000362396245::double precision, 'New York'::text),
    (4, 24096441188, 'New York Running', '2026-08-24 07:11:27', 17761.55078125, 4725.49609375, 3.759000062942505, 'New York'),
    (4, 24102662361, 'New York Running', '2026-08-24 16:25:56', 11267.66015625, 3751.3759765625, 3.003999948501587, 'New York'),
    (4, 24109982363, 'New York Running', '2026-08-25 07:48:35', 16154.26953125, 4890.13818359375, 3.302999973297119, 'New York'),
    (4, 24115891220, 'New York Running', '2026-08-25 16:22:14', 9660.6103515625, 3071.4619140625, 3.1449999809265137, 'New York'),
    (4, 24122650235, 'New York Running', '2026-08-26 06:49:59', 7157.81005859375, 2351.464111328125, 3.0439999103546143, 'New York'),
    (4, 24130426743, 'New York Running', '2026-08-26 18:38:30', 18123.119140625, 4670.287109375, 3.88100004196167, 'New York'),
    (4, 24148351213, 'East Brunswick Running', '2026-08-28 07:53:18', 16108.330078125, 4944.13623046875, 3.2579998970031743, 'East Brunswick'),
    (4, 24151982375, 'East Brunswick Running', '2026-08-28 14:25:47', 6845.66015625, 2038.7080078125, 3.3580000400543213, 'East Brunswick'),
    (4, 24185923344, 'Indoor Cycling', '2026-08-31 11:38:24', 0.0, 2853.639892578125, 0.0, null),
    (4, 24189239990, 'Indoor Cycling', '2026-08-31 16:53:22', 0.0, 2701.824951171875, 0.0, null),
    (4, 24202517685, 'Indoor Cycling', '2026-09-01 14:57:42', 0.0, 7314.962890625, 0.0, null),
    (4, 24208748928, 'Indoor Cycling', '2026-09-02 06:10:21', 0.0, 4441.5810546875, 0.0, null),
    (4, 24215596145, 'Indoor Cycling', '2026-09-02 15:41:01', 0.0, 3052.616943359375, 0.0, null),
    (4, 24289892119, 'Indoor Cycling', '2026-09-08 16:56:53', 0.0, 3670.4560546875, 0.0, null),
    (4, 24314674614, 'Indoor Cycling', '2026-09-10 16:12:54', 0.0, 3610.416015625, 0.0, null),
    (4, 24326286443, 'Indoor Cycling', '2026-09-11 16:30:28', 0.0, 4505.09814453125, 0.0, null),
    (4, 24335873014, 'Treadmill Running', '2026-09-12 11:02:46', 7258.14013671875, 2297.3759765625, 3.1589999198913574, null),
    (4, 24336633243, 'Indoor Cycling', '2026-09-12 11:47:06', 0.0, 3616.93798828125, 0.0, null),
    (4, 24347147622, 'New York Running', '2026-09-13 09:30:37', 8215.51953125, 2530.948974609375, 3.246000051498413, 'New York'),
    (4, 24351305055, 'Indoor Cycling', '2026-09-13 16:28:38', 0.0, 3723.9208984375, 0.0, null),
    (4, 24356590283, 'New York Running', '2026-09-14 06:48:31', 11278.650390625, 3393.658935546875, 3.3229999542236333, 'New York'),
    (4, 24364119012, 'Treadmill Running', '2026-09-14 19:16:11', 6598.31005859375, 2100.320068359375, 3.1419999599456787, null),
    (4, 24370126873, 'New York Running', '2026-09-15 07:30:27', 7174.6201171875, 2226.5791015625, 3.221999883651734, 'New York'),
    (4, 24376518688, 'New York Running', '2026-09-15 16:39:41', 12073.01953125, 3760.992919921875, 3.2100000381469727, 'New York'),
    (4, 24415510795, 'Copenhagen Running', '2026-09-19 08:44:35', 6960.47998046875, 2172.299072265625, 3.2039999961853027, 'Copenhagen'),
    (4, 24431094143, 'Copenhagen Running', '2026-09-20 10:03:54', 21323.759765625, 5281.69189453125, 4.0370001792907715, 'Copenhagen'),
    (4, 24458071531, 'New York Running', '2026-09-22 10:49:55', 17719.810546875, 4541.8359375, 3.9010000228881836, 'New York'),
    (4, 24462586888, 'New York Running', '2026-09-22 17:36:38', 9694.759765625, 3575.1689453125, 2.711999893188476, 'New York'),
    (4, 24476219213, 'New York Running', '2026-09-23 18:38:05', 16802.580078125, 4846.865234375, 3.467000007629395, 'New York'),
    (4, 24485212264, 'New York Running', '2026-09-24 12:43:15', 16130.1201171875, 4851.26708984375, 3.325000047683716, 'New York'),
    (4, 24492603124, 'New York Running', '2026-09-25 07:27:38', 3711.75, 1177.095947265625, 3.1530001163482666, 'New York'),
    (4, 24493192640, 'New York Running', '2026-09-25 07:59:14', 13475.1796875, 3001.2958984375, 4.489999771118164, 'New York'),
    (4, 24493433100, 'New York Running', '2026-09-25 08:52:50', 3238.929931640625, 1096.9580078125, 2.953000068664551, 'New York'),
    (4, 24507124460, 'New York Running', '2026-09-26 08:44:12', 32207.490234375, 8262.251953125, 3.898000001907349, 'New York'),
    (4, 24527537809, 'New York Running', '2026-09-28 06:32:31', 9148.8798828125, 2778.73193359375, 3.2920000553131104, 'New York'),
    (4, 24534230847, 'New York Running', '2026-09-28 16:36:26', 14517.330078125, 3269.8310546875, 4.440000057220459, 'New York'),
    (4, 24534779354, 'Warm up/cooldown', '2026-09-28 18:47:39', 3218.688, 960.0, 3.3527999999999993, null),
    (4, 24540881387, 'Treadmill Running', '2026-09-29 07:27:51', 12874.75, 4022.14599609375, 3.200999975204468, null),
    (4, 24547075462, 'Treadmill Running', '2026-09-29 16:31:24', 8046.72021484375, 2473.3720703125, 3.253000020980835, null),
    (4, 24552677686, 'New York Running', '2026-09-30 06:09:51', 9667.1396484375, 2955.134033203125, 3.2709999084472656, 'New York'),
    (4, 24560811309, 'New York Running', '2026-09-30 18:58:07', 10000.2001953125, 2138.33203125, 4.677000045776367, 'New York'),
    (4, 24561196221, 'New York Running', '2026-09-30 19:36:56', 4963.2001953125, 1704.009033203125, 2.9130001068115234, 'New York'),
    (4, 24561210801, 'Warm up', '2026-09-30 20:36:18', 2896.8192000000004, 960.0, 3.01752, null),
    (4, 24571455720, 'New York Running', '2026-10-01 15:07:47', 14500.2001953125, 4344.291015625, 3.338000059127808, 'New York'),
    (4, 24582789090, 'Treadmill Running', '2026-10-02 16:15:53', 8766.8603515625, 2701.47900390625, 3.244999885559082, null),
    (4, 24589514272, 'New York Running', '2026-10-03 05:54:49', 32204.0703125, 7814.85986328125, 4.120999813079834, 'New York'),
    (4, 24608612497, 'New York Running', '2026-10-04 18:00:24', 16118.26953125, 5294.71923828125, 3.0439999103546143, 'New York'),
    (4, 24620336663, 'New York Running', '2026-10-05 17:46:10', 19321.689453125, 5528.27978515625, 3.4949998855590825, 'New York'),
    (4, 24626496721, 'New York Running', '2026-10-06 07:35:49', 9673.490234375, 3029.126953125, 3.193000078201294, 'New York'),
    (4, 24633280698, 'New York Running', '2026-10-06 17:12:55', 20944.69921875, 5706.85009765625, 3.6700000762939453, 'New York'),
    (4, 24638506250, 'New York Running', '2026-10-07 06:10:52', 12438.75, 4088.278076171875, 3.0429999828338627, 'New York'),
    (4, 24645112774, 'Treadmill Running', '2026-10-07 16:56:41', 6759.240234375, 2166.748046875, 3.119999885559082, null),
    (4, 24656976875, 'New York Running', '2026-10-08 11:57:34', 8069.4501953125, 2452.261962890625, 3.2909998893737793, 'New York'),
    (4, 24656495683, 'New York Running', '2026-10-08 15:46:50', 16106.7998046875, 4786.63818359375, 3.365000009536743, 'New York'),
    (4, 24667087546, 'Treadmill Running', '2026-10-09 16:10:32', 9656.0595703125, 2935.735107421875, 3.2890000343322754, null),
    (4, 24673896083, 'New York Running', '2026-10-10 06:26:57', 34663.48046875, 8091.19287109375, 4.283999919891357, 'New York'),
    (4, 24674228542, 'New York Running', '2026-10-10 08:55:53', 3227.169921875, 996.864013671875, 3.2369999885559086, 'New York'),
    (4, 24701517217, 'New York Running', '2026-10-12 15:08:55', 6613.35009765625, 1980.5999755859375, 3.3389999866485596, 'New York'),
    (4, 24702660507, 'New York Running', '2026-10-12 17:14:19', 16150.4697265625, 4750.39990234375, 3.4000000953674316, 'New York'),
    (4, 24707786944, 'New York Running', '2026-10-13 06:13:50', 16406.69921875, 5054.5009765625, 3.246000051498413, 'New York'),
    (4, 24714250422, 'Treadmill Running', '2026-10-13 16:19:15', 7724.85009765625, 2427.87109375, 3.181999921798706, null),
    (4, 24723343058, 'New York Running', '2026-10-14 11:28:12', 8065.0400390625, 2447.424072265625, 3.2950000762939458, 'New York'),
    (4, 24728129298, 'New York Running', '2026-10-14 19:04:29', 20396.109375, 5488.47314453125, 3.7160000801086426, 'New York'),
    (4, 24728195794, 'Run', '2026-10-14 20:59:50', 3218.688, 960.0, 3.3527999999999993, null),
    (4, 24732224998, 'New York Running', '2026-10-15 06:02:33', 16261.2001953125, 5057.77880859375, 3.214999914169312, 'New York'),
    (4, 24738465911, 'Treadmill Running', '2026-10-15 16:15:25', 8046.72021484375, 2496.426025390625, 3.223000049591065, null),
    (4, 24749382612, 'New York Running', '2026-10-16 16:21:53', 9857.900390625, 3069.800048828125, 3.2109999656677246, 'New York'),
    (4, 24757693631, 'New York Running', '2026-10-17 10:24:10', 5497.97998046875, 1395.4339599609375, 3.940000057220459, 'New York'),
    (4, 24758713101, 'New York Running', '2026-10-17 10:57:50', 19516.779296875, 4370.98095703125, 4.465000152587891, 'New York'),
    (4, 24759221770, 'New York Running', '2026-10-17 12:12:43', 7512.58984375, 2133.70703125, 3.5209999084472656, 'New York'),
    (4, 24784076902, 'East Brunswick Running', '2026-10-19 16:31:23', 17289.33984375, 4972.18212890625, 3.4769999980926514, 'East Brunswick'),
    (4, 24796289138, 'New York Running', '2026-10-20 16:22:26', 17720.150390625, 5302.67578125, 3.3420000076293945, 'New York'),
    (4, 24802395169, 'New York Running', '2026-10-21 07:33:42', 9664.25, 3038.287109375, 3.180999994277954, 'New York'),
    (4, 24808451846, 'New York Running', '2026-10-21 17:51:21', 6902.35009765625, 2184.782958984375, 3.1589999198913574, 'New York'),
    (4, 24808856754, 'New York Running', '2026-10-21 18:55:35', 13557.2197265625, 3229.373046875, 4.197999954223633, 'New York'),
    (4, 24809077551, 'New York Running', '2026-10-21 20:07:24', 3247.31005859375, 1107.2330322265625, 2.933000087738037, 'New York'),
    (4, 24825042740, 'Montreal Running', '2026-10-23 07:28:23', 16907.26953125, 5151.041015625, 3.2820000648498535, 'Montreal'),
    (4, 24862457176, 'New York Running', '2026-10-26 16:32:40', 9674.169921875, 3027.947021484375, 3.194999933242798, 'New York'),
    (4, 24874425544, 'Treadmill Running', '2026-10-27 16:16:24', 6647.81982421875, 2086.535888671875, 3.186000108718872, null),
    (4, 24874556840, 'Running', '2026-10-27 17:16:19', 5632.704000000001, 1800.0, 3.12928, null),
    (4, 24887744074, 'New York Running', '2026-10-28 18:43:05', 9897.48046875, 2899.489990234375, 3.4140000343322754, 'New York'),
    (4, 24887780640, 'Running', '2026-10-28 19:49:54', 5149.9008, 1440.0, 3.57632, null),
    (4, 24903933597, 'New York Running', '2026-10-30 07:21:43', 9277.2001953125, 2766.212890625, 3.3540000915527344, 'New York'),
    (4, 24917500260, 'New York Running', '2026-10-31 09:40:13', 5480.0400390625, 1595.31005859375, 3.434999942779541, 'New York'),
    (4, 24932022890, 'New York Running', '2026-11-01 09:11:50', 42606.05078125, 9462.123046875, 4.502999782562256, 'New York'),
    (4, 25024998599, 'New York Running', '2026-11-09 16:31:13', 11809.9697265625, 3687.18310546875, 3.203000068664551, 'New York'),
    (4, 25030805591, 'New York Running', '2026-11-10 06:39:43', 16096.26953125, 4906.244140625, 3.2809998989105225, 'New York'),
    (4, 25042916008, 'New York Running', '2026-11-11 06:29:57', 18765.80078125, 5453.2568359375, 3.440999984741211, 'New York'),
    (4, 25054528359, 'New York Running', '2026-11-12 07:14:55', 16099.240234375, 4574.35693359375, 3.5190000534057617, 'New York'),
    (4, 25102384657, 'New York Running', '2026-11-16 16:04:33', 12895.849609375, 3948.52001953125, 3.266000032424927, 'New York'),
    (4, 25108334014, 'New York Running', '2026-11-17 07:04:34', 14059.8095703125, 4662.13623046875, 3.0160000324249268, 'New York'),
    (4, 25119256779, 'New York Running', '2026-11-18 06:53:10', 6153.64990234375, 2183.1630859375, 2.819000005722046, 'New York'),
    (4, 25125367898, 'New York Running', '2026-11-18 16:32:15', 13752.5498046875, 4916.2451171875, 2.796999931335449, 'New York'),
    (4, 25134020287, 'Treadmill Running', '2026-11-19 12:35:57', 14966.900390625, 4365.6611328125, 3.427999973297119, null),
    (4, 25136175679, 'New York Running', '2026-11-19 17:33:47', 8133.60009765625, 2488.322021484375, 3.2690000534057617, 'New York'),
    (4, 25147398360, 'New York Running', '2026-11-20 16:42:52', 13059.8603515625, 3896.405029296875, 3.351999998092652, 'New York')
) as src (
  local_id,
  garmin_activity_id,
  name,
  start_time_local,
  distance_meters,
  duration_seconds,
  average_speed_mps,
  location_name
)
join public.athletes athlete on athlete.local_id = src.local_id
where athlete.display_name <> 'Athlete'
on conflict (athlete_id, garmin_activity_id) do update
set
  name = excluded.name,
  start_time_local = excluded.start_time_local,
  distance_meters = excluded.distance_meters,
  duration_seconds = excluded.duration_seconds,
  average_speed_mps = excluded.average_speed_mps,
  location_name = excluded.location_name,
  updated_at = now();
