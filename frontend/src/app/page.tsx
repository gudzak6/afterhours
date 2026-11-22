"use client";

import Link from "next/link";
import { Bell, BellOff, ChevronLeft, ChevronRight, Footprints, Info, RefreshCw, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { AthleteName } from "@/components/athlete-name";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { mirrorRosterRuns } from "@/lib/account";
import {
  createBrief,
  createReport,
  errorMessage,
  getDashboard,
  syncRoster,
  updateCoach,
  type CoachDashboard,
} from "@/lib/api";

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

const LATER_BRIEF_SECTIONS = [
  "Priority Athlete Findings",
  "Positive Training Developments",
  "Upcoming Training Considerations",
  "Data Limitations",
];

function athleteClauses(sentence: string, hits: string[]) {
  const placed = hits
    .map((name) => ({ name, index: sentence.toLowerCase().indexOf(name.toLowerCase()) }))
    .filter((item) => item.index >= 0)
    .sort((a, b) => a.index - b.index);
  if (placed.length < 2) return placed.map((item) => ({ name: item.name, text: sentence }));
  return placed.map((item, index) => {
    const end = index + 1 < placed.length ? placed[index + 1].index : sentence.length;
    const text = sentence
      .slice(item.index, end)
      .replace(/\s+and\s*$/i, "")
      .replace(/,\s*$/, "")
      .trim();
    return { name: item.name, text };
  });
}

function executiveAssessment(summary: string, athleteNames: string[]) {
  const marker = "Executive Coaching Assessment";
  const start = summary.indexOf(marker);
  if (start === -1) return null;
  let body = summary.slice(start + marker.length).trim();
  let cut = body.length;
  for (const heading of LATER_BRIEF_SECTIONS) {
    const index = body.indexOf(heading);
    if (index >= 0 && index < cut) cut = index;
  }
  body = body.slice(0, cut).trim();
  const lines = body.split(/\n+/).map((line) => line.trim()).filter(Boolean);
  const explicit = lines.filter((line) => /^[-•*]\s+/.test(line));
  if (explicit.length > 0) {
    return {
      intro: lines.filter((line) => !/^[-•*]\s+/.test(line)).join(" "),
      bullets: explicit.map((line) => line.replace(/^[-•*]\s+/, "")),
    };
  }
  const names = athleteNames.filter((name) => name && name.toLowerCase() !== "athlete").sort((a, b) => b.length - a.length);
  const sentences = body.split(/(?<=[.!?])\s+/).map((sentence) => sentence.trim()).filter(Boolean);
  const intro: string[] = [];
  const closing: string[] = [];
  const own = new Map<string, string[]>();
  let seenAthlete = false;
  for (const sentence of sentences) {
    const hits = names.filter((name) => sentence.toLowerCase().includes(name.toLowerCase()));
    if (hits.length === 0) {
      (seenAthlete ? closing : intro).push(sentence);
      continue;
    }
    seenAthlete = true;
    const pieces = athleteClauses(sentence, hits);
    for (const piece of pieces) {
      const list = own.get(piece.name) ?? [];
      list.push(piece.text);
      own.set(piece.name, list);
    }
  }
  const bullets = names
    .filter((name) => own.has(name))
    .map((name) => {
      const text = [
        ...(own.get(name) ?? []).map((part) => (/[.!?]$/.test(part) ? part : `${part}.`)),
        ...closing,
      ].join(" ");
      return text.toLowerCase().startsWith(name.toLowerCase()) ? text : `${name}: ${text}`;
    });
  if (bullets.length === 0) return { intro: body, bullets: [] as string[] };
  return { intro: intro.join(" "), bullets };
}

function BriefAssessment({ summary, athleteNames }: { summary: string; athleteNames: string[] }) {
  const assessment = executiveAssessment(summary, athleteNames);
  if (!assessment) {
    return <p className="max-w-3xl text-sm leading-6 whitespace-pre-line">{summary}</p>;
  }
  return (
    <div className="max-w-3xl space-y-2 text-sm leading-6">
      <p className="font-medium">Executive Coaching Assessment</p>
      {assessment.intro ? <p>{assessment.intro}</p> : null}
      {assessment.bullets.length > 0 ? (
        <ul className="list-disc space-y-2 pl-5">
          {assessment.bullets.map((bullet) => (
            <li key={bullet}>{bullet}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

type DashboardActivity = CoachDashboard["recent_activities"][number];
type PlannedWorkout = CoachDashboard["planned_workouts"][number];

function rowsForDay(dashboard: CoachDashboard, selectedDay: string) {
  const activities = dashboard.recent_activities.filter((activity) => activity.start_time_local?.startsWith(selectedDay));
  const plans = dashboard.planned_workouts.filter((plan) => plan.scheduled_date === selectedDay);
  const groups = new Map<number, { name: string; planned: PlannedWorkout[]; activities: DashboardActivity[] }>();

  function groupFor(athleteId: number, name: string) {
    const current = groups.get(athleteId);
    if (current) {
      if (current.name === "Athlete" && name) current.name = name;
      return current;
    }
    const created: { name: string; planned: PlannedWorkout[]; activities: DashboardActivity[] } = {
      name: name || "Athlete",
      planned: [],
      activities: [],
    };
    groups.set(athleteId, created);
    return created;
  }

  for (const athlete of dashboard.athletes) {
    groupFor(athlete.id, athlete.display_name);
  }
  for (const plan of plans) {
    groupFor(plan.athlete_id, plan.athlete_name || "Athlete").planned.push(plan);
  }
  for (const activity of activities) {
    groupFor(activity.athlete_id, activity.athlete_name || "Athlete").activities.push(activity);
  }

  const rosterIds = dashboard.athletes.map((athlete) => athlete.id);
  const order = [...rosterIds, ...[...groups.keys()].filter((athleteId) => !rosterIds.includes(athleteId))];
  const rows: Array<{
    key: string;
    athleteId: number;
    athleteName: string;
    planned: PlannedWorkout[];
    activity: DashboardActivity | null;
  }> = [];
  for (const athleteId of order) {
    const group = groups.get(athleteId);
    if (!group) continue;
    if (group.activities.length === 0) {
      rows.push({
        key: `athlete-${athleteId}`,
        athleteId,
        athleteName: group.name,
        planned: group.planned,
        activity: null,
      });
      continue;
    }
    group.activities.forEach((activity, index) => {
      rows.push({
        key: `run-${athleteId}-${activity.garmin_activity_id}-${activity.start_time_local ?? index}`,
        athleteId,
        athleteName: group.name,
        planned: group.planned,
        activity,
      });
    });
  }
  return rows;
}

type DayRow = ReturnType<typeof rowsForDay>[number];

function DayCard({
  row,
  today,
  onAnalyze,
}: {
  row: DayRow;
  today: string;
  onAnalyze: (activity: DashboardActivity) => void;
}) {
  const activity = row.activity;
  if (!activity) {
    return (
      <article className="rounded-xl border border-border bg-card py-4">
        <div className="flex items-start gap-3 px-4">
          <AthleteMark name={row.athleteName} athleteId={row.athleteId} />
          <div className="min-w-0">
            <Link href={`/athletes/${row.athleteId}`} className="font-semibold hover:underline"><AthleteName name={row.athleteName} /></Link>
            <p className="text-sm text-muted-foreground">No run stored.</p>
            <PlannedGhost athleteId={row.athleteId} planned={row.planned} />
          </div>
        </div>
      </article>
    );
  }

  const miles = activity.distance_meters == null ? null : activity.distance_meters / 1609.344;
  const when = activityWhen(activity.start_time_local, today);
  const place = activity.location_name?.trim();
  return (
    <article className="overflow-hidden rounded-xl border border-border bg-card">
      <div className="flex items-start gap-3 px-4 pt-4">
        <AthleteMark name={row.athleteName} athleteId={row.athleteId} />
        <div className="min-w-0">
          <Link href={`/athletes/${row.athleteId}`} className="font-semibold hover:underline"><AthleteName name={row.athleteName} /></Link>
          <p className="text-sm text-muted-foreground">
            {when}
            {place ? ` · ${place}` : ""}
          </p>
        </div>
      </div>
      <div className="px-4 pt-4">
        <Link href={`/activities/${activity.garmin_activity_id}`} className="inline-flex items-center gap-2 hover:underline">
          <Footprints className="size-5 shrink-0" />
          <span className="text-lg font-semibold tracking-tight sm:text-xl">{activity.name || "Run"}</span>
        </Link>
        <PlannedGhost athleteId={row.athleteId} planned={row.planned} />
      </div>
      <dl className="grid grid-cols-3 gap-3 px-4 py-4">
        <Stat label="Distance" value={miles == null ? "—" : `${miles.toFixed(2)} mi`} />
        <Stat label="Pace" value={paceLabel(activity.average_pace_seconds_per_mile)} />
        <Stat label="Time" value={durationLabel(activity.duration_seconds)} />
      </dl>
      <div className="border-t border-border px-4 py-3">
        <Button type="button" size="sm" variant="outline" onClick={() => onAnalyze(activity)}>
          AI analysis
        </Button>
      </div>
    </article>
  );
}

function AthleteMark({ name, athleteId }: { name: string; athleteId: number }) {
  return (
    <Link
      href={`/athletes/${athleteId}`}
      aria-label={name}
      className="flex size-10 shrink-0 items-center justify-center rounded-md bg-primary text-sm font-semibold text-primary-foreground"
    >
      {initials(name)}
    </Link>
  );
}

function plannedLabel(plan: PlannedWorkout) {
  const extras = (plan.detail ?? "").split(" · ").filter((part) => /\d/.test(part));
  return [plan.title, ...extras].filter(Boolean).join(", ");
}

function PlannedGhost({ athleteId, planned }: { athleteId: number; planned: PlannedWorkout[] }) {
  const className = "mt-1 text-xs text-muted-foreground/60";
  if (planned.length === 0) return <p className={className}>No workout planned</p>;
  return (
    <p className={className}>
      Planned
      {" · "}
      <Link href={`/athletes/${athleteId}?section=plan`} className="hover:underline">
        {planned.map(plannedLabel).join(" · ")}
      </Link>
    </p>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="mt-1 text-base font-semibold tracking-tight sm:text-lg">{value}</dd>
    </div>
  );
}

function AnalysisModal({
  activity,
  athleteName,
  busy,
  error,
  onClose,
  onRun,
}: {
  activity: DashboardActivity | null;
  athleteName: string | null;
  busy: boolean;
  error: string | null;
  onClose: () => void;
  onRun: (garminActivityId: number) => void;
}) {
  useEffect(() => {
    if (!activity) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [activity, onClose]);

  if (!activity) return null;
  const kind = activity.analysis_kind === "easy" ? "Easy run" : activity.analysis_kind === "workout" ? "Workout analysis" : "AI analysis";
  return (
    <div
      className="fixed inset-x-0 top-0 z-[80] flex h-dvh items-end justify-center bg-black/45 px-4 pt-[max(1rem,env(safe-area-inset-top))] pb-[max(6.5rem,env(safe-area-inset-bottom))] sm:items-center sm:p-6"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="analysis-title"
        className="flex max-h-full w-full max-w-lg flex-col overflow-hidden rounded-xl border border-border bg-card shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 px-5 pt-5">
          <div className="min-w-0">
            <p className="text-xs tracking-wide text-muted-foreground uppercase">{kind}</p>
            <h2 id="analysis-title" className="mt-1 text-xl font-semibold">{activity.name || "Run"}</h2>
            {athleteName ? <p className="text-sm text-muted-foreground"><AthleteName name={athleteName} /></p> : null}
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className="inline-flex size-11 shrink-0 items-center justify-center rounded-full text-muted-foreground hover:bg-muted">
            <X className="size-4" />
          </button>
        </div>
        <div className="overflow-y-auto px-5 py-4">
          <p className="text-sm leading-6 whitespace-pre-wrap">
            {busy && !activity.analysis_summary
              ? "Writing the analysis…"
              : activity.analysis_summary || "No analysis saved for this activity."}
          </p>
          {error ? <p className="mt-3 text-sm text-destructive">{error}</p> : null}
        </div>
        <div className="flex flex-col gap-2 border-t border-border px-5 py-4 sm:flex-row sm:justify-end">
          <Button type="button" variant="outline" className="h-11 w-full sm:h-8 sm:w-auto" onClick={onClose}>Close</Button>
          <Button type="button" className="h-11 w-full sm:h-8 sm:w-auto" disabled={busy} onClick={() => onRun(activity.garmin_activity_id)}>
            {busy ? "Writing…" : activity.analysis_summary ? "Write again" : "Run analysis"}
          </Button>
        </div>
      </div>
    </div>
  );
}

function initials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return parts.slice(0, 2).map((part) => part[0]?.toUpperCase() ?? "").join("") || "A";
}

function activityWhen(local: string | null, today: string) {
  if (!local) return "Run";
  const [date, time] = local.split(" ");
  if (!date || !time) return local;
  const [hourText, minute] = time.split(":");
  const hour = Number(hourText);
  if (!Number.isFinite(hour) || minute == null) return local;
  const suffix = hour >= 12 ? "PM" : "AM";
  const clock = `${hour % 12 || 12}:${minute} ${suffix}`;
  if (date === today) return `Today at ${clock}`;
  const parsed = parseDay(date);
  return `${MONTHS[parsed.getMonth()].slice(0, 3)} ${parsed.getDate()} at ${clock}`;
}

function paceLabel(seconds: number | null | undefined) {
  if (seconds == null || !Number.isFinite(seconds)) return "—";
  const rounded = Math.round(seconds);
  const minutes = Math.floor(rounded / 60);
  return `${minutes}:${String(rounded % 60).padStart(2, "0")} /mi`;
}

function durationLabel(seconds: number | null | undefined) {
  if (seconds == null || !Number.isFinite(seconds)) return "—";
  const total = Math.round(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  if (hours > 0) return `${hours}h ${minutes}m`;
  const remainder = total % 60;
  return remainder > 0 ? `${minutes}m ${remainder}s` : `${minutes}m`;
}

function WeekStrip({
  weekStart,
  selectedDay,
  reloading,
  syncing,
  onSelect,
  onShiftWeek,
  onReload,
}: {
  weekStart: string;
  selectedDay: string;
  reloading: boolean;
  syncing: boolean;
  onSelect: (day: string) => void;
  onShiftWeek: (weeks: number) => void;
  onReload: () => void;
}) {
  const days = WEEKDAYS.map((_, index) => shiftDay(weekStart, index));
  return (
    <div className="max-w-xl space-y-3">
      <div className="flex items-center justify-between gap-2">
        <button
          type="button"
          onClick={() => onShiftWeek(-1)}
          className="inline-flex size-11 shrink-0 items-center justify-center rounded-full border border-border text-muted-foreground hover:bg-muted"
          aria-label="Previous week"
        >
          <ChevronLeft className="size-4" />
        </button>
        <p className="min-w-0 text-center text-xs tracking-[0.08em] text-muted-foreground uppercase sm:tracking-[0.16em]">{dayLabel(selectedDay)}</p>
        <button
          type="button"
          onClick={() => onShiftWeek(1)}
          className="inline-flex size-11 shrink-0 items-center justify-center rounded-full border border-border text-muted-foreground hover:bg-muted"
          aria-label="Next week"
        >
          <ChevronRight className="size-4" />
        </button>
      </div>
      <div className="grid grid-cols-7 gap-1 sm:gap-2">
          {days.map((day) => {
            const date = parseDay(day);
            const selected = day === selectedDay;
            return (
              <button
                key={day}
                type="button"
                onClick={() => onSelect(day)}
                aria-pressed={selected}
                className={`mx-auto flex aspect-square w-full max-w-12 flex-col items-center justify-center rounded-full border text-center ${
                  selected
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-border bg-card text-foreground hover:bg-muted"
                }`}
              >
                <span className="text-[9px] leading-none tracking-wide uppercase max-[380px]:hidden sm:text-[10px]">{WEEKDAYS[date.getDay()]}</span>
                <span className="text-[10px] leading-none uppercase min-[381px]:hidden">{WEEKDAYS[date.getDay()].slice(0, 1)}</span>
                <span className="text-xs font-medium leading-none sm:text-sm">{date.getDate()}</span>
              </button>
            );
          })}
      </div>
      <div>
        <button
          type="button"
          onClick={onReload}
          disabled={reloading || syncing}
          className="inline-flex min-h-11 items-center gap-1.5 rounded-full border border-border px-4 text-xs text-muted-foreground hover:bg-muted disabled:opacity-60"
        >
          <RefreshCw className={`size-3.5 ${reloading || syncing ? "animate-spin" : ""}`} />
          {syncing ? "Syncing" : "Sync Garmin"}
        </button>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const [dashboard, setDashboard] = useState<CoachDashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [selectedDay, setSelectedDay] = useState<string | null>(null);
  const [analyzingId, setAnalyzingId] = useState<number | null>(null);
  const [analysisId, setAnalysisId] = useState<number | null>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [reloading, setReloading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [writingBrief, setWritingBrief] = useState(false);
  const requestId = useRef(0);
  const viewedDay = useRef<string | null>(null);
  viewedDay.current = selectedDay;

  const load = useCallback(async (day?: string) => {
    const id = requestId.current + 1;
    requestId.current = id;
    setReloading(true);
    try {
      const next = await getDashboard(day);
      if (requestId.current !== id) return;
      setDashboard(next);
      setSelectedDay((current) => day ?? current ?? next.today);
      setError(null);
      void mirrorRosterRuns(next.recent_activities).catch(() => undefined);
    } catch (loadError) {
      if (requestId.current !== id) return;
      setError(errorMessage(loadError));
    } finally {
      if (requestId.current === id) setReloading(false);
    }
  }, []);

  async function reloadFromGarmin(day: string) {
    setSyncing(true);
    setError(null);
    try {
      const result = await syncRoster();
      if (result.errors.length > 0) setNotice(result.errors[0]);
    } catch (syncError) {
      setError(errorMessage(syncError));
    } finally {
      setSyncing(false);
    }
    await load(day);
  }

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  const writeBrief = useCallback(async (day: string) => {
    setWritingBrief(true);
    setNotice(null);
    try {
      const result = await createBrief(day);
      if (viewedDay.current !== day) return;
      if (!result.report) {
        setNotice("A brief is written from the coaching server. This page keeps the roster and the runs already saved.");
        return;
      }
      setDashboard((current) =>
        current ? { ...current, brief: result.report, brief_created_at: result.created_at } : current,
      );
    } catch (briefError) {
      if (viewedDay.current !== day) return;
      const message = errorMessage(briefError);
      setNotice(
        /not connected|did not return|not found/i.test(message)
          ? "A brief is written from the coaching server. This page keeps the roster and the runs already saved."
          : message,
      );
    } finally {
      setWritingBrief(false);
    }
  }, []);

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
      const kind = result.report.analysis_kind === "easy" ? "easy" : "workout";
      setDashboard((current) =>
        current
          ? {
              ...current,
              recent_activities: current.recent_activities.map((activity) =>
                activity.garmin_activity_id === garminActivityId
                  ? { ...activity, analysis_summary: summary, analysis_kind: kind }
                  : activity,
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

  return (
    <div className="space-y-4">
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      {!dashboard && !error ? <p className="text-sm text-muted-foreground">Loading the roster…</p> : null}

      {dashboard && selectedDay ? (
        <>
          <WeekStrip
            weekStart={shiftDay(selectedDay, -parseDay(selectedDay).getDay())}
            selectedDay={selectedDay}
            reloading={reloading}
            syncing={syncing}
            onSelect={(day) => {
              setSelectedDay(day);
              void load(day);
            }}
            onShiftWeek={(weeks) => {
              const day = shiftDay(selectedDay, weeks * 7);
              setSelectedDay(day);
              void load(day);
            }}
            onReload={() => void reloadFromGarmin(selectedDay)}
          />
          <h2 className="font-heading text-xl tracking-tight">Athletes runs today</h2>
          {shiftDay(selectedDay, -parseDay(selectedDay).getDay()) !== dashboard.week_start ? (
            <p className="text-sm text-muted-foreground">Loading {dayLabel(selectedDay)}…</p>
          ) : rowsForDay(dashboard, selectedDay).length === 0 ? (
            <p className="text-sm text-muted-foreground">No runs stored for {dayLabel(selectedDay)}.</p>
          ) : (
            <>
            <div className="space-y-3">
            {rowsForDay(dashboard, selectedDay).map((row) => (
              <DayCard
                key={row.key}
                row={row}
                today={dashboard.today}
                onAnalyze={(activity) => {
                  setAnalysisId(activity.garmin_activity_id);
                  setAnalysisError(null);
                  if (!activity.analysis_summary) void runAnalysis(activity.garmin_activity_id);
                }}
              />
            ))}
            </div>
            <AnalysisModal
              activity={dashboard.recent_activities.find((item) => item.garmin_activity_id === analysisId) ?? null}
              athleteName={rowsForDay(dashboard, selectedDay).find((row) => row.activity?.garmin_activity_id === analysisId)?.athleteName ?? null}
              busy={analyzingId !== null && analyzingId === analysisId}
              error={analysisError}
              onClose={() => setAnalysisId(null)}
              onRun={(garminActivityId) => void runAnalysis(garminActivityId)}
            />
            </>
          )}
          <Card>
            <CardHeader className="flex flex-row items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <CardTitle>AI coaching brief</CardTitle>
                <div className="group relative">
                  <button
                    type="button"
                    className="rounded-full p-1 text-muted-foreground"
                    aria-label={selectedDay > dashboard.today ? "preview of the planned workouts for this day" : "summary of athletes workouts for today"}
                  >
                    <Info className="size-4" />
                  </button>
                  <p className="pointer-events-none absolute top-full left-0 z-10 mt-2 hidden w-52 border border-foreground/20 bg-background px-3 py-2 text-[11px] leading-snug text-foreground group-hover:block group-focus-within:block">
                    {selectedDay > dashboard.today ? "preview of the planned workouts for this day" : "summary of athletes workouts for today"}
                  </p>
                </div>
              </div>
              <div className="group relative">
                <button
                  type="button"
                  onClick={() => void toggleEmail()}
                  className={`rounded-full border p-2 ${
                    dashboard.coach.email_notifications_enabled
                      ? "border-emerald-300 bg-emerald-50 text-emerald-900"
                      : "border-border text-muted-foreground"
                  }`}
                  aria-label="Add email and text notifications coming soon"
                >
                  {dashboard.coach.email_notifications_enabled ? <Bell className="size-4" /> : <BellOff className="size-4" />}
                </button>
                <p className="pointer-events-none absolute top-full right-0 z-10 mt-2 hidden w-44 border border-foreground/20 bg-background px-3 py-2 text-right text-[11px] leading-snug tracking-[0.08em] text-foreground uppercase group-hover:block group-focus-within:block">
                  Add email and text notifications coming soon
                </p>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              {notice ? <p className="text-sm text-muted-foreground">{notice}</p> : null}
              {writingBrief && !dashboard.brief ? (
                <p className="text-sm text-muted-foreground">Writing the coaching brief for {dayLabel(selectedDay)}…</p>
              ) : dashboard.brief ? (
                <div className="space-y-3">
                  {selectedDay > dashboard.today ? (
                    <p className="text-xs tracking-[0.14em] text-muted-foreground uppercase">Preview · this day has not been run</p>
                  ) : null}
                  <BriefAssessment
                    summary={dashboard.brief.daily_summary}
                    athleteNames={dashboard.athletes.map((athlete) => athlete.display_name)}
                  />
                  {writingBrief ? (
                    <p className="text-sm text-muted-foreground">Writing a new coaching brief for {dayLabel(selectedDay)}…</p>
                  ) : null}
                  <Button type="button" variant="outline" className="min-h-11" disabled={writingBrief} onClick={() => void writeBrief(selectedDay)}>
                    {writingBrief ? "Regenerating…" : "Regenerate"}
                  </Button>
                </div>
              ) : (
                <div className="space-y-3">
                  <p className="text-sm text-muted-foreground">
                    No coaching brief has been written for {dayLabel(selectedDay)}.
                  </p>
                  <Button type="button" variant="outline" disabled={writingBrief} onClick={() => void writeBrief(selectedDay)}>
                    {writingBrief ? "Generating…" : "Generate coaching brief"}
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
        </>
      ) : null}
    </div>
  );
}
