"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useAthlete } from "@/components/athlete-frame";
import { milesLabel, planText } from "@/components/athlete-ui";
import { errorMessage, getAthleteWeek, type PlanView, type PlannedWorkout, type PlanWeek } from "@/lib/api";

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export default function AthleteWeekPage() {
  const { athleteId } = useAthlete();
  const [view, setView] = useState<(PlanView & { today: string }) | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setView(await getAthleteWeek(athleteId));
  }, [athleteId]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void load().catch((loadError: unknown) => setError(errorMessage(loadError)));
    }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  const weeks = view?.weeks ?? [];

  return (
    <div className="space-y-4">
      <div>
        <h1 className="font-heading text-4xl tracking-tight">Training plan</h1>
        <p className="mt-2 text-sm text-muted-foreground">Each week is shown the way it was written in the uploaded spreadsheet.</p>
      </div>
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      {weeks.length === 0 ? <p className="text-sm text-muted-foreground">No plan is uploaded yet.</p> : null}
      {weeks.length > 0 ? (
        <div className="overflow-x-auto rounded-xl border border-border bg-card">
          <table className="w-full min-w-[64rem] border-collapse text-sm">
            <thead>
              <tr className="border-b border-border text-left text-[11px] tracking-wide text-muted-foreground uppercase">
                <th className="px-3 py-2 font-medium">Week</th>
                {WEEKDAYS.map((day) => (
                  <th key={day} className="px-3 py-2 font-medium">{day}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {weeks.map((week) => (
                <WeekRow key={week.week_start} week={week} workouts={view?.workouts ?? []} today={view?.today ?? null} />
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}

function WeekRow({ week, workouts, today }: { week: PlanWeek; workouts: PlannedWorkout[]; today: string | null }) {
  const start = week.week_start;
  return (
    <tr className={`border-b border-border align-top last:border-b-0 ${week.in_progress ? "bg-muted/40" : ""}`}>
      <th className="w-28 px-3 py-3 text-left font-medium">
        {start.slice(5)}
        <p className="mt-1 text-xs font-normal text-muted-foreground">{milesLabel(week.actual_miles)} of {milesLabel(week.planned_miles)}</p>
      </th>
      {WEEKDAYS.map((_, index) => {
        const day = addDays(start, index);
        const sessions = workouts.filter((workout) => workout.scheduled_date === day);
        return (
          <td key={day} className={`px-2 py-3 ${day === today ? "bg-primary/5" : ""}`}>
            <div className="space-y-2">
              {sessions.map((workout) => (
                <Link key={workout.id} href={`/athlete/workouts/${workout.id}`} className="block rounded-lg px-1 py-1 hover:bg-muted">
                  <p className="whitespace-pre-wrap">{planText(workout)}</p>
                  <p className="mt-1 text-[11px] tracking-wide text-muted-foreground uppercase">{workout.status.replaceAll("_", " ")}</p>
                </Link>
              ))}
            </div>
          </td>
        );
      })}
    </tr>
  );
}

function addDays(iso: string, days: number): string {
  const [year, month, day] = iso.split("-").map(Number);
  const date = new Date(Date.UTC(year, (month || 1) - 1, day || 1));
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}
