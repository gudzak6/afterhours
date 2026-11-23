"use client";

import Link from "next/link";
import { Calendar, ChevronDown, ChevronLeft, ChevronRight, ChevronUp, CircleCheck, Info, RefreshCw, Sparkles } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { AthleteName } from "@/components/athlete-name";
import { mirrorRosterRuns } from "@/lib/account";
import {
  activityPath,
  errorMessage,
  getCoachReview,
  getDashboard,
  syncRoster,
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
  if (group.planned.length > 0) return "Planned";
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

function CoachReview({ athleteId, day }: { athleteId: number; day: string }) {
  const key = `${athleteId}:${day}`;
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<{ key: string; status: "loading" | "ready" | "error"; paragraph: string; error: string } | null>(null);

  useEffect(() => {
    let cancelled = false;
    setState({ key, status: "loading", paragraph: "", error: "" });
    getCoachReview(athleteId, day).then(
      (result) => {
        if (!cancelled) setState({ key, status: "ready", paragraph: result.paragraph, error: "" });
      },
      (loadError) => {
        if (!cancelled) setState({ key, status: "error", paragraph: "", error: errorMessage(loadError) });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [athleteId, day, attempt, key]);

  const current = state?.key === key ? state : null;
  return (
    <div>
      <div className="flex items-center gap-1 text-sm font-medium">
        <Sparkles className="size-3.5" />
        Coach&apos;s review
        <span className="group/info relative">
          <button
            type="button"
            className="rounded-full p-1 text-muted-foreground"
            aria-label="AI-generated coaching assessment based on the athlete's planned workout, completed activity, and recent training."
            onClick={(event) => event.stopPropagation()}
          >
            <Info className="size-4" />
          </button>
          <p className="pointer-events-none absolute top-full left-0 z-10 mt-2 hidden w-64 border border-foreground/20 bg-background px-3 py-2 text-[11px] leading-snug text-foreground normal-case group-hover/info:block group-focus-within/info:block">
            AI-generated coaching assessment based on the athlete&apos;s planned workout, completed activity, and recent training.
          </p>
        </span>
      </div>
      {current?.status === "error" ? (
        <p className="mt-1 text-sm text-muted-foreground">
          {current.error}{" "}
          <button type="button" className="underline" onClick={() => setAttempt((value) => value + 1)}>
            Try again
          </button>
        </p>
      ) : (
        <p className="mt-1 text-sm leading-6 text-muted-foreground">
          {current?.status === "ready" ? current.paragraph : "Writing Coach's review…"}
        </p>
      )}
    </div>
  );
}

function AthletePanel({
  group,
  day,
  open,
  onToggle,
  planHref,
}: {
  group: AthleteDay;
  day: string;
  open: boolean;
  onToggle: () => void;
  planHref: string | null;
}) {
  const status = dayStatus(group);
  const miles = totalMiles(group.activities);
  const milesText = miles == null ? null : `${miles.toFixed(2)} mi`;
  const planText = group.planned.length === 0 ? "No workout assigned" : group.planned.map(plannedLabel).join(" · ");
  const summary = group.activities.length === 0
    ? `${planText} · No activity yet`
    : `${planText} · ${milesText ?? "Distance unavailable"}${group.activities.length === 1 ? "" : ` · ${group.activities.length} runs`}`;
  const statusClass = status === "Completed" ? "text-emerald-700" : status === "Planned" ? "text-amber-700" : "text-muted-foreground";

  return (
    <article className="rounded-lg border border-border bg-background">
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
        className="flex w-full cursor-pointer items-start gap-3 px-3 py-3 text-left"
      >
        <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-neutral-100 text-sm font-semibold">
          {initials(group.athleteName)}
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-baseline gap-x-2">
            <Link href={`/athletes/${group.athleteId}`} onClick={(event) => event.stopPropagation()} className="font-semibold hover:underline">
              <AthleteName name={group.athleteName} />
            </Link>
            {status === "Unplanned" ? null : <span className={`text-sm ${statusClass}`}>{status}</span>}
          </span>
          <span className="mt-0.5 block text-sm text-muted-foreground">
            {planHref ? (
              <>
                <Link href={planHref} onClick={(event) => event.stopPropagation()} className="hover:text-foreground hover:underline">
                  {planText}
                </Link>
                {group.activities.length === 0
                  ? " · No activity yet"
                  : ` · ${milesText ?? "Distance unavailable"}${group.activities.length === 1 ? "" : ` · ${group.activities.length} runs`}`}
              </>
            ) : summary}
          </span>
        </span>
        {open ? <ChevronUp className="mt-1 size-4 shrink-0 text-muted-foreground" /> : <ChevronDown className="mt-1 size-4 shrink-0 text-muted-foreground" />}
      </div>
      {open ? (
        <div className="space-y-3 border-t border-border px-3 py-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-2">
              <p className="flex items-center gap-2 text-xs tracking-[0.14em] text-muted-foreground uppercase">
                <Calendar className="size-3.5" />
                Planned
              </p>
              {group.planned.length === 0 ? (
                <p className="text-sm text-muted-foreground">No workout assigned</p>
              ) : group.planned.map((plan) => (
                <div key={plan.id} className="rounded-lg border border-border bg-background px-2.5 py-2">
                  <span className="min-w-0">
                    <span className="block text-sm font-medium">{plan.title}</span>
                    {plan.detail ? <span className="block text-xs text-muted-foreground">{(plan.detail.split(" · ").filter((part) => /\d/.test(part)).join(" · ")) || plan.detail}</span> : null}
                  </span>
                </div>
              ))}
            </div>
            <div className="space-y-2">
              <p className="flex items-center gap-2 text-xs tracking-[0.14em] text-muted-foreground uppercase">
                <CircleCheck className="size-3.5" />
                Completed
              </p>
              {group.activities.length === 0 ? (
                <p className="text-sm text-muted-foreground">No activity yet</p>
              ) : group.activities.map((activity) => (
                <Link
                  key={`${activity.garmin_activity_id}-${activity.start_time_local}`}
                  href={activityPath(activity.garmin_activity_id, group.athleteId)}
                  className="block rounded-lg border border-border bg-background px-2.5 py-2 text-sm hover:bg-muted"
                >
                  {completedLine(activity)}
                </Link>
              ))}
            </div>
          </div>
          <CoachReview athleteId={group.athleteId} day={day} />
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

const SCHEDULE_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function mondayOf(iso: string): string {
  const offset = (parseDay(iso).getDay() + 6) % 7;
  return shiftDay(iso, -offset);
}

function weekRangeLabel(start: string): string {
  const end = parseDay(shiftDay(start, 6));
  const begin = parseDay(start);
  const left = `${MONTHS[begin.getMonth()].slice(0, 3)} ${begin.getDate()}`;
  const right = begin.getMonth() === end.getMonth()
    ? String(end.getDate())
    : `${MONTHS[end.getMonth()].slice(0, 3)} ${end.getDate()}`;
  return `${left} – ${right}`;
}

function TrainingSchedule({
  selectedDay,
  markedDays,
  reloading,
  syncing,
  athletes,
  athleteFilter,
  onAthlete,
  onSelect,
  onShiftWeek,
  onReload,
  children,
}: {
  selectedDay: string;
  markedDays: Set<string>;
  reloading: boolean;
  syncing: boolean;
  athletes: Array<{ id: number; display_name: string }>;
  athleteFilter: number | "all";
  onAthlete: (athleteId: number | "all") => void;
  onSelect: (day: string) => void;
  onShiftWeek: (weeks: number) => void;
  onReload: () => void;
  children: ReactNode;
}) {
  const weekStart = mondayOf(selectedDay);
  const days = SCHEDULE_DAYS.map((_, index) => shiftDay(weekStart, index));
  return (
    <section className="rounded-xl border border-border bg-card px-3 py-3 sm:px-4">
      <div className="flex flex-col gap-3 md:grid md:grid-cols-[auto_minmax(0,1fr)_auto] md:items-center md:gap-4 lg:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)]">
        <h2 className="font-heading text-xl tracking-tight">Athletes Training Week</h2>
        <div className="flex items-center justify-between gap-3 sm:justify-center">
          <button
            type="button"
            onClick={() => onShiftWeek(-1)}
            className="inline-flex size-10 shrink-0 items-center justify-center rounded-full border border-border text-muted-foreground hover:bg-muted"
            aria-label="Previous week"
          >
            <ChevronLeft className="size-4" />
          </button>
          <p className="min-w-28 text-center text-sm font-medium">{weekRangeLabel(weekStart)}</p>
          <button
            type="button"
            onClick={() => onShiftWeek(1)}
            className="inline-flex size-10 shrink-0 items-center justify-center rounded-full border border-border text-muted-foreground hover:bg-muted"
            aria-label="Next week"
          >
            <ChevronRight className="size-4" />
          </button>
        </div>
        <div className="flex items-center gap-2 md:justify-end">
          <select
            aria-label="Athlete"
            value={athleteFilter === "all" ? "all" : String(athleteFilter)}
            onChange={(event) => onAthlete(event.target.value === "all" ? "all" : Number(event.target.value))}
            className="h-10 min-w-0 flex-1 rounded-full border border-border bg-background px-3 text-sm md:w-44 md:flex-none"
          >
            <option value="all">All athletes</option>
            {athletes.map((athlete) => (
              <option key={athlete.id} value={athlete.id}>{athlete.display_name}</option>
            ))}
          </select>
          <button
            type="button"
            onClick={onReload}
            disabled={reloading || syncing}
            className="inline-flex h-10 shrink-0 items-center gap-1.5 rounded-full border border-border px-3 text-sm text-muted-foreground hover:bg-muted disabled:opacity-60"
          >
            <RefreshCw className={`size-3.5 ${reloading || syncing ? "animate-spin" : ""}`} />
            {syncing ? "Syncing" : "Sync runs"}
          </button>
        </div>
      </div>
      <div className="mt-3 grid grid-cols-7 gap-1.5 sm:gap-3">
        {days.map((day, index) => {
          const date = parseDay(day);
          const selected = day === selectedDay;
          const marked = markedDays.has(day);
          return (
            <button
              key={day}
              type="button"
              onClick={() => onSelect(day)}
              aria-pressed={selected}
              aria-label={`${SCHEDULE_DAYS[index]} ${date.getDate()}${marked ? ", workout planned" : ""}`}
              className={`flex min-h-16 flex-col items-center justify-center gap-1 rounded-lg border px-1 py-2 ${
                selected
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-border bg-background text-foreground hover:bg-muted"
              }`}
            >
              <span className="text-[10px] tracking-wide uppercase sm:text-xs">{SCHEDULE_DAYS[index]}</span>
              <span className="text-base leading-none font-medium sm:text-lg">{date.getDate()}</span>
              <span className={`size-1.5 rounded-full ${marked ? (selected ? "bg-primary-foreground" : "bg-primary") : "invisible"}`} />
            </button>
          );
        })}
      </div>
      <div className="mt-3 border-t border-border pt-3">{children}</div>
    </section>
  );
}

export default function DashboardPage() {
  const [dashboard, setDashboard] = useState<CoachDashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [selectedDay, setSelectedDay] = useState<string | null>(null);
  const [selectedAthlete, setSelectedAthlete] = useState<number | "all">("all");
  const [openAthletes, setOpenAthletes] = useState<number[]>([]);
  const [reloading, setReloading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const requestId = useRef(0);

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

  const groups = dashboard && selectedDay ? athletesForDay(dashboard, selectedDay) : [];
  const roster = dashboard?.athletes ?? [];
  const athleteFilter = roster.some((athlete) => athlete.id === selectedAthlete) ? selectedAthlete : "all";
  const visibleGroups = athleteFilter === "all" ? groups : groups.filter((group) => group.athleteId === athleteFilter);
  const groupKey = visibleGroups.map((group) => group.athleteId).join(",");
  useEffect(() => {
    setOpenAthletes(groupKey ? [Number(groupKey.split(",")[0])] : []);
  }, [selectedDay, groupKey]);

  return (
    <div className="space-y-4">
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      {notice ? <p className="text-sm text-muted-foreground">{notice}</p> : null}
      {!dashboard && !error ? <p className="text-sm text-muted-foreground">Loading the roster…</p> : null}

      {dashboard && selectedDay ? (
        <>
          <TrainingSchedule
            selectedDay={selectedDay}
            markedDays={new Set(dashboard.planned_workouts.filter((plan) => athleteFilter === "all" || plan.athlete_id === athleteFilter).map((plan) => plan.scheduled_date))}
            reloading={reloading}
            syncing={syncing}
            athletes={roster}
            athleteFilter={athleteFilter}
            onAthlete={setSelectedAthlete}
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
          >
            {shiftDay(selectedDay, -parseDay(selectedDay).getDay()) !== dashboard.week_start ? (
              <p className="text-sm text-muted-foreground">Loading {dayLabel(selectedDay)}…</p>
            ) : (
              <>
                <div className="flex items-end justify-between gap-3">
                  <p className="text-sm text-muted-foreground">{fullDayLabel(selectedDay)}</p>
                  <div className="flex items-center gap-3">
                    <p className="text-sm text-muted-foreground">{visibleGroups.length} {visibleGroups.length === 1 ? "athlete" : "athletes"}</p>
                    {visibleGroups.length > 0 ? (
                      <button
                        type="button"
                        className="text-sm text-muted-foreground hover:text-foreground"
                        onClick={() => setOpenAthletes(openAthletes.length === visibleGroups.length ? [] : visibleGroups.map((group) => group.athleteId))}
                      >
                        {openAthletes.length === visibleGroups.length ? "Collapse all" : "Expand all"}
                      </button>
                    ) : null}
                  </div>
                </div>
                {visibleGroups.length === 0 ? (
                  <p className="mt-3 text-sm text-muted-foreground">No athletes on the roster.</p>
                ) : (
                  <div className="mt-3 space-y-3">
                    {visibleGroups.map((group) => (
                      <AthletePanel
                        key={group.athleteId}
                        group={group}
                        day={selectedDay}
                        planHref={selectedDay > dashboard.today && group.planned.length > 0 ? `/athletes/${group.athleteId}?section=plan&day=${selectedDay}` : null}
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
              </>
            )}
          </TrainingSchedule>
        </>
      ) : null}
    </div>
  );
}
