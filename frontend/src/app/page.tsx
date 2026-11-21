"use client";

import Link from "next/link";
import { Bell, BellOff, ChevronLeft, ChevronRight } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  createBrief,
  createReport,
  errorMessage,
  getDashboard,
  updateCoach,
  type BriefItem,
  type CoachDashboard,
} from "@/lib/api";
import { formatMiles, formatWhen } from "@/lib/format";

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
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

function dayLabel(iso: string): string {
  const date = parseDay(iso);
  return `${WEEKDAYS[date.getDay()]}, ${MONTHS[date.getMonth()]} ${date.getDate()}`;
}

type DashboardActivity = CoachDashboard["recent_activities"][number];
type PlannedWorkout = CoachDashboard["planned_workouts"][number];

function rowsForDay(dashboard: CoachDashboard, selectedDay: string) {
  const activities = dashboard.recent_activities.filter((activity) => activity.start_time_local?.startsWith(selectedDay));
  const plans = dashboard.planned_workouts.filter((plan) => plan.scheduled_date === selectedDay);
  const ran = new Set(activities.map((activity) => activity.athlete_id));
  const rows: Array<{
    key: string;
    athleteId: number;
    athleteName: string;
    planned: PlannedWorkout[];
    activity: DashboardActivity | null;
  }> = activities.map((activity) => ({
    key: `run-${activity.garmin_activity_id}`,
    athleteId: activity.athlete_id,
    athleteName: activity.athlete_name || "Athlete",
    planned: plans.filter((plan) => plan.athlete_id === activity.athlete_id),
    activity,
  }));
  const planOnly = new Map<number, PlannedWorkout[]>();
  for (const plan of plans) {
    if (ran.has(plan.athlete_id)) continue;
    const current = planOnly.get(plan.athlete_id) ?? [];
    current.push(plan);
    planOnly.set(plan.athlete_id, current);
  }
  for (const [athleteId, athletePlans] of planOnly) {
    rows.push({
      key: `plan-${athleteId}`,
      athleteId,
      athleteName: athletePlans[0]?.athlete_name || "Athlete",
      planned: athletePlans,
      activity: null,
    });
  }
  return rows;
}

function WeekStrip({
  weekStart,
  selectedDay,
  onSelect,
  onShiftWeek,
}: {
  weekStart: string;
  selectedDay: string;
  onSelect: (day: string) => void;
  onShiftWeek: (weeks: number) => void;
}) {
  const days = WEEKDAYS.map((_, index) => shiftDay(weekStart, index));
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => onShiftWeek(-1)}
          className="rounded-full border border-border p-2 text-muted-foreground hover:bg-muted"
          aria-label="Previous week"
        >
          <ChevronLeft className="size-4" />
        </button>
        <div className="grid flex-1 grid-cols-7 gap-2">
          {days.map((day) => {
            const date = parseDay(day);
            const selected = day === selectedDay;
            return (
              <button
                key={day}
                type="button"
                onClick={() => onSelect(day)}
                aria-pressed={selected}
                className={`mx-auto flex size-14 flex-col items-center justify-center rounded-full border text-center sm:size-16 ${
                  selected
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-border bg-card text-foreground hover:bg-muted"
                }`}
              >
                <span className="text-[10px] tracking-wide uppercase sm:text-[11px]">{WEEKDAYS[date.getDay()]}</span>
                <span className="text-sm font-medium sm:text-base">{date.getDate()}</span>
              </button>
            );
          })}
        </div>
        <button
          type="button"
          onClick={() => onShiftWeek(1)}
          className="rounded-full border border-border p-2 text-muted-foreground hover:bg-muted"
          aria-label="Next week"
        >
          <ChevronRight className="size-4" />
        </button>
      </div>
      <p className="text-xs tracking-[0.16em] text-muted-foreground uppercase">{dayLabel(selectedDay)}</p>
    </div>
  );
}

