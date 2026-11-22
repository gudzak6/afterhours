"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { AthleteName } from "@/components/athlete-name";
import { CoachingReport } from "@/components/coaching-report";
import { DetectedWorkout, WorkoutBreakdown } from "@/components/workout-breakdown";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { createReport, deleteActivity, errorMessage, getActivity, type ActivityDetail } from "@/lib/api";
import { formatActivityType, formatDuration, formatHeartRate, formatMiles, formatNumber, formatPace, formatWhen, hasField } from "@/lib/format";

export default function ActivityDetailPage() {
  const params = useParams<{ id: string }>();
  const search = useSearchParams();
  const router = useRouter();
  const activityId = Number(params.id);
  const ownerParam = Number(search.get("athlete"));
  const ownerId = Number.isInteger(ownerParam) ? ownerParam : null;
  const [detail, setDetail] = useState<ActivityDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);

  function load() {
    return getActivity(activityId, ownerId).then((row) => {
      setDetail(row);
      setError(null);
    });
  }

  useEffect(() => {
    if (!Number.isInteger(activityId)) {
      return;
    }
    const timer = window.setTimeout(() => {
      void load().catch((loadError: unknown) => setError(errorMessage(loadError)));
    }, 0);
    return () => window.clearTimeout(timer);
  }, [activityId, ownerId]);

  async function onDelete() {
    if (!detail) {
      return;
    }
    const confirmed = window.confirm("Delete this imported activity from the local database?");
    if (!confirmed) {
      return;
    }
    setDeleting(true);
    try {
      await deleteActivity(detail.activity.garmin_activity_id, detail.activity.athlete_id);
      router.push("/activities");
    } catch (deleteError) {
      setError(errorMessage(deleteError));
      setDeleting(false);
    }
  }

  async function onReport() {
    if (!detail) {
      return;
    }
    setBusy("report");
    setError(null);
    try {
      await createReport(detail.activity.garmin_activity_id, detail.activity.athlete_id ?? ownerId);
      await load();
    } catch (reportError) {
      setError(errorMessage(reportError));
    } finally {
      setBusy(null);
    }
  }

  if (error && !detail) {
    return <p className="text-sm text-destructive">{error}</p>;
  }
  if (!detail) {
    return <p className="text-sm text-muted-foreground">Loading activity.</p>;
  }

  const activity = detail.activity;
  const facts = [
    ["Distance", formatMiles(activity.distance_miles, hasField(activity, "distance_meters"))],
    ["Duration", formatDuration(activity.duration_seconds, hasField(activity, "duration_seconds"))],
    ["Pace", formatPace(activity.average_pace_seconds_per_mile, hasField(activity, "average_speed_mps"))],
    ["Average HR", formatHeartRate(activity.average_heart_rate_bpm, hasField(activity, "average_heart_rate_bpm"))],
    ["Max HR", formatHeartRate(activity.max_heart_rate_bpm, hasField(activity, "max_heart_rate_bpm"))],
    ["Cadence", formatNumber(activity.average_cadence_spm, hasField(activity, "average_cadence_spm"), "spm")],
    ["Elevation", formatNumber(activity.elevation_gain_meters, hasField(activity, "elevation_gain_meters"), "m")],
  ];
  const report = detail.report;

  return (
    <div className="space-y-6">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <Link href="/activities" className="text-sm text-muted-foreground hover:underline">
            Activities
          </Link>
          <h1 className="font-heading mt-2 text-2xl tracking-tight sm:text-3xl">{activity.name || "Untitled activity"}</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            {activity.athlete_name ? (
              <>
                <Link href={`/athletes/${activity.athlete_id}`} className="hover:underline">
                  <AthleteName name={activity.athlete_name} />
                </Link>
                {" · "}
              </>
            ) : null}
            {formatWhen(activity.start_time_local, activity.start_time_utc)} · {formatActivityType(activity.activity_type_key)}
          </p>
        </div>
        <Button type="button" variant="destructive" onClick={onDelete} disabled={deleting}>
          {deleting ? "Deleting…" : "Delete activity"}
        </Button>
      </div>
      {error ? <p className="text-sm text-destructive">{error}</p> : null}

      <Card>
        <CardHeader>
          <CardTitle>Summary</CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            {facts.map(([label, value]) => (
              <div key={label}>
                <dt className="text-xs tracking-wide text-muted-foreground uppercase">{label}</dt>
                <dd className="mt-1 text-base">{value}</dd>
              </div>
            ))}
          </dl>
        </CardContent>
      </Card>

      <DetectedWorkout metrics={detail.metrics} />

      <Card>
        <CardHeader>
          <CardTitle>Activity Analysis</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <Button type="button" disabled={busy !== null} onClick={() => void onReport()}>
            {busy === "report" ? "Writing…" : report ? "Write another report" : "Write report"}
          </Button>
          {report ? <CoachingReport report={report} /> : <p className="text-muted-foreground">No report stored.</p>}
          <Link href={`/agent?activity=${activity.garmin_activity_id}${activity.athlete_id == null ? "" : `&athlete=${activity.athlete_id}`}`} className="underline">
            Ask the agent about this activity
          </Link>
        </CardContent>
      </Card>

      <WorkoutBreakdown metrics={detail.metrics} />
    </div>
  );
}
