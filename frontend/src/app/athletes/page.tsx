"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Check, ChevronRight, X } from "lucide-react";
import { AthleteName } from "@/components/athlete-name";
import { errorMessage, getActivities, getDashboard, type Activity, type CoachDashboard, type RosterAthlete } from "@/lib/api";

const METERS_PER_MILE = 1609.344;

function addDays(iso: string, days: number) {
  const [year, month, day] = iso.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function mondayOf(iso: string) {
  const [year, month, day] = iso.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  const sinceMonday = date.getUTCDay() === 0 ? 6 : date.getUTCDay() - 1;
  date.setUTCDate(date.getUTCDate() - sinceMonday);
  return date.toISOString().slice(0, 10);
}

function weekMileage(today: string, athlete: RosterAthlete, activities: Activity[], dashboard: CoachDashboard) {
  const start = mondayOf(today);
  const days = Array.from({ length: 7 }, (_, index) => addDays(start, index));
  const miles = days.map(() => 0);
  const source = activities.length > 0 ? activities : dashboard.recent_activities;
  for (const activity of source) {
    if (activity.athlete_id !== athlete.id || !activity.start_time_local) continue;
    const index = days.indexOf(activity.start_time_local.slice(0, 10));
    if (index < 0) continue;
    const recorded = "distance_miles" in activity ? activity.distance_miles : null;
    const distance = typeof recorded === "number" ? recorded : activity.distance_meters == null ? null : activity.distance_meters / METERS_PER_MILE;
    if (distance != null) miles[index] += distance;
  }
  const total = miles.reduce((sum, value) => sum + value, 0);
  return { days, miles, total: total > 0 ? total : athlete.weekly_miles };
}

function WeekBars({ miles, today, days }: { miles: number[]; today: string; days: string[] }) {
  const peak = Math.max(...miles, 0);
  return (
    <div className="flex h-10 items-end gap-1" aria-hidden>
      {miles.map((value, index) => {
        const current = days[index] === today;
        const empty = value <= 0;
        const height = empty ? 28 : Math.max(42, (value / peak) * 100);
        const color = empty ? "bg-[#d5d5d5]" : current ? "bg-primary" : "bg-[#6ec4de]";
        return <span key={days[index]} className={`w-2 rounded-[2px] ${color}`} style={{ height: `${height}%` }} />;
      })}
    </div>
  );
}

function GarminStatus({ status }: { status: string }) {
  const connected = status === "connected";
  const pending = status === "pending";
  const label = connected ? "Garmin connected" : pending ? "Garmin signing in" : "Garmin not connected";
  return (
    <p className="mt-1 flex items-center gap-1.5 text-sm text-muted-foreground">
      <span
        className={`inline-flex size-4 shrink-0 items-center justify-center rounded-full ${connected ? "bg-emerald-500 text-white" : pending ? "bg-amber-400" : "bg-foreground/20"}`}
        aria-hidden
      >
        {connected ? <Check className="size-2.5" strokeWidth={3} /> : null}
      </span>
      {label}
    </p>
  );
}

export default function AthletesPage() {
  const [dashboard, setDashboard] = useState<CoachDashboard | null>(null);
  const [activities, setActivities] = useState<Activity[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

  const load = useCallback(async () => {
    try {
      const [roster, runs] = await Promise.all([getDashboard(), getActivities(200).catch(() => null)]);
      setDashboard(roster);
      setActivities(runs?.activities ?? []);
      setError(null);
    } catch (loadError) {
      setError(errorMessage(loadError));
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void load();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  useEffect(() => {
    if (!adding) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setAdding(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [adding]);

  const athletes = dashboard?.athletes ?? [];
  const countLabel = `${athletes.length} athlete${athletes.length === 1 ? "" : "s"}`;

  return (
    <div className="space-y-4">
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      {!dashboard && !error ? <p className="text-sm text-muted-foreground">Loading the roster…</p> : null}
      {dashboard ? (
        <section className="overflow-hidden rounded-xl border border-border bg-card">
          <header className="flex items-center justify-between gap-4 border-b border-border px-5 py-4">
            <h1 className="text-lg font-semibold tracking-tight">Athletes</h1>
            <div className="flex items-center gap-3">
              <p className="text-sm text-muted-foreground">{countLabel}</p>
              <button
                type="button"
                onClick={() => setAdding(true)}
                className="inline-flex h-8 items-center rounded-lg bg-primary px-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/80"
              >
                Add athlete
              </button>
            </div>
          </header>
          {athletes.length === 0 ? (
            <p className="px-5 py-6 text-sm text-muted-foreground">No athletes on the roster.</p>
          ) : (
            <ul>
              {athletes.map((athlete) => {
                const week = weekMileage(dashboard.today, athlete, activities, dashboard);
                const shown = week.total == null ? "0.0 mi" : `${week.total.toFixed(1)} mi`;
                return (
                  <li key={athlete.id} className="border-b border-border last:border-0">
                    <Link
                      href={`/athletes/${athlete.id}`}
                      className="flex flex-col gap-4 px-5 py-4 transition-colors hover:bg-foreground/[0.03] sm:flex-row sm:items-center sm:justify-between"
                    >
                      <span>
                        <span className="block text-base font-semibold tracking-tight">
                          <AthleteName name={athlete.display_name} />
                        </span>
                        <GarminStatus status={athlete.garmin_status} />
                        <span className="mt-1 flex items-center gap-1 text-sm text-muted-foreground">
                          Click to see activities and other data
                          <ChevronRight className="size-3.5" aria-hidden />
                        </span>
                      </span>
                      <span className="flex items-center gap-4 sm:shrink-0">
                        <span className="min-w-16 text-center">
                          <span className="block text-xl font-semibold tracking-tight">{shown}</span>
                          <span className="block text-xs text-muted-foreground">This week</span>
                        </span>
                        <WeekBars miles={week.miles} today={dashboard.today} days={week.days} />
                      </span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      ) : null}
      {adding ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/40 p-4" onClick={() => setAdding(false)}>
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="add-athlete-title"
            className="w-full max-w-md rounded-xl border border-border bg-card p-5 shadow-sm"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-3">
              <h2 id="add-athlete-title" className="text-lg font-semibold tracking-tight">Add athlete</h2>
              <button type="button" onClick={() => setAdding(false)} className="rounded-md p-1 text-muted-foreground hover:text-foreground" aria-label="Close">
                <X className="size-4" />
              </button>
            </div>
            <p className="mt-3 text-sm leading-6 text-muted-foreground">
              To add an athlete, they need to sign up and connect their device for tracking. Athlete can sign up{" "}
              <Link href="/login?signup=1" className="text-foreground underline">here</Link>.
            </p>
          </div>
        </div>
      ) : null}
    </div>
  );
}
