import type { SupabaseClient } from "@supabase/supabase-js";
import type { Activity, Athlete, CoachAccount, CoachDashboard, MileageChart, PlanView, PlannedWorkout, PlanWeek, RosterAthlete, RunningStats, WeeklyMileage } from "@/lib/api";

type QueryError = { message: string; code?: string; name?: string } | null;

type AthleteRow = {
  id: number;
  local_id: number | string;
  display_name: string;
  target_time: string | null;
};

type GoalRow = {
  athlete_id: number;
  primary_race_goal: string | null;
};

type PlanRow = {
  id: number;
  athlete_id: number;
  scheduled_date: string;
  title: string;
  workout_type: string | null;
  distance_miles: number | null;
  repetitions: number | null;
  rep_distance_miles: number | null;
  target_pace: string | null;
  intensity: string | null;
};

type ActivityRow = {
  athlete_id: number;
  garmin_activity_id: number;
  name: string | null;
  start_time_local: string | null;
  distance_meters: number | null;
  duration_seconds: number | null;
  average_speed_mps: number | null;
  location_name: string | null;
};

const DEFAULT_TIMEZONE = "America/New_York";

function raise(error: QueryError) {
  if (!error) return;
  if (error.code === "PGRST205" || error.code === "42P01") {
    throw new Error("The account database is not set up yet.");
  }
  throw new Error(error.message);
}

function unreadable(error: QueryError) {
  if (!error) return false;
  return error.code === "42501" || /permission denied/i.test(error.message);
}

async function readableRows<T>(query: PromiseLike<{ data: T[] | null; error: QueryError }>): Promise<T[]> {
  const { data, error } = await query;
  if (unreadable(error)) return [];
  raise(error);
  return data ?? [];
}

async function optionalRows<T>(query: PromiseLike<{ data: T[] | null; error: QueryError }>): Promise<T[]> {
  const { data, error } = await query;
  if (!error) return data ?? [];
  if (unreadable(error) || error.code === "PGRST205" || error.code === "42P01") return [];
  raise(error);
  return [];
}

function paceSeconds(speed: number | null) {
  if (speed == null || speed <= 0) return null;
  return 1609.344 / speed;
}

function signedOut(error: QueryError) {
  if (!error) return false;
  return error.name === "AuthSessionMissingError" || error.message === "Auth session missing!";
}

