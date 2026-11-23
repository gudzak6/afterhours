"use client";

import Link from "next/link";
import { Calendar, ChevronDown, ChevronLeft, ChevronRight, CircleCheck, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useAthlete } from "@/components/athlete-frame";
import { durationLabel, milesLabel, paceLabel } from "@/components/athlete-ui";
import {
  errorMessage,
  getAthleteCalendar,
  getAthleteWeek,
  getPortalActivities,
  syncAthleteGarmin,
  type CalendarDay,
  type PortalActivity,
} from "@/lib/api";
import { formatWhen } from "@/lib/format";

const SCHEDULE_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

function parseDay(iso: string): Date {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(year, (month || 1) - 1, day || 1);
}

function isoDay(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

function shiftDay(iso: string, days: number): string {
  const date = parseDay(iso);
  date.setDate(date.getDate() + days);
  return isoDay(date);
}

function mondayOf(iso: string): string {
  return shiftDay(iso, -((parseDay(iso).getDay() + 6) % 7));
}

function weekRangeLabel(start: string): string {
  const begin = parseDay(start);
  const end = parseDay(shiftDay(start, 6));
  const left = `${MONTHS[begin.getMonth()].slice(0, 3)} ${begin.getDate()}`;
  const right = begin.getMonth() === end.getMonth() ? String(end.getDate()) : `${MONTHS[end.getMonth()].slice(0, 3)} ${end.getDate()}`;
  return `${left} – ${right}`;
}

function fullDayLabel(iso: string): string {
  const date = parseDay(iso);
  return `${WEEKDAYS[date.getDay()]}, ${MONTHS[date.getMonth()]} ${date.getDate()}`;
}

function completedLine(activity: PortalActivity) {
  const miles = activity.distance_miles == null ? "Run" : `${activity.distance_miles.toFixed(2)} mi`;
  const pace = paceLabel(activity.pace_seconds_per_mile);
  const type = activity.workout_type?.replaceAll("_", " ");
  if (pace === "—") return type ? `${miles} ${type}` : miles;
  return type ? `${miles} ${type} · ${pace}` : `${miles} · ${pace}`;
}

export default function AthleteHomePage() {
  const { athleteId, status, openGarmin } = useAthlete();
  const [days, setDays] = useState<Map<string, CalendarDay>>(new Map());
  const [milesById, setMilesById] = useState<Map<number, number | null>>(new Map());
  const [recent, setRecent] = useState<PortalActivity[]>([]);
  const [today, setToday] = useState<string | null>(null);
  const [selectedDay, setSelectedDay] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [syncing, setSyncing] = useState(false);

  const loadWeek = useCallback(async (day: string) => {
    const start = mondayOf(day);
    const months = [...new Set([start.slice(0, 7), shiftDay(start, 6).slice(0, 7)])];
    const [calendars, plan, runs] = await Promise.all([
      Promise.all(months.map((month) => getAthleteCalendar(athleteId, month))),
      getAthleteWeek(athleteId),
      getPortalActivities(athleteId, 8),
    ]);
    const nextDays = new Map<string, CalendarDay>();
    let knownToday = day;
    for (const calendar of calendars) {
      knownToday = calendar.today;
      for (const item of calendar.days) nextDays.set(item.date, item);
    }
    const miles = new Map<number, number | null>();
    for (const workout of plan.workouts) miles.set(workout.id, workout.distance_miles);
    setDays(nextDays);
    setMilesById(miles);
    setRecent(runs.activities);
    setToday(knownToday);
    setSelectedDay((current) => current ?? knownToday);
    setReady(true);
  }, [athleteId]);

  useEffect(() => {
    const now = new Date();
    const month = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
    const timer = window.setTimeout(() => {
      void loadWeek(`${month}-01`).catch((loadError: unknown) => setError(errorMessage(loadError)));
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadWeek]);

  async function showDay(day: string) {
    setSelectedDay(day);
    const start = mondayOf(day);
    const covered = days.has(start) && days.has(shiftDay(start, 6));
    if (covered) return;
    setError(null);
    try {
      await loadWeek(day);
      setSelectedDay(day);
    } catch (loadError) {
      setError(errorMessage(loadError));
    }
  }

  async function onSync() {
    if (!status.garmin.key_saved) {
      window.sessionStorage.removeItem("trainingcoach-garmin-skipped");
      openGarmin();
      return;
    }
    if (!selectedDay) return;
    setSyncing(true);
    setError(null);
    try {
      await syncAthleteGarmin(athleteId);
      await loadWeek(selectedDay);
      setSelectedDay(selectedDay);
    } catch (syncError) {
      setError(errorMessage(syncError));
    } finally {
      setSyncing(false);
    }
  }

  const day = selectedDay ?? today;
  const weekStart = day ? mondayOf(day) : null;
  const weekReady = weekStart != null && days.has(weekStart) && days.has(shiftDay(weekStart, 6));
  const weekDays = weekStart ? SCHEDULE_DAYS.map((_, index) => shiftDay(weekStart, index)) : [];
  const selected = day ? days.get(day) : undefined;
  const planned = selected?.workouts ?? [];
  const completed = selected?.activities ?? [];
  const marked = new Set(weekDays.filter((item) => (days.get(item)?.workouts.length ?? 0) > 0));
  const statusLabel = planned.length > 0 && completed.length > 0 ? "Completed" : planned.length > 0 ? "Planned" : null;
  const statusClass = statusLabel === "Completed" ? "text-emerald-700" : "text-amber-700";

  return (
    <div className="space-y-4">
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      {!ready && !error ? <p className="text-sm text-muted-foreground">Loading your week…</p> : null}
      {ready && weekStart && day ? (
        <section className="rounded-xl border border-border bg-card px-3 py-3 sm:px-4">
          <div className="flex flex-col gap-3 md:grid md:grid-cols-[auto_minmax(0,1fr)_auto] md:items-center md:gap-4">
            <h1 className="font-heading text-xl tracking-tight">Your training week</h1>
            <div className="flex items-center justify-between gap-3 sm:justify-center">
              <button
                type="button"
                onClick={() => void showDay(shiftDay(day, -7))}
                className="inline-flex size-10 shrink-0 items-center justify-center rounded-full border border-border text-muted-foreground hover:bg-muted"
                aria-label="Previous week"
              >
                <ChevronLeft className="size-4" />
              </button>
              <p className="min-w-28 text-center text-sm font-medium">{weekRangeLabel(weekStart)}</p>
              <button
                type="button"
                onClick={() => void showDay(shiftDay(day, 7))}
                className="inline-flex size-10 shrink-0 items-center justify-center rounded-full border border-border text-muted-foreground hover:bg-muted"
                aria-label="Next week"
              >
                <ChevronRight className="size-4" />
              </button>
            </div>
            <button
              type="button"
              onClick={() => void onSync()}
              disabled={syncing}
              className="inline-flex h-10 items-center justify-center gap-1.5 rounded-full border border-border px-3 text-sm text-muted-foreground hover:bg-muted disabled:opacity-60 md:justify-self-end"
            >
              <RefreshCw className={`size-3.5 ${syncing ? "animate-spin" : ""}`} />
              {syncing ? "Syncing" : status.garmin.key_saved ? "Sync runs" : "Connect Garmin"}
            </button>
          </div>
          <div className="mt-3 grid grid-cols-7 gap-1.5 sm:gap-3">
            {weekDays.map((item, index) => {
              const date = parseDay(item);
              const selectedDayActive = item === day;
              return (
                <button
                  key={item}
                  type="button"
                  onClick={() => void showDay(item)}
                  aria-pressed={selectedDayActive}
                  aria-label={`${SCHEDULE_DAYS[index]} ${date.getDate()}${marked.has(item) ? ", workout planned" : ""}`}
                  className={`flex min-h-16 flex-col items-center justify-center gap-1 rounded-lg border px-1 py-2 ${
                    selectedDayActive
                      ? "border-primary bg-primary text-primary-foreground"
                      : "border-border bg-background text-foreground hover:bg-muted"
                  }`}
                >
                  <span className="text-[10px] tracking-wide uppercase sm:text-xs">{SCHEDULE_DAYS[index]}</span>
                  <span className="text-base leading-none font-medium sm:text-lg">{date.getDate()}</span>
                  <span className={`size-1.5 rounded-full ${marked.has(item) ? (selectedDayActive ? "bg-primary-foreground" : "bg-primary") : "invisible"}`} />
                </button>
              );
            })}
          </div>
          <div className="mt-3 space-y-3 border-t border-border pt-3">
            <p className="text-sm text-muted-foreground">
              {fullDayLabel(day)}
              {weekReady && statusLabel ? <span className={`ml-2 ${statusClass}`}>{statusLabel}</span> : null}
            </p>
            {!weekReady ? <p className="text-sm text-muted-foreground">Loading this week…</p> : null}
            {weekReady ? <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-2">
                <p className="flex items-center gap-2 text-xs tracking-[0.14em] text-muted-foreground uppercase">
                  <Calendar className="size-3.5" />
                  Planned
                </p>
                {planned.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No workout assigned</p>
                ) : planned.map((workout) => {
                  const miles = milesById.get(workout.id);
                  return (
                    <Link key={workout.id} href={`/athlete/workouts/${workout.id}`} className="block rounded-lg border border-border bg-background px-2.5 py-2 hover:bg-muted">
                      <span className="block text-sm font-medium">{workout.title}</span>
                      {miles != null ? <span className="block text-xs text-muted-foreground">{miles.toFixed(2)} mi</span> : null}
                    </Link>
                  );
                })}
              </div>
              <div className="space-y-2">
                <p className="flex items-center gap-2 text-xs tracking-[0.14em] text-muted-foreground uppercase">
                  <CircleCheck className="size-3.5" />
                  Completed
                </p>
                {completed.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No activity yet</p>
                ) : completed.map((activity) => (
                  <Link
                    key={activity.garmin_activity_id}
                    href={`/athlete/activities/${activity.garmin_activity_id}`}
                    className="block rounded-lg border border-border bg-background px-2.5 py-2 text-sm hover:bg-muted"
                  >
                    {completedLine(activity)}
                  </Link>
                ))}
              </div>
            </div> : null}
          </div>
        </section>
      ) : null}
      {ready ? (
        <details className="group rounded-xl border border-border bg-card">
          <summary className="flex min-h-14 cursor-pointer list-none items-center justify-between gap-3 px-4 py-4 [&::-webkit-details-marker]:hidden">
            <span className="font-heading text-xl tracking-tight">Recent runs</span>
            <ChevronDown className="size-4 text-muted-foreground transition-transform group-open:rotate-180" />
          </summary>
          <div className="border-t border-border px-4 py-2">
            {recent.length === 0 ? (
              <p className="py-3 text-sm text-muted-foreground">Connect Garmin and sync to pull in your activities.</p>
            ) : (
              <ul className="divide-y divide-border">
                {recent.map((activity) => (
                  <li key={activity.garmin_activity_id}>
                    <Link href={`/athlete/activities/${activity.garmin_activity_id}`} className="flex flex-col gap-1 py-3 hover:bg-muted sm:flex-row sm:items-baseline sm:justify-between">
                      <span className="min-w-0">
                        <span className="font-medium">{activity.name || "Run"}</span>
                        <span className="mt-1 block text-sm text-muted-foreground">{formatWhen(activity.start_time_local, null)}</span>
                      </span>
                      <span className="text-sm text-muted-foreground">
                        {milesLabel(activity.distance_miles)} · {paceLabel(activity.pace_seconds_per_mile)} · {durationLabel(activity.duration_seconds)}
                        {activity.average_heart_rate_bpm == null ? "" : ` · ${Math.round(activity.average_heart_rate_bpm)} bpm`}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </details>
      ) : null}
    </div>
  );
}
