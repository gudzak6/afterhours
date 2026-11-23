"use client";

import Link from "next/link";
import { Bell, BellOff, Calendar, ChevronDown, ChevronLeft, ChevronRight, ChevronUp, CircleCheck, Info, RefreshCw, Sparkles } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { AthleteName } from "@/components/athlete-name";
import { Button } from "@/components/ui/button";
import { mirrorRosterRuns } from "@/lib/account";
import {
  createBrief,
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

const FULL_WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

function fullDayLabel(iso: string): string {
  const date = parseDay(iso);
  return `${FULL_WEEKDAYS[date.getDay()]}, ${MONTHS[date.getMonth()]} ${date.getDate()}`;
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

const PREVIEW_HEADINGS = [
  "Workout Purpose",
  "Athlete-Specific Rationale",
  "Execution Guidance",
  "Success Criteria",
  "Coach Watchpoints",
  "Training Context",
];

function firstSentence(text: string) {
  const match = text.match(/^.*?[.!?](?:\s|$)/);
  return (match ? match[0] : text).trim();
}

function shortenPreview(summary: string) {
  if (!summary.includes("Workout Purpose:")) return null;
  const notes: Array<{ name: string; purpose: string; watch: string }> = [];
  let current: { name: string; purpose: string; watch: string } | null = null;
  for (const chunk of summary.split(/\n\s*\n/).map((part) => part.trim()).filter(Boolean)) {
    const heading = PREVIEW_HEADINGS.find((label) => chunk.startsWith(`${label}:`));
    if (!heading) {
      if (!chunk.includes(":")) {
        current = { name: chunk, purpose: "", watch: "" };
        notes.push(current);
      }
      continue;
    }
    if (!current) continue;
    const body = chunk.slice(heading.length + 1).trim();
    if (heading === "Workout Purpose") current.purpose = firstSentence(body);
    if (heading === "Coach Watchpoints") current.watch = firstSentence(body);
  }
  return notes.some((note) => note.purpose || note.watch) ? notes : null;
}

function BriefAssessment({ summary, athleteNames }: { summary: string; athleteNames: string[] }) {
  const preview = shortenPreview(summary);
  if (preview) {
    return (
      <ul className="max-w-3xl space-y-3 text-sm leading-6">
        {preview.map((note) => (
          <li key={note.name}>
            <p className="font-medium">{note.name}</p>
            {note.purpose ? <p>{note.purpose}</p> : null}
            {note.watch ? <p className="text-muted-foreground">{note.watch}</p> : null}
          </li>
        ))}
      </ul>
    );
  }
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

type AthleteDay = {
  athleteId: number;
  athleteName: string;
  planned: PlannedWorkout[];
  activities: DashboardActivity[];
};

function athletesForDay(dashboard: CoachDashboard, selectedDay: string): AthleteDay[] {
  const activities = dashboard.recent_activities.filter((activity) => activity.start_time_local?.startsWith(selectedDay));
  const plans = dashboard.planned_workouts.filter((plan) => plan.scheduled_date === selectedDay);
  const groups = new Map<number, AthleteDay>();

  function groupFor(athleteId: number, name: string) {
    const current = groups.get(athleteId);
    if (current) {
      if (current.athleteName === "Athlete" && name) current.athleteName = name;
      return current;
    }
    const created: AthleteDay = { athleteId, athleteName: name || "Athlete", planned: [], activities: [] };
    groups.set(athleteId, created);
    return created;
  }

  for (const athlete of dashboard.athletes) groupFor(athlete.id, athlete.display_name);
  for (const plan of plans) groupFor(plan.athlete_id, plan.athlete_name || "Athlete").planned.push(plan);
  for (const activity of activities) groupFor(activity.athlete_id, activity.athlete_name || "Athlete").activities.push(activity);

  const rosterIds = dashboard.athletes.map((athlete) => athlete.id);
  const order = [...rosterIds, ...[...groups.keys()].filter((athleteId) => !rosterIds.includes(athleteId))];
  return order.flatMap((athleteId) => {
    const group = groups.get(athleteId);
    if (!group) return [];
    group.activities.sort((a, b) => (a.start_time_local ?? "").localeCompare(b.start_time_local ?? ""));
    return [group];
  });
}

function milesOf(activity: DashboardActivity) {
  return activity.distance_meters == null ? null : activity.distance_meters / 1609.344;
}

function totalMiles(activities: DashboardActivity[]) {
  const miles = activities.map(milesOf).filter((miles): miles is number => miles != null);
  if (miles.length === 0) return null;
  return miles.reduce((sum, miles) => sum + miles, 0);
}

function dayStatus(group: AthleteDay) {
  if (group.activities.length > 0 && group.planned.length > 0) return "Completed";
  if (group.activities.length > 0) return "Unplanned";
  if (group.planned.length > 0) return "Pending";
  return "Unplanned";
}

function completedLine(activity: DashboardActivity) {
  const miles = milesOf(activity);
  const distance = miles == null ? "Run" : `${miles.toFixed(2)} mi`;
  const pace = paceLabel(activity.average_pace_seconds_per_mile);
  const type = activity.workout_type;
  if (type === "hill_sprints") {
    const count = activity.repetition_count;
    return count ? `${distance} · ${count} hill sprints` : `${distance} hill sprints`;
  }
  if (type === "easy" || type === "recovery") return pace === "—" ? `${distance} easy run` : `${distance} easy run · ${pace}`;
  if (type === "long_run") return pace === "—" ? `${distance} long run` : `${distance} long run · ${pace}`;
  if (type === "strides") {
    const count = activity.repetition_count;
    return count ? `${distance} · ${count} strides` : `${distance} strides`;
  }
  if (type) {
    const label = type.replaceAll("_", " ");
    return pace === "—" ? `${distance} ${label}` : `${distance} ${label} · ${pace}`;
  }
  return pace === "—" ? distance : `${distance} · ${pace}`;
}

function reviewLine(count: number) {
  if (count === 0) return "No activity recorded yet.";
  if (count === 1) return "One activity recorded. Open the athlete detail for the full coaching assessment.";
  const words = ["Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine"];
  const label = words[count - 2] ?? String(count);
  const together = count === 2 ? "both" : "them";
  return `${label} activities recorded. Review ${together} together for the day's coaching assessment.`;
}

function AthletePanel({ group, open, onToggle }: { group: AthleteDay; open: boolean; onToggle: () => void }) {
  const status = dayStatus(group);
  const miles = totalMiles(group.activities);
  const milesText = miles == null ? null : `${miles.toFixed(2)} mi`;
  const planText = group.planned.length === 0 ? "No workout assigned" : group.planned.map(plannedLabel).join(" · ");
  const summary = group.activities.length === 0
    ? `${planText} · No activity yet`
    : `${planText} · ${milesText ?? "Distance unavailable"}${group.activities.length === 1 ? "" : ` · ${group.activities.length} runs`}`;
  const statusClass = status === "Completed" ? "text-emerald-700" : status === "Pending" ? "text-amber-700" : "text-muted-foreground";

  return (
    <article className="rounded-xl border border-foreground/10 bg-white">
      <div
        role="button"
        tabIndex={0}
        onClick={onToggle}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            onToggle();
          }
        }}
        aria-expanded={open}
        className="flex w-full cursor-pointer items-start gap-3 px-4 py-4 text-left"
      >
        <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-neutral-100 text-sm font-semibold">
          {initials(group.athleteName)}
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-baseline gap-x-2">
            <Link href={`/athletes/${group.athleteId}`} onClick={(event) => event.stopPropagation()} className="font-semibold hover:underline">
              <AthleteName name={group.athleteName} />
            </Link>
            <span className={`text-sm ${statusClass}`}>{status}</span>
          </span>
          <span className="mt-0.5 block text-sm text-muted-foreground">{summary}</span>
        </span>
        {open ? <ChevronUp className="mt-1 size-4 shrink-0 text-muted-foreground" /> : <ChevronDown className="mt-1 size-4 shrink-0 text-muted-foreground" />}
      </div>
      {open ? (
        <div className="space-y-5 border-t border-foreground/10 px-4 py-4">
          <div className="grid gap-5 sm:grid-cols-2">
            <div>
              <p className="flex items-center gap-2 text-xs tracking-[0.14em] text-muted-foreground uppercase">
                <Calendar className="size-3.5" />
                Planned
              </p>
              <p className="mt-2 font-semibold">{group.planned.length === 0 ? "No workout assigned" : planText}</p>
              <p className="mt-1 text-sm text-muted-foreground">
                {group.planned.length === 0 ? "No prescribed workout to compare against." : "The workout stored for this day."}
              </p>
            </div>
            <div>
              <p className="flex items-center gap-2 text-xs tracking-[0.14em] text-muted-foreground uppercase">
                <CircleCheck className="size-3.5" />
                Completed
              </p>
              <p className="mt-2 font-semibold">{milesText ? `${milesText} total` : "No activity yet"}</p>
              {group.activities.length === 0 ? (
                <p className="mt-1 text-sm text-muted-foreground">Nothing recorded for this day.</p>
              ) : (
                <ul className="mt-1 space-y-1 text-sm text-muted-foreground">
                  {group.activities.map((activity) => (
                    <li key={`${activity.garmin_activity_id}-${activity.start_time_local}`}>{completedLine(activity)}</li>
                  ))}
                </ul>
              )}
            </div>
          </div>
          <div>
            <p className="flex items-center gap-2 text-sm font-medium">
              <Sparkles className="size-3.5" />
              Coach&apos;s review
            </p>
            <p className="mt-1 text-sm text-muted-foreground">{reviewLine(group.activities.length)}</p>
          </div>
          <p className="text-right text-sm">
            <Link href={`/athletes/${group.athleteId}`} className="text-muted-foreground hover:text-foreground hover:underline">
              Full workout analysis in athlete detail →
            </Link>
          </p>
        </div>
      ) : null}
    </article>
  );
}

