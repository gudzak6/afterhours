export type SyncJob = {
  id: number;
  trigger: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  lookback_days: number | null;
  activities_seen: number;
  activities_imported: number;
  activities_updated: number;
  activities_skipped: number;
  error_code: string | null;
  error_message: string | null;
  http_status: number | null;
};

export type Activity = {
  id: number;
  garmin_activity_id: number;
  name: string | null;
  activity_type_key: string | null;
  start_time_local: string | null;
  start_time_gmt: string | null;
  start_time_utc: string | null;
  distance_meters: number | null;
  distance_miles: number | null;
  duration_seconds: number | null;
  moving_duration_seconds: number | null;
  elapsed_duration_raw: number | null;
  average_speed_mps: number | null;
  average_pace_seconds_per_mile: number | null;
  average_heart_rate_bpm: number | null;
  max_heart_rate_bpm: number | null;
  elevation_gain_meters: number | null;
  elevation_loss_meters: number | null;
  average_cadence_spm: number | null;
  calories: number | null;
  lap_count: number | null;
  location_name: string | null;
  manual_activity: boolean | null;
  import_status: string;
  analysis_status: string;
  workout_type?: string | null;
  classification_source?: string | null;
  present_fields: string[];
  start_latitude?: number | null;
  start_longitude?: number | null;
  athlete_id?: number | null;
  athlete_name?: string | null;
};

export type ActivityList = {
  activities: Activity[];
  total: number;
};

export type TrainingWindow = {
  days: number;
  activity_count: number;
  activities_with_distance: number;
  distance_meters: number | null;
  distance_miles: number | null;
};

export type WeeklyMileage = {
  week_start: string;
  activity_count: number;
  distance_meters: number | null;
  distance_miles: number | null;
};

export type TrainingSummary = {
  activity_count: number;
  last_7_days: TrainingWindow;
  last_28_days: TrainingWindow;
  workout_counts?: Record<string, number>;
  hard_workouts_28_days?: number;
  active_days_28?: number;
  weekly_mileage?: WeeklyMileage[];
};

export type Lap = {
  lap_number: number;
  distance_meters: number | null;
  distance_miles: number | null;
  duration_seconds: number | null;
  pace_seconds_per_mile: number | null;
  average_speed_mps: number | null;
  average_heart_rate_bpm: number | null;
  max_heart_rate_bpm: number | null;
  average_cadence: number | null;
  cadence_field: string | null;
  intensity: string | null;
  lap_trigger: string | null;
  present_fields: string[];
};

export type Segment = {
  segment_index: number;
  kind: string;
  start_lap: number | null;
  end_lap: number | null;
  lap_numbers: number[];
  confidence: number | null;
  source: string;
};

export type SeriesPoint = {
  elapsed_seconds: number | null;
  distance_meters: number | null;
  pace_seconds_per_mile: number | null;
  heart_rate_bpm: number | null;
  altitude_meters: number | null;
  cadence: number | null;
};

export type Classification = {
  workout_type: string;
  confidence: number | null;
  source: string;
  uncertainty: string | null;
  evidence: Record<string, unknown>;
};

export type ActivityDetail = {
  activity: Activity;
  laps: Lap[];
  segments: Segment[];
  classification: Classification | null;
  metrics: Record<string, unknown>;
  series: SeriesPoint[];
  report: Record<string, unknown> | null;
  report_status: string;
  fit_summary: Record<string, unknown> | null;
  workout_steps_found: boolean;
};

export type Threshold = {
  name: string;
  pace_seconds_per_mile: number | null;
  heart_rate_bpm: number | null;
  source: string;
};

export type RecentRace = {
  event?: string | null;
  race_date?: string | null;
  goal_time?: string | null;
  result_time?: string | null;
};

export type AthleteIntake = {
  first_name?: string | null;
  last_name?: string | null;
  email?: string | null;
  phone?: string | null;
  events?: string | null;
  outcome_goals?: string | null;
  process_goals?: string | null;
  personal_bests?: string | null;
  weekly_miles_last_3_weeks?: string | null;
  weekly_miles_last_3_months?: string | null;
  training_stipulations?: string | null;
  training_style?: string | null;
  strengths?: string | null;
  weaknesses?: string | null;
  why_run?: string | null;
  preferred_coach?: string | null;
  anything_else?: string | null;
  heard_about_us?: string | null;
  recent_races?: RecentRace[];
};

