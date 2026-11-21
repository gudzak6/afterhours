"use client";

import { createClient } from "@/utils/supabase/client";
import { createRosterAthlete, type Athlete, type AthleteGoals, type PlannedWorkout, type RaceEntry } from "@/lib/api";

type QueryError = { message: string; code?: string } | null;

function raise(error: QueryError) {
  if (!error) return;
  if (error.code === "PGRST205" || error.code === "42P01") {
    throw new Error("The account database is not set up yet.");
  }
  throw new Error(error.message);
}

function blank(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

export async function hasAccount() {
  const supabase = createClient();
  const { data } = await supabase.auth.getUser();
  return Boolean(data.user);
}

export async function accountEmail() {
  const supabase = createClient();
  const { data } = await supabase.auth.getUser();
  return data.user?.email ?? null;
}

export async function signIn(email: string, password: string) {
  const supabase = createClient();
  const { error } = await supabase.auth.signInWithPassword({ email, password });
  raise(error);
}

export async function signUp(email: string, password: string, displayName: string) {
  const supabase = createClient();
  const { data, error } = await supabase.auth.signUp({
    email,
    password,
    options: {
      data: { display_name: displayName },
      emailRedirectTo: `${window.location.origin}/auth/callback`,
    },
  });
  raise(error);
  return Boolean(data.session);
}

export async function signOut() {
  const supabase = createClient();
  const { error } = await supabase.auth.signOut();
  raise(error);
  window.sessionStorage.removeItem("trainingcoach-athlete");
  window.sessionStorage.removeItem("trainingcoach-garmin-skipped");
}

async function requireUser() {
  const supabase = createClient();
  const { data, error } = await supabase.auth.getUser();
  raise(error);
  if (!data.user) {
    throw new Error("Sign in to save this to your account.");
  }
  return { supabase, user: data.user };
}

async function ensureProfile(supabase: ReturnType<typeof createClient>, user: { id: string; email?: string | null; user_metadata?: Record<string, unknown> }) {
  const { data, error } = await supabase.from("profiles").select("id, role").eq("id", user.id).maybeSingle();
  raise(error);
  if (data) {
    if (data.role !== "athlete") {
      const { error: updateError } = await supabase.from("profiles").update({ role: "athlete", updated_at: new Date().toISOString() }).eq("id", user.id);
      raise(updateError);
    }
    return;
  }
  const displayName = blank(user.user_metadata?.display_name) || user.email?.split("@")[0] || "Athlete";
  const { error: insertError } = await supabase.from("profiles").insert({
    id: user.id,
    display_name: displayName,
    email: user.email ?? null,
    role: "athlete",
  });
  raise(insertError);
}

const ATHLETE_FOR_PREFIX = "trainingcoach-athlete-for:";

export async function signedInAthleteId(): Promise<number | null> {
  const supabase = createClient();
  const { data } = await supabase.auth.getUser();
  const user = data.user;
  if (!user) return null;
  const cacheKey = `${ATHLETE_FOR_PREFIX}${user.id}`;
  const cached = Number(window.localStorage.getItem(cacheKey));
  if (Number.isFinite(cached) && cached > 0) return cached;

  const { data: row, error } = await supabase.from("athletes").select("local_id").eq("user_id", user.id).maybeSingle();
  if (error && error.code !== "PGRST205" && error.code !== "42P01") {
    throw new Error(error.message);
  }
  if (row?.local_id) {
    window.localStorage.setItem(cacheKey, String(row.local_id));
    return Number(row.local_id);
  }

  const displayName = blank(user.user_metadata?.display_name) || user.email?.split("@")[0] || "Athlete";
  const created = await createRosterAthlete(displayName);
  try {
    await ensureAthlete(created.id, created.display_name);
  } catch (setupError) {
    if (!(setupError instanceof Error) || !setupError.message.includes("not set up yet")) throw setupError;
  }
  window.localStorage.setItem(cacheKey, String(created.id));
  window.sessionStorage.setItem("trainingcoach-athlete", String(created.id));
  return created.id;
}

export async function prepareAccount() {
  try {
    const { supabase, user } = await requireUser();
    await ensureProfile(supabase, user);
  } catch (error) {
    if (!(error instanceof Error) || !error.message.includes("not set up yet")) throw error;
  }
  await signedInAthleteId();
}

async function ensureAthlete(localId: number, displayName?: string) {
  const { supabase, user } = await requireUser();
  await ensureProfile(supabase, user);
  const { data, error } = await supabase
    .from("athletes")
    .select("id")
    .eq("coach_id", user.id)
    .eq("local_id", localId)
    .maybeSingle();
  raise(error);
  if (data) {
    return { supabase, user, athleteId: data.id as number };
  }
  const { data: created, error: insertError } = await supabase
    .from("athletes")
    .insert({
      coach_id: user.id,
      user_id: user.id,
      local_id: localId,
      display_name: displayName?.trim() || "Athlete",
    })
    .select("id")
    .single();
  raise(insertError);
  if (!created) throw new Error("The athlete record did not save.");
  return { supabase, user, athleteId: created.id as number };
}

export async function loadAccountProfile() {
  const supabase = createClient();
  const { data: userData } = await supabase.auth.getUser();
  if (!userData.user) return null;
  const { data, error } = await supabase
    .from("profiles")
    .select("display_name, email, timezone, email_notifications_enabled")
    .eq("id", userData.user.id)
    .maybeSingle();
  raise(error);
  return data;
}

export async function saveAccountProfile(body: {
  display_name: string;
  email: string | null;
  timezone: string;
  email_notifications_enabled: boolean;
}) {
  const { supabase, user } = await requireUser();
  await ensureProfile(supabase, user);
  const { error } = await supabase
    .from("profiles")
    .update({ ...body, updated_at: new Date().toISOString() })
    .eq("id", user.id);
  raise(error);
}

const athleteColumns = [
  "display_name",
  "running_experience",
  "typical_weekly_mileage",
  "max_heart_rate_bpm",
  "preferred_training_days",
  "target_time",
  "coach_notes",
  "intake",
  "pace_zones",
  "heart_rate_zones",
] as const;

export async function loadOwnedAthlete(localId: number): Promise<Athlete | null> {
  const supabase = createClient();
  const { data: userData } = await supabase.auth.getUser();
  if (!userData.user) return null;
  const { data: athlete, error } = await supabase
    .from("athletes")
    .select("id, display_name, running_experience, typical_weekly_mileage, max_heart_rate_bpm, preferred_training_days, target_time, coach_notes, intake, pace_zones, heart_rate_zones")
    .eq("coach_id", userData.user.id)
    .eq("local_id", localId)
    .maybeSingle();
  raise(error);
  if (!athlete) return null;
  const [{ data: thresholds, error: thresholdError }, { data: goal, error: goalError }] = await Promise.all([
    supabase.from("athlete_thresholds").select("name, pace_seconds_per_mile, heart_rate_bpm, source").eq("athlete_id", athlete.id),
    supabase.from("training_goals").select("primary_race_goal, goal_race_date").eq("athlete_id", athlete.id).maybeSingle(),
  ]);
  raise(thresholdError);
  raise(goalError);
  return {
    id: localId,
    display_name: athlete.display_name,
    running_experience: athlete.running_experience,
    typical_weekly_mileage: athlete.typical_weekly_mileage,
    max_heart_rate_bpm: athlete.max_heart_rate_bpm,
    preferred_training_days: athlete.preferred_training_days ?? [],
    pace_zones: athlete.pace_zones ?? [],
    heart_rate_zones: athlete.heart_rate_zones ?? [],
    primary_race_goal: goal?.primary_race_goal ?? null,
    goal_race_date: goal?.goal_race_date ?? null,
    target_time: athlete.target_time,
    coach_notes: athlete.coach_notes,
    intake: athlete.intake,
    thresholds: thresholds ?? [],
  };
}

export async function saveOwnedAthlete(localId: number, body: Record<string, unknown>) {
  const displayName = typeof body.display_name === "string" ? body.display_name : undefined;
  const { supabase, athleteId } = await ensureAthlete(localId, displayName);
  const patch: Record<string, unknown> = { updated_at: new Date().toISOString() };
  for (const column of athleteColumns) {
    if (column in body) patch[column] = body[column];
  }
  if (Object.keys(patch).length > 1) {
    const { error } = await supabase.from("athletes").update(patch).eq("id", athleteId);
    raise(error);
  }
  if ("primary_race_goal" in body || "goal_race_date" in body) {
    const { data: existing, error } = await supabase.from("training_goals").select("id").eq("athlete_id", athleteId).maybeSingle();
    raise(error);
    const goalPatch: Record<string, unknown> = { updated_at: new Date().toISOString() };
    if ("primary_race_goal" in body) goalPatch.primary_race_goal = body.primary_race_goal;
    if ("goal_race_date" in body) goalPatch.goal_race_date = body.goal_race_date || null;
    if (existing) {
      const { error: updateError } = await supabase.from("training_goals").update(goalPatch).eq("id", existing.id);
      raise(updateError);
    } else {
      const { error: insertError } = await supabase.from("training_goals").insert({ athlete_id: athleteId, ...goalPatch });
      raise(insertError);
    }
  }
  if (Array.isArray(body.thresholds)) {
    for (const item of body.thresholds) {
      if (!item || typeof item !== "object") continue;
      const threshold = item as Record<string, unknown>;
      const name = typeof threshold.name === "string" ? threshold.name.trim() : "";
      if (!name) continue;
      const { error } = await supabase.from("athlete_thresholds").upsert(
        {
          athlete_id: athleteId,
          name,
          pace_seconds_per_mile: threshold.pace_seconds_per_mile ?? null,
          heart_rate_bpm: threshold.heart_rate_bpm ?? null,
          source: "user",
          updated_at: new Date().toISOString(),
        },
        { onConflict: "athlete_id,name" },
      );
      raise(error);
    }
  }
}

export async function loadAccountGoals(localId: number): Promise<AthleteGoals | null> {
  const supabase = createClient();
  const { data: userData } = await supabase.auth.getUser();
  if (!userData.user) return null;
  const { data: athlete, error } = await supabase
    .from("athletes")
    .select("id, target_time")
    .eq("coach_id", userData.user.id)
    .eq("local_id", localId)
    .maybeSingle();
  raise(error);
  if (!athlete) return null;
  const [{ data: goal, error: goalError }, { data: races, error: raceError }] = await Promise.all([
    supabase.from("training_goals").select("primary_race_goal, goal_race_date").eq("athlete_id", athlete.id).maybeSingle(),
    supabase.from("races").select("id, name, race_date, distance_label, distance_meters, goal_time, result_time, notes").eq("athlete_id", athlete.id).order("race_date", { ascending: true }),
  ]);
  raise(goalError);
  raise(raceError);
  return {
    primary_race_goal: goal?.primary_race_goal ?? null,
    goal_race_date: goal?.goal_race_date ?? null,
    target_time: athlete.target_time,
    races: (races ?? []) as RaceEntry[],
  };
}

export async function saveAccountGoal(localId: number, body: { primary_race_goal: string | null; goal_race_date: string | null; target_time: string | null }) {
  await saveOwnedAthlete(localId, body);
  const saved = await loadAccountGoals(localId);
  if (!saved) throw new Error("The goal did not save.");
  return saved;
}

export async function saveAccountRace(localId: number, body: Record<string, unknown>) {
  const name = typeof body.name === "string" ? body.name.trim() : "";
  if (!name) throw new Error("Name the race.");
  const { supabase, athleteId } = await ensureAthlete(localId);
  const { error } = await supabase.from("races").insert({
    athlete_id: athleteId,
    name,
    race_date: body.race_date || null,
    distance_label: blank(body.distance_label),
    goal_time: blank(body.goal_time),
    result_time: blank(body.result_time),
    notes: blank(body.notes),
  });
  raise(error);
}

export async function deleteAccountRace(raceId: number) {
  const { supabase } = await requireUser();
  const { error } = await supabase.from("races").delete().eq("id", raceId);
  raise(error);
}

type WorkoutDraft = {
  scheduled_date: string;
  title: string;
  workout_type?: string | null;
  distance_miles?: number | null;
  repetitions?: number | null;
  rep_distance_miles?: number | null;
  recovery_seconds?: number | null;
  target_pace?: string | null;
  warmup?: string | null;
  cooldown?: string | null;
  intensity?: string | null;
  coach_notes?: string | null;
  details?: string | null;
};

function workoutRow(athleteId: number, sourceKey: string, draft: WorkoutDraft) {
  return {
    athlete_id: athleteId,
    source_key: sourceKey,
    scheduled_date: draft.scheduled_date,
    title: draft.title,
    workout_type: draft.workout_type ?? null,
    distance_miles: draft.distance_miles ?? null,
    repetitions: draft.repetitions ?? null,
    rep_distance_miles: draft.rep_distance_miles ?? null,
    recovery_seconds: draft.recovery_seconds ?? null,
    target_pace: draft.target_pace ?? null,
    warmup: draft.warmup ?? null,
    cooldown: draft.cooldown ?? null,
    intensity: draft.intensity ?? null,
    coach_notes: draft.coach_notes ?? null,
    details: draft.details ?? null,
    updated_at: new Date().toISOString(),
  };
}

export function draftFromWorkout(workout: PlannedWorkout): WorkoutDraft {
  return {
    scheduled_date: workout.scheduled_date,
    title: workout.title,
    workout_type: workout.workout_type,
    distance_miles: workout.distance_miles,
    repetitions: workout.repetitions,
    rep_distance_miles: workout.rep_distance_miles,
    recovery_seconds: workout.recovery_seconds,
    target_pace: workout.target_pace,
    warmup: workout.warmup,
    cooldown: workout.cooldown,
    intensity: workout.intensity,
    coach_notes: workout.coach_notes,
    details: workout.details ?? null,
  };
}

export async function mirrorWorkout(localId: number, localWorkoutId: number, draft: WorkoutDraft, keepRevision: boolean) {
  const { supabase, athleteId } = await ensureAthlete(localId);
  const sourceKey = `local:${localWorkoutId}`;
  const row = workoutRow(athleteId, sourceKey, draft);
  const { data: existing, error } = await supabase
    .from("scheduled_workouts")
    .select("id, scheduled_date, title, workout_type, distance_miles, repetitions, rep_distance_miles, recovery_seconds, target_pace, warmup, cooldown, intensity, coach_notes, details")
    .eq("athlete_id", athleteId)
    .eq("source_key", sourceKey)
    .maybeSingle();
  raise(error);
  if (!existing) {
    const { error: insertError } = await supabase.from("scheduled_workouts").insert({
      ...row,
      original_prescription: draft,
      created_at: new Date().toISOString(),
    });
    raise(insertError);
    return;
  }
  if (keepRevision) {
    const { error: revisionError } = await supabase.from("plan_revisions").insert({
      scheduled_workout_id: existing.id,
      prescription: existing,
    });
    raise(revisionError);
  }
  const { error: updateError } = await supabase.from("scheduled_workouts").update(row).eq("id", existing.id);
  raise(updateError);
}

export async function mirrorPlanIfEmpty(localId: number, workouts: PlannedWorkout[]) {
  if (workouts.length === 0) return;
  const supabase = createClient();
  const { data: userData } = await supabase.auth.getUser();
  if (!userData.user) return;
  const { data: athlete, error } = await supabase
    .from("athletes")
    .select("id")
    .eq("coach_id", userData.user.id)
    .eq("local_id", localId)
    .maybeSingle();
  raise(error);
  if (athlete) {
    const { count, error: countError } = await supabase
      .from("scheduled_workouts")
      .select("id", { count: "exact", head: true })
      .eq("athlete_id", athlete.id);
    raise(countError);
    if ((count ?? 0) > 0) return;
  }
  for (const workout of workouts) {
    await mirrorWorkout(localId, workout.id, draftFromWorkout(workout), false);
  }
}
