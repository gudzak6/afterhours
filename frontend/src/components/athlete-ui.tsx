"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { Button } from "@/components/ui/button";
import { errorMessage, saveWorkoutFeedback, addWorkoutComment, type PlannedWorkout, type PortalActivity, type WorkoutFeedback, type WorkoutNote } from "@/lib/api";

export const fieldClass = "mt-1 h-9 w-full rounded-lg border border-input bg-card px-3 text-sm";
export const areaClass = "mt-1 min-h-24 w-full rounded-lg border border-input bg-card px-3 py-2 text-sm";

export function paceLabel(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return "—";
  const rounded = Math.round(seconds);
  const minutes = Math.floor(rounded / 60);
  const secs = rounded % 60;
  return `${minutes}:${String(secs).padStart(2, "0")} /mi`;
}

export function milesLabel(miles: number | null | undefined): string {
  if (miles == null || !Number.isFinite(miles)) return "—";
  return `${miles.toFixed(2)} mi`;
}

export function durationLabel(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return "—";
  const total = Math.round(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const remainder = total % 60;
  if (hours > 0) return `${hours}:${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
  return `${minutes}:${String(remainder).padStart(2, "0")}`;
}

export function workoutDetail(workout: PlannedWorkout): string {
  const bits = [
    workout.workout_type?.replaceAll("_", " "),
    workout.distance_miles == null ? null : `${workout.distance_miles.toFixed(2)} mi`,
    workout.repetitions ? `${workout.repetitions} x ${workout.rep_distance_miles?.toFixed(2) ?? "?"} mi` : null,
    workout.target_pace ? `${workout.target_pace}/mi` : null,
    workout.intensity,
  ].filter(Boolean);
  return bits.join(" · ");
}

export function planText(workout: PlannedWorkout): string {
  const written = workout.details?.trim();
  if (written) return written;
  const extra = [workoutDetail(workout), workout.coach_notes?.trim()].filter(Boolean).join("\n");
  return extra ? `${workout.title}\n${extra}` : workout.title;
}

export function ActivityLine({ activity }: { activity: PortalActivity }) {
  return (
    <Link href={`/athlete/activities/${activity.garmin_activity_id}`} className="block rounded-md hover:bg-muted">
      <span className="font-medium">{activity.name || "Run"}</span>
      <p className="text-muted-foreground">
        {milesLabel(activity.distance_miles)} · {paceLabel(activity.pace_seconds_per_mile)}
        {activity.manual ? " · logged" : ""}
      </p>
    </Link>
  );
}

export function FeedbackForm({
  athleteId,
  scheduledWorkoutId,
  garminActivityId,
  initial,
  onSaved,
}: {
  athleteId: number;
  scheduledWorkoutId?: number | null;
  garminActivityId?: number | null;
  initial: WorkoutFeedback | null;
  onSaved: (feedback: WorkoutFeedback) => void;
}) {
  const [rpe, setRpe] = useState(initial?.rpe == null ? "" : String(initial.rpe));
  const [fatigue, setFatigue] = useState(initial?.fatigue == null ? "" : String(initial.fatigue));
  const [soreness, setSoreness] = useState(initial?.soreness == null ? "" : String(initial.soreness));
  const [comment, setComment] = useState(initial?.comment ?? "");
  const [notice, setNotice] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setNotice(null);
    try {
      const saved = await saveWorkoutFeedback(athleteId, {
        scheduled_workout_id: scheduledWorkoutId ?? null,
        garmin_activity_id: garminActivityId ?? null,
        rpe: rpe.trim() ? Number(rpe) : null,
        fatigue: fatigue.trim() ? Number(fatigue) : null,
        soreness: soreness.trim() ? Number(soreness) : null,
        comment,
      });
      onSaved(saved);
      setNotice("Feedback saved.");
    } catch (saveError) {
      setNotice(errorMessage(saveError));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={(event) => void onSubmit(event)} className="grid gap-3 sm:grid-cols-3">
      <label className="text-sm">
        RPE, 1–10
        <input value={rpe} onChange={(event) => setRpe(event.target.value)} inputMode="numeric" className={fieldClass} />
      </label>
      <label className="text-sm">
        Fatigue, 1–5
        <input value={fatigue} onChange={(event) => setFatigue(event.target.value)} inputMode="numeric" className={fieldClass} />
      </label>
      <label className="text-sm">
        Soreness, 1–5
        <input value={soreness} onChange={(event) => setSoreness(event.target.value)} inputMode="numeric" className={fieldClass} />
      </label>
      <label className="text-sm sm:col-span-3">
        Comment
        <textarea value={comment} onChange={(event) => setComment(event.target.value)} className={areaClass} />
      </label>
      <div className="sm:col-span-3">
        <Button type="submit" disabled={saving}>{saving ? "Saving…" : "Save feedback"}</Button>
        {notice ? <p className="mt-2 text-sm">{notice}</p> : null}
      </div>
    </form>
  );
}

export function CommentList({
  athleteId,
  author,
  comments,
  scheduledWorkoutId,
  garminActivityId,
  onPosted,
}: {
  athleteId: number;
  author: "athlete" | "coach";
  comments: WorkoutNote[];
  scheduledWorkoutId?: number | null;
  garminActivityId?: number | null;
  onPosted: (note: WorkoutNote) => void;
}) {
  const [body, setBody] = useState("");
  const [notice, setNotice] = useState<string | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setNotice(null);
    try {
      const note = await addWorkoutComment(athleteId, {
        author,
        body,
        scheduled_workout_id: scheduledWorkoutId ?? null,
        garmin_activity_id: garminActivityId ?? null,
      });
      setBody("");
      onPosted(note);
    } catch (postError) {
      setNotice(errorMessage(postError));
    }
  }

  return (
    <div className="space-y-3">
      {comments.length === 0 ? <p className="text-sm text-muted-foreground">No notes on this workout yet.</p> : null}
      <ul className="space-y-2 text-sm">
        {comments.map((note) => (
          <li key={note.id} className="rounded-lg bg-muted px-3 py-2">
            <p className="text-xs tracking-wide text-muted-foreground uppercase">{note.author}</p>
            <p className="mt-1 whitespace-pre-wrap">{note.body}</p>
          </li>
        ))}
      </ul>
      <form onSubmit={(event) => void onSubmit(event)} className="space-y-2">
        <textarea value={body} onChange={(event) => setBody(event.target.value)} placeholder="Leave a note or a question" className={areaClass} />
        <Button type="submit">Send note</Button>
        {notice ? <p className="text-sm text-destructive">{notice}</p> : null}
      </form>
    </div>
  );
}