export type Athlete = {
  id: number;
  display_name: string;
  running_experience: string | null;
  typical_weekly_mileage: number | null;
  max_heart_rate_bpm: number | null;
  preferred_training_days?: string[];
  pace_zones?: Array<Record<string, unknown>>;
  heart_rate_zones?: Array<Record<string, unknown>>;
  primary_race_goal?: string | null;
  goal_race_date?: string | null;
  target_time?: string | null;
  coach_notes?: string | null;
  intake?: AthleteIntake | null;
  thresholds?: Threshold[];
  openai_configured?: boolean;
};

export type FileImportStatus = {
  running: boolean;
  counts: Record<string, number>;
};

export type ChatMessage = {
  id: number;
  role: string;
  content: string;
  created_at: string;
};

export type GarminStatus = {
  configured: boolean;
  connection_status: string;
  token_cached: boolean;
  token_expires_at: string | null;
  last_error: string | null;
  scheduler_enabled: boolean;
  scheduler_interval_minutes: number;
  fit_download_documented: boolean;
  fit_download_implemented: boolean;
  fit_download_note: string;
  last_sync: SyncJob | null;
};

export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(message: string, status: number, body: unknown) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

export function errorMessage(error: unknown): string {
  const raw = rawErrorMessage(error);
  if (/<!doctype|<html/i.test(raw)) {
    return "The coaching server did not return this page.";
  }
  return raw;
}

function rawErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const body = error.body;
    if (typeof body === "string" && body.trim()) return body;
    if (body && typeof body === "object") {
      const record = body as Record<string, unknown>;
      if (typeof record.error_message === "string" && record.error_message) {
        return record.error_message;
      }
      if (typeof record.message === "string" && record.message) {
        return record.message;
      }
    }
    return error.message;
  }
  return error instanceof Error ? error.message : "Request failed";
}

function missingCoachingApi(error: unknown) {
  if (!(error instanceof ApiError) || error.status < 500) return false;
  return true;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/backend${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
    cache: "no-store",
  });
  if (response.status === 204) {
    return undefined as T;
  }
  const text = await response.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text) as unknown;
    } catch {
      throw new ApiError("The coaching server is not connected to this site.", response.status || 502, null);
    }
  }
  if (!response.ok) {
    const detail =
      body && typeof body === "object" && "detail" in body
        ? (body as { detail: unknown }).detail
        : body;
    const message =
      detail && typeof detail === "object"
        ? String(
            (detail as { error_message?: string; message?: string }).error_message ||
              (detail as { message?: string }).message ||
              response.statusText,
          )
        : typeof detail === "string"
          ? detail
          : response.statusText;
    throw new ApiError(message, response.status, detail);
  }
  return body as T;
}

function serverMissing(error: unknown) {
  return error instanceof ApiError && (error.status === 404 || error.status >= 500 || /not connected/i.test(error.message));
}

export async function getActivities(limit = 100) {
  try {
    return await request<ActivityList>(`/api/activities?limit=${limit}`);
  } catch (error) {
    if (!serverMissing(error)) throw error;
    const [{ createClient }, { loadStoredActivities }] = await Promise.all([
      import("@/utils/supabase/client"),
      import("@/lib/account-dashboard"),
    ]);
    return loadStoredActivities(createClient(), limit);
  }
}

export function getActivity(activityId: number) {
  return request<ActivityDetail>(`/api/activities/${activityId}`);
}

export function deleteActivity(activityId: number) {
  return request<void>(`/api/activities/${activityId}`, { method: "DELETE" });
}

export function getSummary() {
  return request<TrainingSummary>("/api/training/summary");
}

export function getGarminStatus() {
  return request<GarminStatus>("/api/garmin/status");
}

export function getAthlete() {
  return request<Athlete>("/api/athlete");
}

