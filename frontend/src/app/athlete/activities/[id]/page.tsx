"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { useAthlete } from "@/components/athlete-frame";
import { CommentList, durationLabel, FeedbackForm, fieldClass, milesLabel, paceLabel } from "@/components/athlete-ui";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { editPortalActivity, errorMessage, getPortalActivity, type PortalActivity, type PlannedWorkout, type WorkoutFeedback, type WorkoutNote } from "@/lib/api";

export default function AthleteActivityPage() {
  const params = useParams<{ id: string }>();
  const garminId = Number(params.id);
  const { athleteId } = useAthlete();
  const [activity, setActivity] = useState<PortalActivity | null>(null);
  const [planned, setPlanned] = useState<PlannedWorkout | null>(null);
  const [feedback, setFeedback] = useState<WorkoutFeedback | null>(null);
  const [comments, setComments] = useState<WorkoutNote[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    const detail = await getPortalActivity(athleteId, garminId);
    setActivity(detail.activity);
    setPlanned(detail.planned);
    setFeedback(detail.feedback);
    setComments(detail.comments);
  }, [athleteId, garminId]);

  useEffect(() => {
    if (!Number.isFinite(garminId)) return;
    const timer = window.setTimeout(() => {
      void load().catch((loadError: unknown) => setError(errorMessage(loadError)));
    }, 0);
    return () => window.clearTimeout(timer);
  }, [garminId, load]);

  if (!activity && !error) return <p className="text-sm text-muted-foreground">Loading the run…</p>;
  if (!activity) return <p className="text-sm text-destructive">{error}</p>;

  return (
    <div className="space-y-4">
      <div>
        <p className="text-xs text-muted-foreground"><Link href="/athlete" className="hover:underline">Home</Link></p>
        <h1 className="font-heading text-2xl tracking-tight sm:text-3xl">{activity.name || "Run"}</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          {activity.start_time_local} · {milesLabel(activity.distance_miles)} · {paceLabel(activity.pace_seconds_per_mile)} · {durationLabel(activity.duration_seconds)}
        </p>
      </div>
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      {notice ? <p className="text-sm">{notice}</p> : null}
      {planned ? (
        <Card>
          <CardHeader>
            <CardTitle>Compared with the plan</CardTitle>
          </CardHeader>
          <CardContent className="text-sm">
            <Link href={`/athlete/workouts/${planned.id}`} className="font-medium hover:underline">{planned.title}</Link>
            <p className="mt-1 text-muted-foreground">{planned.summary || planned.status.replaceAll("_", " ")}</p>
          </CardContent>
        </Card>
      ) : null}
      <Card>
        <CardHeader>
          <CardTitle>Correct this run</CardTitle>
        </CardHeader>
        <CardContent>
          <EditForm
            activity={activity}
            onSave={async (body) => {
              setNotice(null);
              const updated = await editPortalActivity(athleteId, garminId, body);
              setActivity(updated);
              setNotice("Run updated. A later Garmin sync keeps these corrections.");
            }}
            onError={setError}
          />
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>How it felt</CardTitle></CardHeader>
        <CardContent>
          <FeedbackForm athleteId={athleteId} garminActivityId={garminId} scheduledWorkoutId={planned?.id} initial={feedback} onSaved={setFeedback} />
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Notes</CardTitle></CardHeader>
        <CardContent>
          <CommentList
            athleteId={athleteId}
            author="athlete"
            comments={comments}
            garminActivityId={garminId}
            scheduledWorkoutId={planned?.id}
            onPosted={(note) => setComments((current) => [...current, note])}
          />
        </CardContent>
      </Card>
    </div>
  );
}

function EditForm({
  activity,
  onSave,
  onError,
}: {
  activity: PortalActivity;
  onSave: (body: Record<string, unknown>) => Promise<void>;
  onError: (message: string) => void;
}) {
  const [name, setName] = useState(activity.name ?? "");
  const [distance, setDistance] = useState(activity.distance_miles == null ? "" : String(Number(activity.distance_miles.toFixed(2))));
  const [duration, setDuration] = useState(activity.duration_seconds == null ? "" : durationLabel(activity.duration_seconds));
  const [heart, setHeart] = useState(activity.average_heart_rate_bpm == null ? "" : String(Math.round(activity.average_heart_rate_bpm)));
  const [notes, setNotes] = useState(activity.notes ?? "");

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    try {
      await onSave({
        name,
        distance_miles: distance.trim() ? Number(distance) : null,
        duration_seconds: parseDuration(duration),
        average_heart_rate_bpm: heart.trim() ? Number(heart) : null,
        notes,
      });
    } catch (saveError) {
      onError(errorMessage(saveError));
    }
  }

  return (
    <form onSubmit={(event) => void onSubmit(event)} className="grid gap-3 sm:grid-cols-2">
      <label className="text-sm sm:col-span-2">Name<input value={name} onChange={(event) => setName(event.target.value)} className={fieldClass} /></label>
      <label className="text-sm">Distance, miles<input value={distance} onChange={(event) => setDistance(event.target.value)} className={fieldClass} /></label>
      <label className="text-sm">Duration<input value={duration} onChange={(event) => setDuration(event.target.value)} placeholder="45:00" className={fieldClass} /></label>
      <label className="text-sm">Heart rate<input value={heart} onChange={(event) => setHeart(event.target.value)} className={fieldClass} /></label>
      <label className="text-sm sm:col-span-2">Notes<textarea value={notes} onChange={(event) => setNotes(event.target.value)} className="mt-1 min-h-20 w-full rounded-lg border border-input bg-card px-3 py-2 text-sm" /></label>
      <div className="sm:col-span-2"><Button type="submit">Save corrections</Button></div>
    </form>
  );
}

function parseDuration(value: string): number | null {
  const text = value.trim();
  if (!text) return null;
  const parts = text.split(":").map(Number);
  if (parts.some((part) => !Number.isFinite(part))) return null;
  if (parts.length === 2) return parts[0] * 60 + parts[1];
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
  return null;
}
