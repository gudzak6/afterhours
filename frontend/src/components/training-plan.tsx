"use client";

import Link from "next/link";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { StatusPill } from "@/components/status-pill";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { hasAccount, mirrorPlanIfEmpty, mirrorWorkout } from "@/lib/account";
import { errorMessage, getAthletePlan, updateAthletePlan, type PlanView, type PlanWeek, type PlannedWorkout } from "@/lib/api";

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const WORKOUT_TYPES = ["easy", "recovery", "long_run", "intervals", "threshold", "tempo", "marathon_pace", "strides", "progression", "race", "other"];
const fieldClass = "mt-1 w-full rounded-lg border border-input bg-card px-3 py-2 text-sm";

type WorkoutForm = {
  scheduled_date: string;
  title: string;
  details: string;
  workout_type: string;
  distance_miles: string;
  target_pace: string;
  coach_notes: string;
};

export function TrainingPlan({ athleteId }: { athleteId: number }) {
  const [view, setView] = useState<PlanView | null>(null);
  const [week, setWeek] = useState<string | null>(null);
  const [day, setDay] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<WorkoutForm | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (focusDay?: string) => {
    const plan = await getAthletePlan(athleteId);
    setView(plan);
    const today = todayIso();
    setWeek((current) => (focusDay ? weekFor(plan.weeks, focusDay) ?? current : current ?? weekFor(plan.weeks, today)));
    setDay((current) => {
      if (focusDay) return focusDay;
      if (current) return current;
      const start = weekFor(plan.weeks, today);
      if (!start) return null;
      if (today >= start && today < addDays(start, 7)) return today;
      const first = plan.workouts.find((workout) => workout.scheduled_date >= start && workout.scheduled_date < addDays(start, 7));
      return first?.scheduled_date ?? start;
    });
    if (await hasAccount()) {
      try {
        await mirrorPlanIfEmpty(athleteId, plan.workouts);
      } catch {
        // The local plan still renders. Saving a workout reports an account error.
      }
    }
  }, [athleteId]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void load().catch((loadError: unknown) => setError(errorMessage(loadError)));
    }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  function openEdit(workout: PlannedWorkout) {
    setEditingId(workout.id);
    setForm({
      scheduled_date: workout.scheduled_date,
      title: workout.title,
      details: workout.details ?? "",
      workout_type: workout.workout_type ?? "",
      distance_miles: workout.distance_miles == null ? "" : String(Math.round(workout.distance_miles * 100) / 100),
      target_pace: workout.target_pace ?? "",
      coach_notes: workout.coach_notes ?? "",
    });
    setError(null);
  }

  async function onSave(event: FormEvent, workout: PlannedWorkout) {
    event.preventDefault();
    if (!form) return;
    const title = form.title.trim();
    if (!title) {
      setError("A workout needs a name.");
      return;
    }
    const distance = form.distance_miles.trim();
    const miles = distance === "" ? null : Number(distance);
    if (miles != null && !Number.isFinite(miles)) {
      setError("Distance needs to be a number of miles.");
      return;
    }
    const body = {
      scheduled_date: form.scheduled_date,
      title,
      details: form.details.trim() || null,
      workout_type: form.workout_type || null,
      distance_miles: miles,
      target_pace: form.target_pace.trim() || null,
      coach_notes: form.coach_notes.trim() || null,
      warmup: workout.warmup,
      cooldown: workout.cooldown,
      repetitions: workout.repetitions,
      rep_distance_miles: workout.rep_distance_miles,
      recovery_seconds: workout.recovery_seconds,
      intensity: workout.intensity,
    };
    setSaving(true);
    setError(null);
    try {
      await updateAthletePlan(athleteId, workout.id, body);
      if (await hasAccount()) {
        try {
          await mirrorWorkout(athleteId, workout.id, body, true);
        } catch {
          // The coaching plan is saved. The account copy can catch up on the next visit.
        }
      }
      setEditingId(null);
      setForm(null);
      await load(body.scheduled_date);
    } catch (saveError: unknown) {
      setError(errorMessage(saveError));
    } finally {
      setSaving(false);
    }
  }

  const selected = view?.weeks.find((item) => item.week_start === week) ?? null;
  const visible = view?.workouts.filter((workout) => {
    if (!selected) return true;
    return workout.scheduled_date >= selected.week_start && workout.scheduled_date < addDays(selected.week_start, 7);
  }) ?? [];
  const days = selected ? WEEKDAYS.map((_, index) => addDays(selected.week_start, index)) : [];
  const selectedDay = day && days.includes(day) ? day : days.find((item) => visible.some((workout) => workout.scheduled_date === item)) ?? days[0] ?? null;
  const dayWorkouts = selectedDay ? visible.filter((workout) => workout.scheduled_date === selectedDay) : visible;

  function showWeek(weekStart: string) {
    setWeek(weekStart);
    const workouts = view?.workouts.filter((workout) => workout.scheduled_date >= weekStart && workout.scheduled_date < addDays(weekStart, 7)) ?? [];
    setDay(workouts[0]?.scheduled_date ?? weekStart);
  }

  function shiftWeek(delta: number) {
    if (!view || !week) return;
    const index = view.weeks.findIndex((item) => item.week_start === week);
    const next = view.weeks[index + delta];
    if (next) showWeek(next.week_start);
  }
  const points = (view?.weeks ?? []).map((item) => ({
    label: item.week_start.slice(5),
    planned: item.planned_miles,
    actual: item.actual_miles,
  }));

  return (
    <div className="space-y-4">
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      <Card>
        <CardHeader>
          <CardTitle>Planned and actual mileage</CardTitle>
          <CardDescription>{view?.trend || "Mileage variance is shown only when every workout that week has a prescribed distance."}</CardDescription>
        </CardHeader>
        <CardContent>
          {points.length === 0 ? (
            <p className="text-sm text-muted-foreground">Add workouts to compare the block with Garmin mileage.</p>
          ) : (
            <div className="h-56 w-full min-w-0">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={points}>
                  <CartesianGrid vertical={false} stroke="oklch(0.88 0.02 80)" />
                  <XAxis dataKey="label" tickLine={false} axisLine={false} />
                  <YAxis tickLine={false} axisLine={false} width={36} />
                  <Tooltip formatter={(value) => [`${Number(value).toFixed(1)} mi`, ""]} />
                  <Bar dataKey="planned" fill="oklch(0.75 0.04 80)" radius={[6, 6, 0, 0]} />
                  <Bar dataKey="actual" fill="oklch(0.5 0.13 42)" radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </CardContent>
      </Card>

      {selected && selectedDay ? (
        <div className="space-y-4">
          <div className="flex max-w-xl items-center justify-between gap-2">
            <button
              type="button"
              onClick={() => shiftWeek(-1)}
              className="inline-flex size-11 shrink-0 items-center justify-center rounded-full border border-border text-muted-foreground hover:bg-muted"
              aria-label="Previous week"
            >
              <ChevronLeft className="size-4" />
            </button>
            <p className="min-w-0 text-center text-xs tracking-[0.08em] text-muted-foreground uppercase sm:tracking-[0.16em]">{dayLabel(selectedDay)}</p>
            <button
              type="button"
              onClick={() => shiftWeek(1)}
              className="inline-flex size-11 shrink-0 items-center justify-center rounded-full border border-border text-muted-foreground hover:bg-muted"
              aria-label="Next week"
            >
              <ChevronRight className="size-4" />
            </button>
          </div>
          <div className="grid max-w-xl grid-cols-7 gap-1 sm:gap-2">
              {days.map((item, index) => {
                const date = parseDay(item);
                const active = item === selectedDay;
                const hasWorkout = visible.some((workout) => workout.scheduled_date === item);
                return (
                  <button
                    key={item}
                    type="button"
                    onClick={() => setDay(item)}
                    aria-pressed={active}
                    className={`mx-auto flex aspect-square w-full max-w-12 flex-col items-center justify-center rounded-full border text-center ${
                      active ? "border-primary bg-primary text-primary-foreground" : "border-border bg-card text-foreground hover:bg-muted"
                    }`}
                  >
                    <span className="text-[9px] leading-none tracking-wide uppercase max-[380px]:hidden sm:text-[10px]">{WEEKDAYS[index]}</span>
                    <span className="text-[10px] leading-none uppercase min-[381px]:hidden">{WEEKDAYS[index].slice(0, 1)}</span>
                    <span className="text-xs font-medium leading-none sm:text-sm">{date.getDate()}</span>
                    <span className={`mt-0.5 size-1 rounded-full ${hasWorkout ? (active ? "bg-primary-foreground" : "bg-primary") : "bg-transparent"}`} />
                  </button>
                );
              })}
          </div>
        </div>
      ) : null}

      {selected ? (
        <Card>
          <CardHeader>
            <CardTitle>Week of {selected.week_start}</CardTitle>
            <CardDescription>
              {selected.in_progress
                ? `${selected.completed_workouts} completed so far, ${selected.still_scheduled} still scheduled.`
                : `${selected.completed_workouts} of ${selected.planned_workouts} workouts completed.`}
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-2 text-sm sm:grid-cols-2">
            <p>Planned mileage: {selected.planned_miles == null ? "—" : `${selected.planned_miles.toFixed(1)} mi`}</p>
            <p>Actual mileage: {selected.actual_miles == null ? "—" : `${selected.actual_miles.toFixed(1)} mi`}</p>
            <p>Variance: {selected.variance_miles == null ? "Not calculated" : `${selected.variance_miles.toFixed(1)} mi (${selected.variance_percent?.toFixed(0)}%)`}</p>
            <p>Quality sessions: {selected.completed_quality} completed, {selected.partial_quality} partial, of {selected.planned_quality}</p>
            <p>Long run: {selected.planned_long_run_miles == null ? "—" : `${selected.planned_long_run_miles.toFixed(1)} planned`}{selected.actual_long_run_miles == null ? "" : ` · ${selected.actual_long_run_miles.toFixed(1)} actual`}</p>
            <p>Unmatched {selected.unmatched} · Confirmed missed {selected.confirmed_missed}</p>
          </CardContent>
        </Card>
      ) : null}

      {selectedDay && dayWorkouts.length === 0 ? <p className="text-sm text-muted-foreground">No workout is scheduled for {dayLabel(selectedDay)}.</p> : null}
      <ul className="space-y-3">
        {dayWorkouts.map((workout) => (
          <li key={workout.id} className="rounded-xl border border-border p-3 text-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="font-medium">{workout.scheduled_date} · {workout.title}</p>
                {workout.details ? (
                  <p className="mt-1 whitespace-pre-wrap text-muted-foreground">{workout.details}</p>
                ) : (
                  <p className="text-muted-foreground">
                    {(workout.workout_type || "unspecified").replaceAll("_", " ")}
                    {workout.distance_miles == null ? "" : ` · ${workout.distance_miles.toFixed(2)} mi`}
                    {workout.repetitions == null ? "" : ` · ${workout.repetitions} reps`}
                    {workout.target_pace ? ` · ${workout.target_pace}/mi` : ""}
                  </p>
                )}
              </div>
              <StatusPill status={workout.status} />
            </div>
            {workout.summary ? <p className="mt-2">{workout.summary}</p> : null}
            {workout.match ? (
              <p className="mt-1 text-muted-foreground">
                Matched {workout.match.source}: {" "}
                <Link href={`/activities/${workout.match.garmin_activity_id}`} className="hover:underline">{workout.match.name || "Activity"}</Link>
              </p>
            ) : null}
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <Button type="button" variant="outline" size="sm" onClick={() => openEdit(workout)}>
                Edit workout
              </Button>
              {workout.revisions.length > 0 ? <span className="text-xs text-muted-foreground">{workout.revisions.length} earlier version{workout.revisions.length === 1 ? "" : "s"} kept</span> : null}
            </div>
            {editingId === workout.id && form ? (
              <form onSubmit={(event) => void onSave(event, workout)} className="mt-3 grid gap-3 border-t border-border pt-3 sm:grid-cols-2">
                <label className="text-sm">Date
                  <input type="date" required value={form.scheduled_date} onChange={(event) => setForm({ ...form, scheduled_date: event.target.value })} className={fieldClass} />
                </label>
                <label className="text-sm">Name
                  <input required value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} className={fieldClass} />
                </label>
                <label className="text-sm">Type
                  <select value={form.workout_type} onChange={(event) => setForm({ ...form, workout_type: event.target.value })} className={fieldClass}>
                    <option value="">Unspecified</option>
                    {(form.workout_type && !WORKOUT_TYPES.includes(form.workout_type) ? [form.workout_type, ...WORKOUT_TYPES] : WORKOUT_TYPES).map((type) => (
                      <option key={type} value={type}>{type.replaceAll("_", " ")}</option>
                    ))}
                  </select>
                </label>
                <label className="text-sm">Distance, miles
                  <input value={form.distance_miles} onChange={(event) => setForm({ ...form, distance_miles: event.target.value })} inputMode="decimal" className={fieldClass} />
                </label>
                <label className="text-sm">Target pace
                  <input value={form.target_pace} onChange={(event) => setForm({ ...form, target_pace: event.target.value })} placeholder="8:00" className={fieldClass} />
                </label>
                <label className="text-sm sm:col-span-2">Prescription
                  <textarea value={form.details} onChange={(event) => setForm({ ...form, details: event.target.value })} className={`${fieldClass} min-h-24`} />
                </label>
                <label className="text-sm sm:col-span-2">Coach notes
                  <textarea value={form.coach_notes} onChange={(event) => setForm({ ...form, coach_notes: event.target.value })} className={`${fieldClass} min-h-16`} />
                </label>
                <div className="flex gap-2 sm:col-span-2">
                  <Button type="submit" disabled={saving}>{saving ? "Saving" : "Save workout"}</Button>
                  <Button type="button" variant="outline" onClick={() => { setEditingId(null); setForm(null); }}>Cancel</Button>
                </div>
              </form>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}

function todayIso() {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

function weekFor(weeks: PlanWeek[], day: string) {
  const current = weeks.find((item) => item.week_start <= day && addDays(item.week_start, 7) > day);
  if (current) return current.week_start;
  const upcoming = weeks.find((item) => item.week_start > day);
  if (upcoming) return upcoming.week_start;
  return weeks.at(-1)?.week_start ?? null;
}

function parseDay(iso: string): Date {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(year, (month || 1) - 1, day || 1);
}

function dayLabel(iso: string): string {
  const date = parseDay(iso);
  const weekday = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][date.getDay()];
  return `${weekday}, ${MONTHS[date.getMonth()]} ${date.getDate()}`;
}

function addDays(iso: string, days: number) {
  const [year, month, day] = iso.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}