export function updateAthlete(body: Record<string, unknown>) {
  return request<Athlete>("/api/athlete", {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function getFileStatus() {
  return request<FileImportStatus>("/api/garmin/files");
}

export function startFileImport() {
  return request<FileImportStatus>("/api/garmin/files", { method: "POST", body: "{}" });
}

export function importActivityFile(activityId: number) {
  return request<{ import_status: string }>(`/api/activities/${activityId}/file`, {
    method: "POST",
    body: "{}",
  });
}

export function updateClassification(activityId: number, workoutType: string) {
  return request<Classification>(`/api/activities/${activityId}/classification`, {
    method: "PATCH",
    body: JSON.stringify({ workout_type: workoutType }),
  });
}

export function createReport(activityId: number) {
  return request<{ status: string; model: string | null; report: Record<string, unknown> }>(
    `/api/activities/${activityId}/report`,
    { method: "POST", body: "{}" },
  );
}

export function sendChat(message: string, conversationId: number | null, garminActivityId: number | null) {
  return request<{ conversation_id: number; messages: ChatMessage[] }>("/api/coach/chat", {
    method: "POST",
    body: JSON.stringify({
      message,
      conversation_id: conversationId,
      garmin_activity_id: garminActivityId,
    }),
  });
}

export type CoachAccount = {
  display_name: string;
  email: string | null;
  timezone: string;
  email_notifications_enabled: boolean;
  email_configured: boolean;
};

export type RosterAthlete = {
  id: number;
  display_name: string;
  race_goal: string | null;
  target_time: string | null;
  weekly_miles: number | null;
  recent_activity: string | null;
  recent_activity_id: number | null;
  recent_activity_at: string | null;
  training_status: string;
  attention_reasons: string[];
  garmin_status: string;
  ran_today: boolean;
  planned_weekly_miles?: number | null;
  workouts_completed?: number;
  workouts_scheduled?: number;
  workouts_still_scheduled?: number;
  key_workout_status?: string | null;
};

export type BriefItem = {
  athlete_id: number;
  athlete_name: string;
  garmin_activity_id: number | null;
  reason?: string;
  note?: string;
  action?: string;
};

export type CoachingBrief = {
  daily_summary: string;
  requires_attention: BriefItem[];
  positive_developments: BriefItem[];
  suggested_actions: BriefItem[];
};

export type CoachDashboard = {
  athlete_count: number;
  ran_today: number;
  attention_count: number;
  athletes: RosterAthlete[];
  recent_activities: Array<{
    garmin_activity_id: number;
    athlete_id: number;
    athlete_name: string | null;
    name: string | null;
    distance_meters: number | null;
    duration_seconds?: number | null;
    average_pace_seconds_per_mile?: number | null;
    location_name?: string | null;
    start_time_local: string | null;
    analysis_summary?: string | null;
    analysis_kind?: "easy" | "workout" | null;
  }>;
  planned_workouts: Array<{
    id: number;
    athlete_id: number;
    athlete_name: string | null;
    scheduled_date: string;
    title: string;
    detail: string | null;
  }>;
  today: string;
  week_start: string;
  brief: CoachingBrief | null;
  brief_created_at: string | null;
  coach: CoachAccount;
};

export async function getDashboard(day?: string) {
  const query = day ? `?day=${encodeURIComponent(day)}` : "";
  try {
    return await request<CoachDashboard>(`/api/coach/dashboard${query}`);
  } catch (error) {
    if (!serverMissing(error)) throw error;
    const [{ createClient }, { loadAccountDashboard }] = await Promise.all([
      import("@/utils/supabase/client"),
      import("@/lib/account-dashboard"),
    ]);
    return loadAccountDashboard(createClient(), day);
  }
}

export function syncRoster() {
  return request<{ synced: number; imported: number; updated: number; errors: string[] }>("/api/coach/sync", {
    method: "POST",
    body: "{}",
  });
}

export function getCoach() {
  return request<CoachAccount>("/api/coach");
}

export function updateCoach(body: Record<string, unknown>) {
  return request<CoachAccount>("/api/coach", { method: "PATCH", body: JSON.stringify(body) });
}

export function createBrief(day: string) {
  return request<{ status: string; created_at: string | null; report: CoachingBrief | null }>("/api/coach/brief", {
    method: "POST",
    body: JSON.stringify({ day }),
  });
}

export function deleteAthlete(athleteId: number) {
  return request<void>(`/api/athletes/${athleteId}`, { method: "DELETE" });
}

export function createRosterAthlete(displayName: string) {
  return request<Athlete>("/api/coach/athletes", {
    method: "POST",
    body: JSON.stringify({ display_name: displayName }),
  });
}

export function getAthleteById(athleteId: number) {
  return request<Athlete>(`/api/athletes/${athleteId}`);
}

export function updateAthleteById(athleteId: number, body: Record<string, unknown>) {
  return request<Athlete>(`/api/athletes/${athleteId}`, { method: "PATCH", body: JSON.stringify(body) });
}

export type MileageChart = {
  week_start: string;
  week_end: string;
  distance_miles: number | null;
  duration_seconds: number | null;
  elevation_feet: number | null;
  weeks: Array<{
    week_start: string;
    week_end: string;
    distance_miles: number | null;
    activity_count: number;
    current: boolean;
  }>;
  runs: Array<{
    garmin_activity_id: number;
    name: string | null;
    start_time_local: string | null;
    distance_miles: number | null;
    duration_seconds: number | null;
    elevation_feet: number | null;
  }>;
};

export type RunningStats = {
  last_4_weeks: {
    activities_per_week: number | null;
    distance_miles: number | null;
    duration_seconds: number | null;
    elevation_feet: number | null;
  };
  best_efforts: Array<{
    label: string;
    duration_seconds: number | null;
    garmin_activity_id: number | null;
    start_time_local: string | null;
  }>;
};

export async function getAthleteOverview(athleteId: number) {
  try {
    return await request<{
      athlete: Athlete;
      status: RosterAthlete | null;
      weekly_mileage: WeeklyMileage[];
      mileage_chart: MileageChart;
      running_stats: RunningStats;
      recent_workouts: Array<{
        garmin_activity_id: number;
        name: string | null;
        distance_meters: number | null;
        start_time_local: string | null;
        workout_type: string | null;
      }>;
      goal?: {
        primary_race_goal: string | null;
        goal_race_date: string | null;
        target_time: string | null;
      };
      races?: RaceEntry[];
    }>(`/api/athletes/${athleteId}/overview`);
  } catch (error) {
    if (!serverMissing(error)) throw error;
    const [{ createClient }, { loadStoredOverview }] = await Promise.all([
      import("@/utils/supabase/client"),
      import("@/lib/account-dashboard"),
    ]);
    return loadStoredOverview(createClient(), athleteId);
  }
}

export type PlanWeek = {
  week_start: string;
  in_progress: boolean;
  planned_miles: number | null;
  planned_miles_complete: boolean;
  actual_miles: number | null;
  variance_miles: number | null;
  variance_percent: number | null;
  planned_workouts: number;
  completed_workouts: number;
  partial_workouts: number;
  still_scheduled: number;
  confirmed_missed: number;
  unmatched: number;
  planned_quality: number;
  completed_quality: number;
  partial_quality: number;
  planned_long_run_miles: number | null;
  actual_long_run_miles: number | null;
  adherence: number | null;
};

export type PlannedWorkout = {
  id: number;
  scheduled_date: string;
  title: string;
  workout_type: string | null;
  distance_miles: number | null;
  warmup: string | null;
  cooldown: string | null;
  repetitions: number | null;
  rep_distance_miles: number | null;
  recovery_seconds: number | null;
  target_pace: string | null;
  intensity: string | null;
  coach_notes: string | null;
  details?: string | null;
  comparison?: Record<string, unknown> | null;
  feedback?: WorkoutFeedback | null;
  comments?: WorkoutNote[];
  status: string;
  execution: string | null;
  summary: string | null;
  match: { garmin_activity_id: number; name: string | null; source: string; distance_miles: number | null } | null;
  candidates: Array<{ garmin_activity_id: number; name: string | null; distance_miles: number | null }>;
  original_prescription: Record<string, unknown> | null;
  revisions: Array<{ created_at: string; prescription: Record<string, unknown> }>;
};

export type PlanView = {
  trend: string | null;
  weeks: PlanWeek[];
  workouts: PlannedWorkout[];
};

export async function getAthletePlan(athleteId: number) {
  try {
    return await request<PlanView>(`/api/athletes/${athleteId}/plan`);
  } catch (error) {
    if (!serverMissing(error)) throw error;
    const [{ createClient }, { loadStoredPlan }] = await Promise.all([
      import("@/utils/supabase/client"),
      import("@/lib/account-dashboard"),
    ]);
    return loadStoredPlan(createClient(), athleteId);
  }
}

export function addAthletePlan(athleteId: number, body: Record<string, unknown>) {
  return request<{ id: number }>(`/api/athletes/${athleteId}/plan`, { method: "POST", body: JSON.stringify(body) });
}

export function updateAthletePlan(athleteId: number, planId: number, body: Record<string, unknown>) {
  return request<{ id: number }>(`/api/athletes/${athleteId}/plan/${planId}`, { method: "PATCH", body: JSON.stringify(body) });
}

export function importAthletePlan(athleteId: number, body: { filename: string; text?: string; content_base64?: string }) {
  return request<{ created: number; errors: string[] }>(`/api/athletes/${athleteId}/plan/import`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export type ProgramImportResult = {
  created: number;
  replaced: number;
  source: string;
  start: string;
  end: string;
  notes: string[];
  workouts: Array<{ scheduled_date: string; title: string }>;
};

export function importTrainingProgram(
  athleteId: number,
  body: { filename?: string; text?: string; content_base64?: string; start_date?: string; request?: string },
) {
  return request<ProgramImportResult>(`/api/athletes/${athleteId}/plan/program`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function matchAthletePlan(athleteId: number, planId: number, body: { garmin_activity_id?: number | null; confirmed_missed?: boolean }) {
  return request<{ id: number }>(`/api/athletes/${athleteId}/plan/${planId}/match`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function syncGarmin() {
  return request<SyncJob>("/api/garmin/sync", {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export type WorkoutFeedback = {
  rpe: number | null;
  fatigue: number | null;
  soreness: number | null;
  comment: string | null;
};

export type WorkoutNote = {
  id: number;
  author: string;
  body: string;
  created_at: string;
};

export type PortalGarmin = {
  connected: boolean;
  status: string;
  key_saved: boolean;
  last_error: string | null;
  last_sync_at: string | null;
};

export type PortalStatus = {
  athlete: Athlete;
  intake_complete: boolean;
  garmin: PortalGarmin;
  coach_name: string;
  openai_configured: boolean;
};

export type PortalActivity = {
  garmin_activity_id: number;
  name: string | null;
  start_time_local: string | null;
  distance_miles: number | null;
  duration_seconds: number | null;
  pace_seconds_per_mile: number | null;
  average_heart_rate_bpm: number | null;
  manual: boolean;
  notes: string | null;
  workout_type?: string | null;
};

export type PortalHome = {
  today: string;
  name: string;
  workouts: PlannedWorkout[];
  activities: PortalActivity[];
  recent: PortalActivity[];
  week: PlanWeek | null;
  upcoming: PlannedWorkout[];
  goal: {
    primary_race_goal: string | null;
    goal_race_date: string | null;
    target_time: string | null;
  };
  garmin: PortalGarmin;
};

export type CalendarDay = {
  date: string;
  in_month: boolean;
  workouts: Array<{ id: number; title: string; details?: string | null; workout_type: string | null; status: string }>;
  activities: PortalActivity[];
};

export type RaceEntry = {
  id: number;
  name: string;
  race_date: string | null;
  distance_label: string | null;
  distance_meters: number | null;
  goal_time: string | null;
  result_time: string | null;
  notes: string | null;
};

export type AthleteGoals = {
  primary_race_goal: string | null;
  goal_race_date: string | null;
  target_time: string | null;
  races: RaceEntry[];
};

export type AthleteAnalytics = {
  weekly_mileage: WeeklyMileage[];
  monthly_mileage: Array<{ month: string; distance_miles: number }>;
  pace_trends: Array<{ week_start: string; pace_seconds_per_mile: number | null; runs: number }>;
  heart_rate: {
    easy_average_bpm: number | null;
    easy_count: number;
    workout_average_bpm: number | null;
    workout_count: number;
    window_days: number;
  };
  training_load: {
    weeks: Array<{ week_start: string; distance_miles: number | null }>;
    this_week_miles: number | null;
    previous_four_week_average: number | null;
    acute_chronic_ratio: number | null;
  };
  personal_records: {
    best_efforts: RunningStats["best_efforts"];
    races: RaceEntry[];
  };
  planned_vs_actual: PlannedWorkout[];
  lactate: Array<{
    id: number;
    measured_on: string;
    mmol: number;
    pace_seconds_per_mile: number | null;
    heart_rate_bpm: number | null;
    notes: string | null;
  }>;
  threshold: { pace_seconds_per_mile: number | null; heart_rate_bpm: number | null } | null;
  predictions: {
    source: { name: string; result_time: string | null; distance_label: string | null } | null;
    estimates: Array<{ label: string; time: string }>;
    note: string;
  };
};

export function joinAthlete(intake: AthleteIntake, athleteId?: number | null) {
  return request<PortalStatus>("/api/portal/join", {
    method: "POST",
    body: JSON.stringify({ intake, athlete_id: athleteId ?? null }),
  });
}

export function getPortal(athleteId: number) {
  return request<PortalStatus>(`/api/portal/${athleteId}`);
}

export function connectAthleteGarmin(athleteId: number, email: string, password: string, mfaCode?: string) {
  return request<PortalStatus & { sync?: SyncJob; mfa_required?: boolean }>(`/api/portal/${athleteId}/garmin`, {
    method: "POST",
    body: JSON.stringify({ email, password, mfa_code: mfaCode || null }),
  });
}

export function syncAthleteGarmin(athleteId: number) {
  return request<SyncJob>(`/api/portal/${athleteId}/garmin/sync`, { method: "POST", body: "{}" });
}

export function getAthleteHome(athleteId: number) {
  return request<PortalHome>(`/api/portal/${athleteId}/home`);
}

export function getPortalActivities(athleteId: number, limit = 20) {
  return request<{ activities: PortalActivity[] }>(`/api/portal/${athleteId}/activities?limit=${limit}`);
}

export function getAthleteCalendar(athleteId: number, month: string) {
  return request<{ month: string; today: string; days: CalendarDay[] }>(
    `/api/portal/${athleteId}/calendar?month=${encodeURIComponent(month)}`,
  );
}

export function getAthleteWeek(athleteId: number) {
  return request<PlanView & { today: string }>(`/api/portal/${athleteId}/week`);
}

export function getAthleteWorkout(athleteId: number, planId: number) {
  return request<PlannedWorkout>(`/api/portal/${athleteId}/workouts/${planId}`);
}

export function getPortalActivity(athleteId: number, garminActivityId: number) {
  return request<{
    activity: PortalActivity;
    planned: PlannedWorkout | null;
    feedback: WorkoutFeedback | null;
    comments: WorkoutNote[];
  }>(`/api/portal/${athleteId}/activities/${garminActivityId}`);
}

export function logManualActivity(athleteId: number, body: Record<string, unknown>) {
  return request<PortalActivity>(`/api/portal/${athleteId}/activities`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function editPortalActivity(athleteId: number, garminActivityId: number, body: Record<string, unknown>) {
  return request<PortalActivity>(`/api/portal/${athleteId}/activities/${garminActivityId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function saveWorkoutFeedback(athleteId: number, body: Record<string, unknown>) {
  return request<WorkoutFeedback>(`/api/portal/${athleteId}/feedback`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function addWorkoutComment(athleteId: number, body: Record<string, unknown>) {
  return request<WorkoutNote>(`/api/portal/${athleteId}/comments`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function getMessages(athleteId: number) {
  try {
    return await request<{ messages: WorkoutNote[] }>(`/api/portal/${athleteId}/messages`);
  } catch (error) {
    if (!serverMissing(error)) throw error;
    return { messages: [] };
  }
}

export function sendMessage(athleteId: number, author: "athlete" | "coach", body: string) {
  return request<WorkoutNote>(`/api/portal/${athleteId}/messages`, {
    method: "POST",
    body: JSON.stringify({ author, body }),
  });
}

export function matchPortalWorkout(athleteId: number, planId: number, garminActivityId: number | null) {
  return request<{ id: number }>(`/api/portal/${athleteId}/workouts/${planId}/match`, {
    method: "PATCH",
    body: JSON.stringify({ garmin_activity_id: garminActivityId }),
  });
}

export function getAthleteGoals(athleteId: number) {
  return request<AthleteGoals>(`/api/portal/${athleteId}/goals`);
}

export function saveAthleteGoal(athleteId: number, body: Record<string, unknown>) {
  return request<AthleteGoals>(`/api/portal/${athleteId}/goals`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function saveBestEffort(athleteId: number, label: string, durationSeconds: number | null) {
  return request<RunningStats>(`/api/athletes/${athleteId}/best-efforts`, {
    method: "PATCH",
    body: JSON.stringify({ label, duration_seconds: durationSeconds }),
  });
}

export function saveRace(athleteId: number, body: Record<string, unknown>, raceId?: number) {
  const path = raceId ? `/api/portal/${athleteId}/races/${raceId}` : `/api/portal/${athleteId}/races`;
  return request<RaceEntry>(path, { method: raceId ? "PATCH" : "POST", body: JSON.stringify(body) });
}

export function deleteRace(athleteId: number, raceId: number) {
  return request<void>(`/api/portal/${athleteId}/races/${raceId}`, { method: "DELETE" });
}

export function getAthleteAnalytics(athleteId: number) {
  return request<AthleteAnalytics>(`/api/portal/${athleteId}/analytics`);
}

export function saveLactate(athleteId: number, body: Record<string, unknown>) {
  return request<AthleteAnalytics["lactate"][number]>(`/api/portal/${athleteId}/lactate`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function askAthleteAssistant(athleteId: number, message: string, conversationId: number | null) {
  return request<{ conversation_id: number; messages: ChatMessage[] }>(`/api/portal/${athleteId}/assistant`, {
    method: "POST",
    body: JSON.stringify({ message, conversation_id: conversationId, garmin_activity_id: null }),
  });
}