function plannedLabel(plan: PlannedWorkout) {
  const extras = (plan.detail ?? "").split(" · ").filter((part) => /\d/.test(part));
  return [plan.title, ...extras].filter(Boolean).join(", ");
}

function initials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return parts.slice(0, 2).map((part) => part[0]?.toUpperCase() ?? "").join("") || "A";
}

function paceLabel(seconds: number | null | undefined) {
  if (seconds == null || !Number.isFinite(seconds)) return "—";
  const rounded = Math.round(seconds);
  const minutes = Math.floor(rounded / 60);
  return `${minutes}:${String(rounded % 60).padStart(2, "0")} /mi`;
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
          {syncing ? "Syncing" : "Sync athlete runs"}
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
  const [openAthletes, setOpenAthletes] = useState<number[]>([]);
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

  const groups = dashboard && selectedDay ? athletesForDay(dashboard, selectedDay) : [];
  const groupKey = groups.map((group) => group.athleteId).join(",");
  useEffect(() => {
    setOpenAthletes(groupKey ? [Number(groupKey.split(",")[0])] : []);
  }, [selectedDay, groupKey]);

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
          {shiftDay(selectedDay, -parseDay(selectedDay).getDay()) !== dashboard.week_start ? (
            <p className="text-sm text-muted-foreground">Loading {dayLabel(selectedDay)}…</p>
          ) : (
            <section className="rounded-xl border border-foreground/10 bg-white px-4 py-4 sm:px-5">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h2 className="font-heading text-xl tracking-tight">Daily Training</h2>
                  <p className="mt-1 text-sm text-muted-foreground">{fullDayLabel(selectedDay)}</p>
                </div>
                <p className="text-sm text-muted-foreground">{groups.length} {groups.length === 1 ? "athlete" : "athletes"}</p>
              </div>
              {groups.length > 0 ? (
                <div className="mt-3 flex justify-end">
                  <button
                    type="button"
                    className="text-sm text-muted-foreground hover:text-foreground"
                    onClick={() => setOpenAthletes(openAthletes.length === groups.length ? [] : groups.map((group) => group.athleteId))}
                  >
                    {openAthletes.length === groups.length ? "Collapse all" : "Expand all"}
                  </button>
                </div>
              ) : null}
              {groups.length === 0 ? (
                <p className="mt-4 text-sm text-muted-foreground">No athletes on the roster.</p>
              ) : (
                <div className="mt-4 space-y-3">
                  {groups.map((group) => (
                    <AthletePanel
                      key={group.athleteId}
                      group={group}
                      open={openAthletes.includes(group.athleteId)}
                      onToggle={() =>
                        setOpenAthletes((current) =>
                          current.includes(group.athleteId) ? current.filter((id) => id !== group.athleteId) : [...current, group.athleteId],
                        )
                      }
                    />
                  ))}
                </div>
              )}
            </section>
          )}
          <details className="group rounded-xl border border-foreground/10 bg-white">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-4 [&::-webkit-details-marker]:hidden">
              <span className="flex items-center gap-2">
                <span className="font-heading text-xl tracking-tight">Coaching summary</span>
                <span className="group/info relative">
                  <button
                    type="button"
                    className="rounded-full p-1 text-muted-foreground"
                    aria-label={selectedDay > dashboard.today ? "preview of the planned workouts for this day" : "summary of athletes workouts for today"}
                    onClick={(event) => event.preventDefault()}
                  >
                    <Info className="size-4" />
                  </button>
                  <p className="pointer-events-none absolute top-full left-0 z-10 mt-2 hidden w-52 border border-foreground/20 bg-background px-3 py-2 text-[11px] leading-snug text-foreground group-hover/info:block group-focus-within/info:block">
                    {selectedDay > dashboard.today ? "preview of the planned workouts for this day" : "summary of athletes workouts for today"}
                  </p>
                </span>
              </span>
              <span className="flex items-center gap-2">
                <span className="group/bell relative">
                  <button
                    type="button"
                    onClick={(event) => {
                      event.preventDefault();
                      void toggleEmail();
                    }}
                    className={`rounded-full border p-2 ${
                      dashboard.coach.email_notifications_enabled
                        ? "border-emerald-300 bg-emerald-50 text-emerald-900"
                        : "border-border text-muted-foreground"
                    }`}
                    aria-label="Add email and text notifications coming soon"
                  >
                    {dashboard.coach.email_notifications_enabled ? <Bell className="size-4" /> : <BellOff className="size-4" />}
                  </button>
                  <p className="pointer-events-none absolute top-full right-0 z-10 mt-2 hidden w-44 border border-foreground/20 bg-background px-3 py-2 text-right text-[11px] leading-snug tracking-[0.08em] text-foreground uppercase group-hover/bell:block group-focus-within/bell:block">
                    Add email and text notifications coming soon
                  </p>
                </span>
                <ChevronDown className="size-4 text-muted-foreground transition-transform group-open:rotate-180" />
              </span>
            </summary>
            <div className="space-y-4 border-t border-foreground/10 px-4 py-4">
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
            </div>
          </details>
        </>
      ) : null}
    </div>
  );
}
