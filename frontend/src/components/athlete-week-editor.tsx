"use client";

import { ChevronLeft, ChevronRight, GripVertical } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { planText } from "@/components/athlete-ui";
import { Button } from "@/components/ui/button";
import { errorMessage, getAthleteWeek, rescheduleAthletePlan, type PlanView, type PlannedWorkout } from "@/lib/api";

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function parseDay(iso: string): Date {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(year, (month || 1) - 1, day || 1);
}

function addDays(iso: string, days: number): string {
  const date = parseDay(iso);
  date.setDate(date.getDate() + days);
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

function weekRangeLabel(start: string) {
  const begin = parseDay(start);
  const end = parseDay(addDays(start, 6));
  const left = `${MONTHS[begin.getMonth()]} ${begin.getDate()}`;
  const right = begin.getMonth() === end.getMonth() ? String(end.getDate()) : `${MONTHS[end.getMonth()]} ${end.getDate()}`;
  return `${left} – ${right}`;
}

function weekContaining(weeks: PlanView["weeks"], today: string) {
  const current = weeks.find((item) => item.week_start <= today && addDays(item.week_start, 7) > today);
  if (current) return current.week_start;
  const upcoming = weeks.find((item) => item.week_start > today);
  return upcoming?.week_start ?? weeks.at(-1)?.week_start ?? null;
}

export function AthleteWeekEditor({ athleteId }: { athleteId: number }) {
  const [view, setView] = useState<(PlanView & { today: string }) | null>(null);
  const [week, setWeek] = useState<string | null>(null);
  const [dates, setDates] = useState<Record<number, string>>({});
  const [dropDay, setDropDay] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const applyPlan = useCallback((plan: PlanView & { today: string }, keepWeek?: string | null) => {
    const nextDates: Record<number, string> = {};
    for (const workout of plan.workouts) nextDates[workout.id] = workout.scheduled_date;
    setView(plan);
    setDates(nextDates);
    setWeek(keepWeek && plan.weeks.some((item) => item.week_start === keepWeek) ? keepWeek : weekContaining(plan.weeks, plan.today));
  }, []);

  const load = useCallback(async (keepWeek?: string | null) => {
    applyPlan(await getAthleteWeek(athleteId), keepWeek);
  }, [athleteId, applyPlan]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void load().catch((loadError: unknown) => setError(errorMessage(loadError)));
    }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  const days = week ? WEEKDAYS.map((_, index) => addDays(week, index)) : [];
  const placed = view?.workouts.map((workout) => ({ ...workout, scheduled_date: dates[workout.id] ?? workout.scheduled_date })) ?? [];
  const moves = placed.filter((workout) => {
    const savedDate = view?.workouts.find((item) => item.id === workout.id)?.scheduled_date;
    return savedDate != null && savedDate !== workout.scheduled_date;
  });

  function shiftWeek(delta: number) {
    if (!view || !week) return;
    const index = view.weeks.findIndex((item) => item.week_start === week);
    const next = view.weeks[index + delta];
    if (next) setWeek(next.week_start);
  }

  async function onSave() {
    if (moves.length === 0) return;
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      await rescheduleAthletePlan(athleteId, moves.map((workout) => ({ id: workout.id, scheduled_date: workout.scheduled_date })));
      await load(week);
      setSaved(true);
    } catch (saveError) {
      setError(errorMessage(saveError));
    } finally {
      setSaving(false);
    }
  }

  if (!view && !error) return <p className="text-sm text-muted-foreground">Loading this week…</p>;

  return (
    <div className="space-y-4">
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      {!view || view.weeks.length === 0 ? <p className="text-sm text-muted-foreground">No plan is uploaded yet.</p> : (
        <>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-2">
              <button
                type="button"
                aria-label="Previous week"
                onClick={() => shiftWeek(-1)}
                disabled={view.weeks.findIndex((item) => item.week_start === week) <= 0}
                className="inline-flex size-11 shrink-0 items-center justify-center rounded-full border border-border text-muted-foreground hover:bg-muted disabled:opacity-40"
              >
                <ChevronLeft className="size-4" />
              </button>
              <select
                aria-label="Week"
                value={week ?? ""}
                onChange={(event) => setWeek(event.target.value)}
                className="h-11 min-w-0 flex-1 rounded-full border border-border bg-card px-4 text-sm sm:flex-none"
              >
                {view.weeks.map((item, index) => (
                  <option key={item.week_start} value={item.week_start}>Week {index + 1}</option>
                ))}
              </select>
              <button
                type="button"
                aria-label="Next week"
                onClick={() => shiftWeek(1)}
                disabled={view.weeks.findIndex((item) => item.week_start === week) >= view.weeks.length - 1}
                className="inline-flex size-11 shrink-0 items-center justify-center rounded-full border border-border text-muted-foreground hover:bg-muted disabled:opacity-40"
              >
                <ChevronRight className="size-4" />
              </button>
            </div>
            <div className="flex items-center justify-between gap-3 sm:justify-end sm:gap-6">
              {week ? <p className="text-xs tracking-[0.14em] text-muted-foreground uppercase">{weekRangeLabel(week)}</p> : null}
              <Button type="button" className="min-h-11 shrink-0" onClick={() => void onSave()} disabled={saving || moves.length === 0}>
                {saving ? "Saving…" : "Save week"}
              </Button>
            </div>
          </div>
          <p className="text-sm leading-6 text-muted-foreground">Drag a workout onto another day. Save to update the plan and send Coach Owen a message.</p>
          {saved ? <p className="text-sm text-muted-foreground">Saved. Coach Owen can see the new days, and the change is in your messages.</p> : null}
          <div className="space-y-3">
            {days.map((day, index) => {
              const date = parseDay(day);
              const sessions = placed.filter((workout) => workout.scheduled_date === day);
              return (
                <div
                  key={day}
                  onDragOver={(event) => {
                    event.preventDefault();
                    setDropDay(day);
                  }}
                  onDragLeave={(event) => {
                    if (event.currentTarget.contains(event.relatedTarget as Node | null)) return;
                    setDropDay((current) => (current === day ? null : current));
                  }}
                  onDrop={(event) => {
                    event.preventDefault();
                    setDropDay(null);
                    const workoutId = Number(event.dataTransfer.getData("text/plain"));
                    if (!Number.isFinite(workoutId)) return;
                    setSaved(false);
                    setDates((current) => ({ ...current, [workoutId]: day }));
                  }}
                  className={`flex items-start gap-3 rounded-xl border p-3 sm:p-4 ${dropDay === day ? "border-primary bg-muted" : "border-border"}`}
                >
                  <div className="mt-0.5 flex size-12 shrink-0 flex-col items-center justify-center rounded-full border border-border bg-card text-center">
                    <span className="text-[10px] leading-none tracking-wide uppercase">{WEEKDAYS[index]}</span>
                    <span className="text-sm font-medium leading-none">{date.getDate()}</span>
                  </div>
                  <div className="min-w-0 flex-1 space-y-3">
                    {sessions.length === 0 ? <p className="pt-3 text-sm text-muted-foreground">No workout is scheduled.</p> : sessions.map((workout, workoutIndex) => (
                      <WorkoutCard key={workout.id} workout={workout} moved={moves.some((item) => item.id === workout.id)} disabled={saving} first={workoutIndex === 0} />
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}

function WorkoutCard({ workout, moved, disabled, first }: { workout: PlannedWorkout; moved: boolean; disabled: boolean; first: boolean }) {
  return (
    <article
      aria-label={`Drag ${workout.title} to another day`}
      draggable={!disabled}
      onDragStart={(event) => {
        event.dataTransfer.setData("text/plain", String(workout.id));
        event.dataTransfer.effectAllowed = "move";
      }}
      className={`text-sm ${first ? "" : "border-t border-border pt-3"}`}
    >
      <div className="flex items-start gap-2">
        <GripVertical className="mt-0.5 size-4 shrink-0 cursor-grab text-muted-foreground" aria-hidden="true" />
        <div className="min-w-0">
          <p className="font-medium">{workout.title}</p>
          {planText(workout) !== workout.title ? <p className="mt-1 whitespace-pre-wrap text-muted-foreground">{planText(workout)}</p> : null}
          {moved ? <p className="mt-1 text-xs text-muted-foreground">Not saved yet</p> : null}
        </div>
      </div>
    </article>
  );
}