function BriefList({
  title,
  items,
  field,
}: {
  title: string;
  items: BriefItem[];
  field: "reason" | "note" | "action";
}) {
  return (
    <div>
      <h3 className="text-sm font-medium">{title}</h3>
      {items.length === 0 ? (
        <p className="mt-1 text-sm text-muted-foreground">None from the stored activities.</p>
      ) : (
        <ul className="mt-2 space-y-2 text-sm">
          {items.map((item) => (
            <li key={`${field}-${item.athlete_id}-${item.garmin_activity_id ?? "none"}`}>
              <Link href={`/athletes/${item.athlete_id}`} className="font-medium hover:underline">
                {item.athlete_name}
              </Link>
              {item.garmin_activity_id ? (
                <>
                  {" · "}
                  <Link href={`/activities/${item.garmin_activity_id}`} className="hover:underline">
                    activity
                  </Link>
                </>
              ) : null}
              <p className="text-muted-foreground">{item[field]}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function DashboardPage() {
  const [dashboard, setDashboard] = useState<CoachDashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [selectedDay, setSelectedDay] = useState<string | null>(null);
  const [analyzingId, setAnalyzingId] = useState<number | null>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);

  const load = useCallback(async (day?: string) => {
    try {
      const next = await getDashboard(day);
      setDashboard(next);
      setSelectedDay((current) => current ?? next.today);
      setError(null);
    } catch (loadError) {
      setError(errorMessage(loadError));
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  async function toggleEmail() {
    if (!dashboard) return;
    const enabled = !dashboard.coach.email_notifications_enabled;
    setNotice(null);
    try {
      const coach = await updateCoach({ email_notifications_enabled: enabled });
      setDashboard({ ...dashboard, coach });
      setNotice(enabled ? "Daily email is on. One brief is sent at 7:00 in your timezone." : "Daily email is off. The brief stays on this page.");
    } catch (toggleError) {
      setNotice(errorMessage(toggleError));
    }
  }

  async function runAnalysis(garminActivityId: number) {
    setAnalyzingId(garminActivityId);
    setAnalysisError(null);
    try {
      const result = await createReport(garminActivityId);
      const summary = typeof result.report.summary === "string" ? result.report.summary : null;
      setDashboard((current) =>
        current
          ? {
              ...current,
              recent_activities: current.recent_activities.map((activity) =>
                activity.garmin_activity_id === garminActivityId ? { ...activity, analysis_summary: summary } : activity,
              ),
            }
          : current,
      );
    } catch (reportError) {
      setAnalysisError(errorMessage(reportError));
    } finally {
      setAnalyzingId(null);
    }
  }

  async function writeBrief() {
    setBusy(true);
    setNotice(null);
    try {
      const created = await createBrief();
      setDashboard((current) =>
        current ? { ...current, brief: created.report, brief_created_at: created.created_at } : current,
      );
    } catch (briefError) {
      setNotice(errorMessage(briefError));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-heading text-4xl tracking-tight">Dashboard</h1>
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
          Pick a day to see the planned workout, what each athlete ran, and the saved analysis.
        </p>
      </div>
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      {!dashboard && !error ? <p className="text-sm text-muted-foreground">Loading the roster…</p> : null}

      {dashboard && selectedDay ? (
        <>
          <WeekStrip
            weekStart={shiftDay(selectedDay, -parseDay(selectedDay).getDay())}
            selectedDay={selectedDay}
            onSelect={setSelectedDay}
            onShiftWeek={(weeks) => {
              const day = shiftDay(selectedDay, weeks * 7);
              setSelectedDay(day);
              void load(day);
            }}
          />
          {shiftDay(selectedDay, -parseDay(selectedDay).getDay()) !== dashboard.week_start ? (
            <p className="text-sm text-muted-foreground">Loading {dayLabel(selectedDay)}…</p>
          ) : rowsForDay(dashboard, selectedDay).length === 0 ? (
            <p className="text-sm text-muted-foreground">No runs stored for {dayLabel(selectedDay)}.</p>
          ) : (
            <div className="space-y-2">
            {analysisError ? <p className="text-sm text-destructive">{analysisError}</p> : null}
            <div className="overflow-x-auto rounded-xl border border-border">
              <table className="w-full min-w-[64rem] text-left text-sm">
                <thead className="text-xs tracking-wide text-muted-foreground uppercase">
                  <tr className="border-b border-border">
                    <th className="px-4 py-3 font-medium">Athlete</th>
                    <th className="px-4 py-3 font-medium">Planned</th>
                    <th className="px-4 py-3 font-medium">What they ran</th>
                    <th className="px-4 py-3 font-medium">AI analysis</th>
                  </tr>
                </thead>
                <tbody>
                  {rowsForDay(dashboard, selectedDay).map((row) => {
                    const activity = row.activity;
                    const miles = activity?.distance_meters == null ? null : activity.distance_meters / 1609.344;
                    return (
                      <tr key={row.key} className="border-b border-border/70 align-top last:border-0">
                        <td className="px-4 py-3 whitespace-nowrap">
                          <Link href={`/athletes/${row.athleteId}`} className="font-medium hover:underline">
                            {row.athleteName}
                          </Link>
                        </td>
                        <td className="px-4 py-3">
                          {row.planned.length === 0 ? (
                            <span className="text-muted-foreground">No planned workout.</span>
                          ) : (
                            <div className="space-y-2">
                              {row.planned.map((plan) => (
                                <div key={plan.id}>
                                  <Link href={`/athletes/${row.athleteId}?section=plan`} className="font-medium hover:underline">
                                    {plan.title}
                                  </Link>
                                  {plan.detail ? <p className="mt-1 text-muted-foreground">{plan.detail}</p> : null}
                                </div>
                              ))}
                            </div>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          {activity ? (
                            <Link href={`/activities/${activity.garmin_activity_id}`} className="block rounded-md hover:bg-muted">
                              <span className="font-medium">{activity.name || "Activity"}</span>
                              <p className="mt-1 text-muted-foreground">
                                {formatWhen(activity.start_time_local, null)}
                                {" · "}
                                {formatMiles(miles, activity.distance_meters != null)}
                              </p>
                            </Link>
                          ) : (
                            <span className="text-muted-foreground">No run stored.</span>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          {activity ? (
                            <div className="space-y-2">
                              <Button
                                type="button"
                                size="sm"
                                variant="outline"
                                disabled={analyzingId !== null}
                                onClick={() => void runAnalysis(activity.garmin_activity_id)}
                              >
                                {analyzingId === activity.garmin_activity_id ? "Writing…" : "Run analysis"}
                              </Button>
                              <p className="text-muted-foreground">
                                {activity.analysis_summary || "No analysis saved for this activity."}
                              </p>
                            </div>
                          ) : (
                            <span className="text-muted-foreground">No run to analyze.</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            </div>
          )}

          <Card>
            <CardHeader className="flex flex-row items-start justify-between gap-3">
              <div>
                <CardTitle>AI coaching brief</CardTitle>
                <CardDescription>
                  {dashboard.brief_created_at
                    ? `Saved ${new Date(dashboard.brief_created_at).toLocaleString()}`
                    : "No brief has been written yet."}
                </CardDescription>
              </div>
              <button
                type="button"
                onClick={() => void toggleEmail()}
                className={`rounded-full border p-2 ${
                  dashboard.coach.email_notifications_enabled
                    ? "border-emerald-300 bg-emerald-50 text-emerald-900"
                    : "border-border text-muted-foreground"
                }`}
                aria-label={dashboard.coach.email_notifications_enabled ? "Disable daily email" : "Enable daily email"}
              >
                {dashboard.coach.email_notifications_enabled ? <Bell className="size-4" /> : <BellOff className="size-4" />}
              </button>
            </CardHeader>
            <CardContent className="space-y-4">
              {notice ? <p className="text-sm">{notice}</p> : null}
              {dashboard.brief ? (
                <>
                  <p className="text-sm">{dashboard.brief.daily_summary}</p>
                  <BriefList title="Requires attention" items={dashboard.brief.requires_attention} field="reason" />
                  <BriefList title="Positive developments" items={dashboard.brief.positive_developments} field="note" />
                  <BriefList title="Suggested coach actions" items={dashboard.brief.suggested_actions} field="action" />
                </>
              ) : (
                <p className="text-sm text-muted-foreground">
                  The brief is written from the roster and existing workout analyses. It is not generated on every page load.
                </p>
              )}
              <Button type="button" onClick={() => void writeBrief()} disabled={busy}>
                {busy ? "Writing…" : "Write coaching brief"}
              </Button>
            </CardContent>
          </Card>
        </>
      ) : null}
    </div>
  );
}
