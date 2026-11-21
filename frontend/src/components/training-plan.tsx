"use client";

import Link from "next/link";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { StatusPill } from "@/components/status-pill";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { hasAccount, mirrorPlanIfEmpty } from "@/lib/account";
import { errorMessage, getAthletePlan, matchAthletePlan, type PlanView, type PlannedWorkout } from "@/lib/api";

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

export function TrainingPlan({ athleteId }: { athleteId: number }) {
  const [view, setView] = useState<PlanView | null>(null);
  const [week, setWeek] = useState<string | null>(null);
  const [day, setDay] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const plan = await getAthletePlan(athleteId);
    setView(plan);
    setWeek((current) => current ?? plan.weeks.find((item) => item.in_progress)?.week_start ?? plan.weeks.at(-1)?.week_start ?? null);
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

  async function onMatch(workout: PlannedWorkout, value: string) {
    if (value === "missed") {
      await matchAthletePlan(athleteId, workout.id, { confirmed_missed: true });
    } else if (value === "auto") {
      await matchAthletePlan(athleteId, workout.id, { garmin_activity_id: null });
    } else {
      await matchAthletePlan(athleteId, workout.id, { garmin_activity_id: Number(value) });
    }
    await load();
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
            <div className="h-56 w-full">
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
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => shiftWeek(-1)}
              className="rounded-full border border-border p-2 text-muted-foreground hover:bg-muted"
              aria-label="Previous week"
            >
              <ChevronLeft className="size-4" />
            </button>
            <div className="grid flex-1 grid-cols-7 gap-2">
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
                    className={`mx-auto flex size-14 flex-col items-center justify-center rounded-full border text-center sm:size-16 ${
                      active ? "border-primary bg-primary text-primary-foreground" : "border-border bg-card text-foreground hover:bg-muted"
                    }`}
                  >
                    <span className="text-[10px] tracking-wide uppercase sm:text-[11px]">{WEEKDAYS[index]}</span>
                    <span className="text-sm font-medium sm:text-base">{date.getDate()}</span>
                    <span className={`mt-0.5 size-1 rounded-full ${hasWorkout ? (active ? "bg-primary-foreground" : "bg-primary") : "bg-transparent"}`} />
                  </button>
                );
              })}
            </div>
            <button
              type="button"
              onClick={() => shiftWeek(1)}
              className="rounded-full border border-border p-2 text-muted-foreground hover:bg-muted"
              aria-label="Next week"
            >
              <ChevronRight className="size-4" />
            </button>
          </div>
          <p className="text-xs tracking-[0.16em] text-muted-foreground uppercase">{dayLabel(selectedDay)}</p>
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
              <select
                value={workout.match?.source === "manual" ? String(workout.match.garmin_activity_id) : workout.status === "confirmed_missed" ? "missed" : "auto"}
                onChange={(event) => void onMatch(workout, event.target.value)}
                className="h-8 rounded-lg border border-input bg-card px-2 text-xs"
              >
                <option value="auto">Automatic match</option>
                <option value="missed">Confirm missed</option>
                {workout.candidates.map((candidate) => (
                  <option key={candidate.garmin_activity_id} value={candidate.garmin_activity_id}>
                    {candidate.name || "Activity"}{candidate.distance_miles == null ? "" : ` · ${candidate.distance_miles.toFixed(2)} mi`}
                  </option>
                ))}
              </select>
              {workout.revisions.length > 0 ? <span className="text-xs text-muted-foreground">{workout.revisions.length} earlier version{workout.revisions.length === 1 ? "" : "s"} kept</span> : null}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
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
