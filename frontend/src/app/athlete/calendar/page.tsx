"use client";

import Link from "next/link";
import { ChevronDown, ChevronLeft, ChevronRight } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { AthleteTrainingPlan } from "@/components/athlete-training-plan";
import { AthleteWeekEditor } from "@/components/athlete-week-editor";
import { useAthlete } from "@/components/athlete-frame";
import { errorMessage, getAthleteCalendar, type CalendarDay } from "@/lib/api";

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function shiftMonth(month: string, delta: number): string {
  const [year, monthNumber] = month.split("-").map(Number);
  const date = new Date(year, (monthNumber || 1) - 1 + delta, 1);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
}

export default function AthleteCalendarPage() {
  const { athleteId } = useAthlete();
  const [month, setMonth] = useState(() => {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
  });
  const [days, setDays] = useState<CalendarDay[]>([]);
  const [today, setToday] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<"calendar" | "week">("week");
  const [planOpen, setPlanOpen] = useState(false);

  const load = useCallback(async (value: string) => {
    const calendar = await getAthleteCalendar(athleteId, value);
    setDays(calendar.days);
    setToday(calendar.today);
    setMonth(calendar.month);
  }, [athleteId]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void load(month).catch((loadError: unknown) => setError(errorMessage(loadError)));
    }, 0);
    return () => window.clearTimeout(timer);
  }, [load, month]);

  useEffect(() => {
    if (window.location.hash === "#training-plan") setPlanOpen(true);
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="font-heading text-2xl tracking-tight sm:text-3xl">Calendar</h1>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-3">
          <div className="grid grid-cols-2 rounded-lg border border-border p-1 sm:flex">
            <button
              type="button"
              aria-pressed={mode === "calendar"}
              onClick={() => setMode("calendar")}
              className={`min-h-11 rounded-md px-3 text-sm sm:min-h-0 sm:py-1.5 ${mode === "calendar" ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted"}`}
            >
              Calendar
            </button>
            <button
              type="button"
              aria-pressed={mode === "week"}
              onClick={() => setMode("week")}
              className={`min-h-11 rounded-md px-3 text-sm sm:min-h-0 sm:py-1.5 ${mode === "week" ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted"}`}
            >
              Week
            </button>
          </div>
          {mode === "calendar" ? (
            <div className="flex items-center justify-between gap-2 sm:justify-start">
              <button type="button" aria-label="Previous month" onClick={() => setMonth((current) => shiftMonth(current, -1))} className="inline-flex size-11 items-center justify-center rounded-full border border-border">
                <ChevronLeft className="size-4" />
              </button>
              <p className="min-w-28 text-center text-sm">{month}</p>
              <button type="button" aria-label="Next month" onClick={() => setMonth((current) => shiftMonth(current, 1))} className="inline-flex size-11 items-center justify-center rounded-full border border-border">
                <ChevronRight className="size-4" />
              </button>
            </div>
          ) : null}
        </div>
      </div>
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      {mode === "week" ? <AthleteWeekEditor athleteId={athleteId} /> : (
      <>
      <div className="grid grid-cols-7 gap-1 text-center text-[10px] tracking-wide text-muted-foreground uppercase sm:gap-2 sm:text-xs">
        {WEEKDAYS.map((day) => (
          <div key={day}>
            <span className="sm:hidden">{day.slice(0, 1)}</span>
            <span className="hidden sm:inline">{day}</span>
          </div>
        ))}
      </div>
      <div className="grid grid-cols-7 gap-1 sm:gap-2">
        {days.map((day) => (
          <div key={day.date} className={`min-h-20 rounded-lg border p-1 text-[10px] leading-tight sm:min-h-28 sm:rounded-xl sm:p-2 sm:text-xs ${day.date === today ? "border-primary" : "border-border"} ${day.in_month ? "bg-card" : "opacity-50"}`}>
            <p className="font-medium">{Number(day.date.slice(8))}</p>
            <div className="mt-1 space-y-1">
              {day.workouts.map((workout) => (
                <Link key={workout.id} href={`/athlete/workouts/${workout.id}`} className="block rounded bg-muted px-1 py-0.5 hover:underline">
                  <span className="line-clamp-2 whitespace-pre-wrap sm:line-clamp-4">{workout.details?.trim() || workout.title}</span>
                </Link>
              ))}
              {day.activities.map((activity) => (
                <Link key={activity.garmin_activity_id} href={`/athlete/activities/${activity.garmin_activity_id}`} className="block truncate text-muted-foreground hover:underline">
                  {activity.distance_miles == null ? activity.name || "Run" : `${activity.distance_miles.toFixed(1)} mi`}
                </Link>
              ))}
            </div>
          </div>
        ))}
      </div>
      </>
      )}
      <details
        id="training-plan"
        open={planOpen}
        onToggle={(event) => setPlanOpen(event.currentTarget.open)}
        className="group rounded-xl border border-border bg-card"
      >
        <summary className="flex min-h-14 cursor-pointer list-none items-center justify-between gap-3 px-4 py-4 [&::-webkit-details-marker]:hidden">
          <span className="font-heading text-xl tracking-tight">Training plan</span>
          <ChevronDown className="size-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-180" />
        </summary>
        {planOpen ? (
          <div className="border-t border-border px-3 py-4 sm:px-4">
            <AthleteTrainingPlan athleteId={athleteId} />
          </div>
        ) : null}
      </details>
    </div>
  );
}
