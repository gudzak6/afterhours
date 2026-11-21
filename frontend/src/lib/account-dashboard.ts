import type { SupabaseClient } from "@supabase/supabase-js";
import type { CoachAccount, CoachDashboard, RosterAthlete } from "@/lib/api";

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
    ? supabase.from("profiles").select("display_name, email, timezone, email_notifications_enabled").eq("id", user.id).maybeSingle()
    : Promise.resolve({ data: null, error: null });
  const [{ data: profile, error: profileError }, { data: athletes, error: athleteError }] = await Promise.all([
    profileRequest,
    supabase.rpc("roster_athletes"),
  ]);
  raise(profileError);
  raise(athleteError);

  const coach: CoachAccount = {
    display_name: profile?.display_name || user?.email?.split("@")[0] || "Coach Owen",
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
  const supabaseIds = rows.map((row) => row.id);
  const [goals, plans, activities] = await Promise.all([
    readableRows<GoalRow>(supabase.from("training_goals").select("athlete_id, primary_race_goal").in("athlete_id", supabaseIds)),
    readableRows<PlanRow>(
      supabase
        .from("scheduled_workouts")
        .select("id, athlete_id, scheduled_date, title, workout_type, distance_miles, repetitions, rep_distance_miles, target_pace, intensity")
        .in("athlete_id", supabaseIds)
        .gte("scheduled_date", week.start)
        .lt("scheduled_date", week.end)
        .order("scheduled_date"),
    ),
    optionalRows<ActivityRow>(
      supabase
        .from("activities")
        .select("athlete_id, garmin_activity_id, name, start_time_local, distance_meters, duration_seconds, average_speed_mps, location_name")
        .in("athlete_id", supabaseIds)
        .gte("start_time_local", week.start)
        .lt("start_time_local", week.end)
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