function rosterId(value: number | string, fallback: number) {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function todayInTimeZone(timeZone: string) {
  const zone = timeZone || DEFAULT_TIMEZONE;
  let parts: Intl.DateTimeFormatPart[];
  try {
    parts = new Intl.DateTimeFormat("en-US", {
      timeZone: zone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).formatToParts(new Date());
  } catch {
    parts = new Intl.DateTimeFormat("en-US", {
      timeZone: DEFAULT_TIMEZONE,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).formatToParts(new Date());
  }
  const value = (type: string) => parts.find((part) => part.type === type)?.value ?? "";
  return `${value("year")}-${value("month")}-${value("day")}`;
}

function weekContaining(iso: string) {
  const [year, month, day] = iso.split("-").map(Number);
  const selected = new Date(Date.UTC(year, (month || 1) - 1, day || 1));
  selected.setUTCDate(selected.getUTCDate() - selected.getUTCDay());
  const start = selected.toISOString().slice(0, 10);
  selected.setUTCDate(selected.getUTCDate() + 7);
  return { start, end: selected.toISOString().slice(0, 10) };
}

function scheduleWindow(iso: string) {
  const sunday = weekContaining(iso);
  const [year, month, day] = iso.split("-").map(Number);
  const selected = new Date(Date.UTC(year, (month || 1) - 1, day || 1));
  const monday = new Date(selected);
  monday.setUTCDate(selected.getUTCDate() - ((selected.getUTCDay() + 6) % 7));
  const mondayEnd = new Date(monday);
  mondayEnd.setUTCDate(monday.getUTCDate() + 7);
  const mondayStart = monday.toISOString().slice(0, 10);
  const mondayStop = mondayEnd.toISOString().slice(0, 10);
  return {
    start: sunday.start < mondayStart ? sunday.start : mondayStart,
    end: sunday.end > mondayStop ? sunday.end : mondayStop,
  };
}

function planDetail(plan: PlanRow) {
  const bits: string[] = [];
  if (plan.workout_type) bits.push(plan.workout_type.replaceAll("_", " "));
  if (typeof plan.distance_miles === "number") bits.push(`${plan.distance_miles.toFixed(2)} mi`);
  if (plan.repetitions) {
    bits.push(
      typeof plan.rep_distance_miles === "number"
        ? `${plan.repetitions} x ${plan.rep_distance_miles.toFixed(2)} mi`
        : `${plan.repetitions} reps`,
    );
  }
  if (plan.target_pace) bits.push(`${plan.target_pace}/mi`);
  if (plan.intensity) bits.push(plan.intensity);
  return bits.join(" · ") || null;
}

function emptyDashboard(coach: CoachAccount, day?: string | null): CoachDashboard {
  const today = todayInTimeZone(coach.timezone);
  const selected = day && /^\d{4}-\d{2}-\d{2}$/.test(day) ? day : today;
  return {
    athlete_count: 0,
    ran_today: 0,
    attention_count: 0,
    athletes: [],
    recent_activities: [],
    planned_workouts: [],
    today,
    week_start: weekContaining(selected).start,
    brief: null,
    brief_created_at: null,
    coach,
  };
}

export async function loadAccountDashboard(supabase: SupabaseClient, day?: string | null): Promise<CoachDashboard> {
  const { data: userData, error: userError } = await supabase.auth.getUser();
  if (!signedOut(userError)) raise(userError);
  const user = userData.user;
  const profileRequest = user
    ? supabase.from("profiles").select("display_name, email, timezone, email_notifications_enabled, role").eq("id", user.id).maybeSingle()
    : Promise.resolve({ data: null, error: null });
  const [{ data: profile, error: profileError }, { data: athletes, error: athleteError }] = await Promise.all([
    profileRequest,
    supabase.rpc("roster_athletes"),
  ]);
  raise(profileError);
  raise(athleteError);

  const coach: CoachAccount = {
    display_name: profile?.role === "coach" ? profile.display_name : "Coach Owen",
    email: profile?.email ?? user?.email ?? null,
    timezone: profile?.timezone || DEFAULT_TIMEZONE,
    email_notifications_enabled: Boolean(profile?.email_notifications_enabled),
    email_configured: false,
  };
  const rows = ((athletes ?? []) as AthleteRow[]).filter((row) => {
    const name = row.display_name.trim().toLowerCase();
    return name !== "new garmin athlete" && name !== "athlete";
  });
  if (rows.length === 0) return emptyDashboard(coach, day);

  const today = todayInTimeZone(coach.timezone);
  const selected = day && /^\d{4}-\d{2}-\d{2}$/.test(day) ? day : today;
  const week = weekContaining(selected);
  const span = scheduleWindow(selected);
  const supabaseIds = rows.map((row) => row.id);
  const [goals, plans, activities] = await Promise.all([
    readableRows<GoalRow>(supabase.from("training_goals").select("athlete_id, primary_race_goal").in("athlete_id", supabaseIds)),
    readableRows<PlanRow>(
      supabase
        .from("scheduled_workouts")
        .select("id, athlete_id, scheduled_date, title, workout_type, distance_miles, repetitions, rep_distance_miles, target_pace, intensity")
        .in("athlete_id", supabaseIds)
        .gte("scheduled_date", span.start)
        .lt("scheduled_date", span.end)
        .order("scheduled_date"),
    ),
    optionalRows<ActivityRow>(
      supabase
        .from("activities")
        .select("athlete_id, garmin_activity_id, name, start_time_local, distance_meters, duration_seconds, average_speed_mps, location_name")
        .in("athlete_id", supabaseIds)
        .gte("start_time_local", span.start)
        .lt("start_time_local", span.end)
        .order("start_time_local", { ascending: false }),
    ),
  ]);

  const goalByAthlete = new Map<number, string | null>();
  for (const goal of goals) {
    goalByAthlete.set(goal.athlete_id, goal.primary_race_goal);
  }
  const plansByAthlete = new Map<number, PlanRow[]>();
  for (const plan of plans) {
    const list = plansByAthlete.get(plan.athlete_id) ?? [];
    list.push(plan);
    plansByAthlete.set(plan.athlete_id, list);
  }
  const names = new Map<number, { id: number; name: string }>();
  const runsByAthlete = new Map<number, ActivityRow[]>();
  for (const activity of activities) {
    const list = runsByAthlete.get(activity.athlete_id) ?? [];
    list.push(activity);
    runsByAthlete.set(activity.athlete_id, list);
  }
  const roster: RosterAthlete[] = rows.map((row) => {
    const id = rosterId(row.local_id, row.id);
    names.set(row.id, { id, name: row.display_name });
    const weekPlans = plansByAthlete.get(row.id) ?? [];
    const miles = weekPlans.map((plan) => plan.distance_miles).filter((value): value is number => typeof value === "number");
    const runs = runsByAthlete.get(row.id) ?? [];
    const latest = runs[0];
    const runMiles = runs
      .map((activity) => activity.distance_meters)
      .filter((value): value is number => typeof value === "number")
      .reduce((sum, meters) => sum + meters / 1609.344, 0);
    const latestMiles = latest?.distance_meters == null ? null : Math.round((latest.distance_meters / 1609.344) * 100) / 100;
    return {
      id,
      display_name: row.display_name,
      race_goal: goalByAthlete.get(row.id) ?? null,
      target_time: row.target_time,
      weekly_miles: runs.length === 0 ? null : runMiles,
      recent_activity: latest ? `${latest.name || "Activity"}${latestMiles == null ? "" : ` · ${latestMiles} mi`}` : null,
      recent_activity_id: latest?.garmin_activity_id ?? null,
      recent_activity_at: latest?.start_time_local ?? null,
      training_status: runs.length === 0 ? "no_data" : "on_track",
      attention_reasons: [],
      garmin_status: "not_connected",
      ran_today: runs.some((activity) => activity.start_time_local?.startsWith(today) ?? false),
      planned_weekly_miles: miles.length === 0 ? null : miles.reduce((sum, value) => sum + value, 0),
      workouts_completed: 0,
      workouts_scheduled: weekPlans.length,
      workouts_still_scheduled: weekPlans.length,
      key_workout_status: null,
    };
  });

  return {
    athlete_count: roster.length,
    ran_today: roster.filter((athlete) => athlete.ran_today).length,
    attention_count: 0,
    athletes: roster,
    recent_activities: activities.map((activity) => {
      const athlete = names.get(activity.athlete_id);
      return {
        garmin_activity_id: activity.garmin_activity_id,
        athlete_id: athlete?.id ?? activity.athlete_id,
        athlete_name: athlete?.name ?? null,
        name: activity.name,
        distance_meters: activity.distance_meters,
        duration_seconds: activity.duration_seconds,
        average_pace_seconds_per_mile: paceSeconds(activity.average_speed_mps),
        location_name: activity.location_name,
        start_time_local: activity.start_time_local,
        analysis_summary: null,
        analysis_kind: null,
      };
    }),
    planned_workouts: plans.map((plan) => {
      const athlete = names.get(plan.athlete_id);
      return {
        id: plan.id,
        athlete_id: athlete?.id ?? plan.athlete_id,
        athlete_name: athlete?.name ?? null,
        scheduled_date: plan.scheduled_date,
        title: plan.title,
        detail: planDetail(plan),
      };
    }),
    today,
    week_start: week.start,
    brief: null,
    brief_created_at: null,
    coach,
  };
}

function weekStartFor(local: string) {
  const [year, month, day] = local.slice(0, 10).split("-").map(Number);
  const date = new Date(Date.UTC(year, (month || 1) - 1, day || 1));
  date.setUTCDate(date.getUTCDate() - date.getUTCDay());
  return date.toISOString().slice(0, 10);
}

function addDays(iso: string, days: number) {
  const [year, month, day] = iso.split("-").map(Number);
  const date = new Date(Date.UTC(year, (month || 1) - 1, day || 1));
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

async function storedRuns(supabase: SupabaseClient, athleteIds: number[]) {
  if (athleteIds.length === 0) return [];
  return optionalRows<ActivityRow>(
    supabase
      .from("activities")
      .select("athlete_id, garmin_activity_id, name, start_time_local, distance_meters, duration_seconds, average_speed_mps, location_name")
      .in("athlete_id", athleteIds)
      .order("start_time_local", { ascending: false }),
  );
}

function milesOf(meters: number | null) {
  return meters == null ? null : meters / 1609.344;
}

export async function loadStoredActivities(supabase: SupabaseClient, limit = 100): Promise<{ activities: Activity[]; total: number }> {
  const { data, error } = await supabase.rpc("roster_athletes");
  raise(error);
  const roster = (data ?? []) as AthleteRow[];
  const runs = await storedRuns(supabase, roster.map((row) => row.id));
  const localBySupabase = new Map(roster.map((row) => [row.id, rosterId(row.local_id, row.id)]));
  const names = new Map(roster.map((row) => [row.id, row.display_name]));
  const activities = runs.slice(0, limit).map((run) => storedActivity(run, localBySupabase.get(run.athlete_id) ?? run.athlete_id, names.get(run.athlete_id) ?? null));
  return { activities, total: runs.length };
}

export async function loadStoredOverview(supabase: SupabaseClient, athleteId: number) {
  const { data, error } = await supabase.rpc("roster_athletes");
  raise(error);
  const roster = (data ?? []) as AthleteRow[];
  const row = roster.find((item) => rosterId(item.local_id, item.id) === athleteId);
  if (!row) throw new Error("That athlete is not on the roster.");
  const localId = rosterId(row.local_id, row.id);
  const runs = await storedRuns(supabase, [row.id]);
  const weeks = new Map<string, { count: number; meters: number; seconds: number }>();
  for (const run of runs) {
    if (!run.start_time_local) continue;
    const start = weekStartFor(run.start_time_local);
    const current = weeks.get(start) ?? { count: 0, meters: 0, seconds: 0 };
    current.count += 1;
    current.meters += run.distance_meters ?? 0;
    current.seconds += run.duration_seconds ?? 0;
    weeks.set(start, current);
  }
  const weekly_mileage: WeeklyMileage[] = [...weeks.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([week_start, totals]) => ({
      week_start,
      activity_count: totals.count,
      distance_meters: totals.meters,
      distance_miles: totals.meters / 1609.344,
    }));
  const currentWeek = weekStartFor(new Date().toISOString());
  const thisWeek = weekly_mileage.find((week) => week.week_start === currentWeek);
  const prior = weekly_mileage.filter((week) => week.week_start < currentWeek).slice(-4);
  const priorMeters = prior.reduce((sum, week) => sum + (week.distance_meters ?? 0), 0);
  const priorSeconds = prior.reduce((sum, week) => sum + (weeks.get(week.week_start)?.seconds ?? 0), 0);
  const mileage_chart: MileageChart = {
    week_start: currentWeek,
    week_end: addDays(currentWeek, 6),
    distance_miles: thisWeek?.distance_miles ?? null,
    duration_seconds: weeks.get(currentWeek)?.seconds ?? null,
    elevation_feet: null,
    weeks: weekly_mileage.map((week) => ({
      week_start: week.week_start,
      week_end: addDays(week.week_start, 6),
      distance_miles: week.distance_miles,
      activity_count: week.activity_count,
      current: week.week_start === currentWeek,
    })),
    runs: runs
      .filter((run) => run.start_time_local != null && weekStartFor(run.start_time_local) === currentWeek)
      .map((run) => ({
        garmin_activity_id: run.garmin_activity_id,
        name: run.name,
        start_time_local: run.start_time_local,
        distance_miles: milesOf(run.distance_meters),
        duration_seconds: run.duration_seconds,
        elevation_feet: null,
      })),
  };
  const running_stats: RunningStats = {
    last_4_weeks: {
      activities_per_week: prior.length === 0 ? null : prior.reduce((sum, week) => sum + week.activity_count, 0) / prior.length,
      distance_miles: prior.length === 0 ? null : priorMeters / 1609.344,
      duration_seconds: prior.length === 0 ? null : priorSeconds,
      elevation_feet: null,
    },
    best_efforts: [],
  };
  const athlete: Athlete = {
    id: localId,
    display_name: row.display_name,
    running_experience: null,
    typical_weekly_mileage: null,
    max_heart_rate_bpm: null,
    target_time: row.target_time,
  };
  const status: RosterAthlete = {
    id: localId,
    display_name: row.display_name,
    race_goal: null,
    target_time: row.target_time,
    weekly_miles: thisWeek?.distance_miles ?? null,
    recent_activity: null,
    recent_activity_id: null,
    recent_activity_at: null,
    training_status: runs.length === 0 ? "no_data" : "on_track",
    attention_reasons: [],
    garmin_status: "not_connected",
    ran_today: false,
  };
  return {
    athlete,
    status,
    weekly_mileage,
    mileage_chart,
    running_stats,
    recent_workouts: runs.slice(0, 8).map((run) => ({
      garmin_activity_id: run.garmin_activity_id,
      name: run.name,
      distance_meters: run.distance_meters,
      start_time_local: run.start_time_local,
      workout_type: null,
    })),
    goal: {
      primary_race_goal: null,
      goal_race_date: null,
      target_time: row.target_time,
    },
    races: [],
  };
}

const QUALITY_TYPES = new Set(["intervals", "threshold", "tempo", "marathon_pace", "race", "strides", "progression"]);

function mondayOf(iso: string) {
  const [year, month, day] = iso.slice(0, 10).split("-").map(Number);
  const date = new Date(Date.UTC(year, (month || 1) - 1, day || 1));
  const weekday = date.getUTCDay();
  date.setUTCDate(date.getUTCDate() - (weekday === 0 ? 6 : weekday - 1));
  return date.toISOString().slice(0, 10);
}

function localToday() {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

export async function loadStoredPlan(supabase: SupabaseClient, athleteId: number): Promise<PlanView> {
  const { data, error } = await supabase.rpc("roster_athletes");
  raise(error);
  const roster = (data ?? []) as AthleteRow[];
  const row = roster.find((item) => rosterId(item.local_id, item.id) === athleteId);
  if (!row) return { trend: null, weeks: [], workouts: [] };
  const [stored, runs] = await Promise.all([
    readableRows<PlanRow & { details: string | null; warmup: string | null; cooldown: string | null; recovery_seconds: number | null; coach_notes: string | null }>(
      supabase
        .from("scheduled_workouts")
        .select("id, athlete_id, scheduled_date, title, details, workout_type, distance_miles, warmup, cooldown, repetitions, rep_distance_miles, recovery_seconds, target_pace, intensity, coach_notes")
        .eq("athlete_id", row.id)
        .order("scheduled_date"),
    ),
    storedRuns(supabase, [row.id]),
  ]);
  const today = localToday();
  const workouts: PlannedWorkout[] = stored.map((plan) => ({
    id: plan.id,
    scheduled_date: plan.scheduled_date,
    title: plan.title,
    workout_type: plan.workout_type,
    distance_miles: plan.distance_miles,
    warmup: plan.warmup,
    cooldown: plan.cooldown,
    repetitions: plan.repetitions,
    rep_distance_miles: plan.rep_distance_miles,
    recovery_seconds: plan.recovery_seconds,
    target_pace: plan.target_pace,
    intensity: plan.intensity,
    coach_notes: plan.coach_notes,
    details: plan.details,
    status: plan.scheduled_date >= today ? "scheduled" : "unmatched",
    execution: null,
    summary: null,
    match: null,
    candidates: [],
    original_prescription: null,
    revisions: [],
  }));
  if (workouts.length === 0) return { trend: null, weeks: [], workouts: [] };
  const first = mondayOf(workouts[0].scheduled_date);
  const last = mondayOf(workouts[workouts.length - 1].scheduled_date);
  const weeks: PlanWeek[] = [];
  for (let cursor = first; cursor <= last; cursor = addDays(cursor, 7)) {
    const end = addDays(cursor, 7);
    const weekPlans = workouts.filter((plan) => plan.scheduled_date >= cursor && plan.scheduled_date < end);
    const known = weekPlans.map((plan) => plan.distance_miles).filter((value): value is number => typeof value === "number");
    const planned = known.length === 0 ? null : known.reduce((sum, value) => sum + value, 0);
    const weekRuns = runs.filter((run) => {
      const day = run.start_time_local?.slice(0, 10);
      return day != null && day >= cursor && day < end && run.distance_meters != null;
    });
    const actual = weekRuns.length === 0 ? null : weekRuns.reduce((sum, run) => sum + (run.distance_meters ?? 0) / 1609.344, 0);
    const complete = weekPlans.length > 0 && known.length === weekPlans.length;
    const quality = weekPlans.filter((plan) => plan.workout_type != null && QUALITY_TYPES.has(plan.workout_type));
    const longRuns = weekPlans.filter((plan) => plan.workout_type === "long_run" && plan.distance_miles != null);
    const scheduled = weekPlans.filter((plan) => plan.status === "scheduled").length;
    weeks.push({
      week_start: cursor,
      in_progress: cursor <= today && today < end,
      planned_miles: planned,
      planned_miles_complete: complete,
      actual_miles: actual,
      variance_miles: complete && planned && actual != null ? actual - planned : null,
      variance_percent: complete && planned && actual != null ? ((actual - planned) / planned) * 100 : null,
      planned_workouts: weekPlans.length,
      completed_workouts: 0,
      partial_workouts: 0,
      still_scheduled: scheduled,
      confirmed_missed: 0,
      unmatched: weekPlans.length - scheduled,
      planned_quality: quality.length,
      completed_quality: 0,
      partial_quality: 0,
      planned_long_run_miles: longRuns.length === 0 ? null : longRuns.reduce((sum, plan) => sum + (plan.distance_miles ?? 0), 0),
      actual_long_run_miles: null,
      adherence: weekPlans.length === 0 ? null : 0,
    });
  }
  return { trend: null, weeks, workouts };
}

function storedActivity(run: ActivityRow, athleteId: number, athleteName: string | null): Activity {
  return {
    id: run.garmin_activity_id,
    garmin_activity_id: run.garmin_activity_id,
    name: run.name,
    activity_type_key: null,
    start_time_local: run.start_time_local,
    start_time_gmt: null,
    start_time_utc: null,
    distance_meters: run.distance_meters,
    distance_miles: milesOf(run.distance_meters),
    duration_seconds: run.duration_seconds,
    moving_duration_seconds: null,
    elapsed_duration_raw: null,
    average_speed_mps: run.average_speed_mps,
    average_pace_seconds_per_mile: run.average_speed_mps != null && run.average_speed_mps > 0 ? 1609.344 / run.average_speed_mps : null,
    average_heart_rate_bpm: null,
    max_heart_rate_bpm: null,
    elevation_gain_meters: null,
    elevation_loss_meters: null,
    average_cadence_spm: null,
    calories: null,
    lap_count: null,
    location_name: run.location_name,
    manual_activity: null,
    import_status: "stored",
    analysis_status: "not_started",
    present_fields: [],
    athlete_id: athleteId,
    athlete_name: athleteName,
  };
}
