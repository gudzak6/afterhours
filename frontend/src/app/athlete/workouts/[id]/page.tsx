"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { useAthlete } from "@/components/athlete-frame";
import { CommentList, FeedbackForm, milesLabel, paceLabel, planText } from "@/components/athlete-ui";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { errorMessage, getAthleteWorkout, matchPortalWorkout, type PlannedWorkout } from "@/lib/api";

export default function AthleteWorkoutPage() {
  const params = useParams<{ id: string }>();
  const planId = Number(params.id);
  const { athleteId } = useAthlete();
  const [workout, setWorkout] = useState<PlannedWorkout | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setWorkout(await getAthleteWorkout(athleteId, planId));
  }, [athleteId, planId]);

  useEffect(() => {
    if (!Number.isFinite(planId)) return;
    const timer = window.setTimeout(() => {
      void load().catch((loadError: unknown) => setError(errorMessage(loadError)));
    }, 0);
    return () => window.clearTimeout(timer);
  }, [load, planId]);

  async function onMatch(value: string) {
    setError(null);
    try {
      await matchPortalWorkout(athleteId, planId, value ? Number(value) : null);
      await load();
    } catch (matchError) {
      setError(errorMessage(matchError));
    }
  }

  if (!workout && !error) return <p className="text-sm text-muted-foreground">Loading the workout…</p>;
  if (!workout) return <p className="text-sm text-destructive">{error}</p>;
  const comparison = workout.comparison;

  return (
    <div className="space-y-4">
      <div>
        <p className="text-xs text-muted-foreground"><Link href="/athlete/calendar" className="hover:underline">Calendar</Link></p>
        <h1 className="font-heading text-4xl tracking-tight">{workout.title}</h1>
        <p className="mt-2 text-sm text-muted-foreground">{workout.scheduled_date} · {workout.status.replaceAll("_", " ")}</p>
      </div>
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      <Card>
        <CardHeader>
          <CardTitle>From the plan</CardTitle>
          <CardDescription>The workout as it was written in the uploaded spreadsheet.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <p className="whitespace-pre-wrap">{planText(workout)}</p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Planned vs actual</CardTitle>
          <CardDescription>{workout.summary || "Match a run to compare it with this prescription."}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          {comparison ? (
            <p>
              {milesLabel(numberOrNull(comparison.actual_distance_miles))} ran
              {" · "}
              {paceLabel(numberOrNull(comparison.actual_pace_seconds_per_mile))}
              {" · "}
              {String(comparison.execution || "").replaceAll("_", " ")}
            </p>
          ) : null}
          {workout.match ? (
            <Link href={`/athlete/activities/${workout.match.garmin_activity_id}`} className="underline">
              {workout.match.name || "Matched run"}
            </Link>
          ) : (
            <p className="text-muted-foreground">No run is matched.</p>
          )}
          <label className="block">
            Match a run from this day
            <select
              className="mt-1 h-9 w-full rounded-lg border border-input bg-card px-3"
              value={workout.match?.garmin_activity_id ?? ""}
              onChange={(event) => void onMatch(event.target.value)}
            >
              <option value="">No match</option>
              {workout.candidates.map((candidate) => (
                <option key={candidate.garmin_activity_id} value={candidate.garmin_activity_id}>
                  {candidate.name || "Run"} · {milesLabel(candidate.distance_miles)}
                </option>
              ))}
            </select>
          </label>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>How it felt</CardTitle>
        </CardHeader>
        <CardContent>
          <FeedbackForm
            athleteId={athleteId}
            scheduledWorkoutId={workout.id}
            garminActivityId={workout.match?.garmin_activity_id}
            initial={workout.feedback ?? null}
            onSaved={() => void load()}
          />
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Notes for your coach</CardTitle>
        </CardHeader>
        <CardContent>
          <CommentList
            athleteId={athleteId}
            author="athlete"
            comments={workout.comments ?? []}
            scheduledWorkoutId={workout.id}
            garminActivityId={workout.match?.garmin_activity_id}
            onPosted={() => void load()}
          />
        </CardContent>
      </Card>
    </div>
  );
}

function numberOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
