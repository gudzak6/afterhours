"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { MessageThread } from "@/components/message-thread";
import { TrainingPlan } from "@/components/training-plan";
import { AthleteRaces } from "@/components/athlete-races";
import { AthleteStats } from "@/components/athlete-stats";
import { MileageHistory } from "@/components/mileage-history";
import { AthleteName } from "@/components/athlete-name";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  deleteAthlete,
  errorMessage,
  getActivities,
  getAthleteOverview,
  type Activity,
  type Athlete,
  type AthleteGoals,
  type RaceEntry,
  type MileageChart,
  type RunningStats,
} from "@/lib/api";
import { formatMiles, formatWhen } from "@/lib/format";

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "activities", label: "Activities" },
  { id: "plan", label: "Training Plan" },
];

export default function AthletePage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const search = useSearchParams();
  const athleteId = Number(params.id);
  const [removing, setRemoving] = useState(false);
  const section = search.get("section") || "overview";
  const [athlete, setAthlete] = useState<Athlete | null>(null);
  const [mileage, setMileage] = useState<MileageChart | null>(null);
  const [runningStats, setRunningStats] = useState<RunningStats | null>(null);
  const [recent, setRecent] = useState<Array<{ garmin_activity_id: number; name: string | null; distance_meters: number | null; start_time_local: string | null; workout_type: string | null }>>([]);
  const [activities, setActivities] = useState<Activity[]>([]);
  const [goal, setGoal] = useState<AthleteGoals | null>(null);
  const [races, setRaces] = useState<RaceEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [activitiesReady, setActivitiesReady] = useState(false);

  const load = useCallback(async () => {
    if (!Number.isFinite(athleteId)) return;
    setReady(false);
    setActivitiesReady(false);
    try {
      const overview = await getAthleteOverview(athleteId);
      setAthlete(overview.athlete);
      setMileage(overview.mileage_chart);
      setRunningStats(overview.running_stats);
      setRecent(overview.recent_workouts);
      setGoal(
        overview.goal
          ? { ...overview.goal, races: overview.races ?? [] }
          : null,
      );
      setRaces(overview.races ?? []);
      setError(null);
      setReady(true);
    } catch (loadError) {
      setError(errorMessage(loadError));
      return;
    }
    try {
      const activityList = await getActivities(200);
      setActivities(activityList.activities.filter((activity) => activity.athlete_id === athleteId));
    } catch (loadError) {
      setError(errorMessage(loadError));
    } finally {
      setActivitiesReady(true);
    }
  }, [athleteId]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  async function onRemove() {
    const name = athlete?.display_name || "this athlete";
    const confirmed = window.confirm(`Remove ${name}? Their activities, training plan, and reports are deleted with them.`);
    if (!confirmed) {
      return;
    }
    setRemoving(true);
    setError(null);
    try {
      await deleteAthlete(athleteId);
      if (window.sessionStorage.getItem("trainingcoach-athlete") === String(athleteId)) {
        window.sessionStorage.removeItem("trainingcoach-athlete");
      }
      router.push("/");
    } catch (removeError) {
      setError(errorMessage(removeError));
      setRemoving(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <p className="text-xs text-muted-foreground">
            <Link href="/athletes" className="hover:underline">All athletes</Link>
          </p>
          <h1 className="font-heading text-2xl tracking-tight sm:text-3xl">{athlete ? <AthleteName name={athlete.display_name} /> : "Loading…"}</h1>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="destructive" onClick={() => void onRemove()} disabled={removing || !athlete}>
            {removing ? "Removing…" : "Remove athlete"}
          </Button>
        </div>
      </div>
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      <nav className="flex flex-wrap gap-1">
        {TABS.map((tab) => (
          <Link
            key={tab.id}
            href={`/athletes/${athleteId}?section=${tab.id}`}
            className={`rounded-lg px-3 py-1.5 text-sm ${section === tab.id ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted"}`}
          >
            {tab.label}
          </Link>
        ))}
      </nav>

      {!ready && !error ? <p className="text-sm text-muted-foreground">Loading this athlete…</p> : null}

      {ready && section === "overview" ? (
        <div className="grid items-start gap-4 min-[960px]:grid-cols-[minmax(0,1fr)_22rem]">
          <div className="space-y-4">
            <AthleteRaces athleteId={athleteId} goal={goal} races={races} />
            {mileage ? (
              <Card>
                <CardHeader>
                  <CardTitle>Mileage</CardTitle>
                  <CardDescription>Every stored week, with this week filled in. Switch to the runs logged this week.</CardDescription>
                </CardHeader>
                <CardContent>
                  <MileageHistory chart={mileage} />
                </CardContent>
              </Card>
            ) : null}
            <Card>
              <CardHeader>
                <CardTitle>Recent workouts</CardTitle>
              </CardHeader>
              <CardContent>
                {recent.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No workouts stored for this athlete.</p>
                ) : (
                  <ul className="space-y-2 text-sm">
                    {recent.map((workout) => (
                      <li key={workout.garmin_activity_id}>
                        <Link href={`/activities/${workout.garmin_activity_id}`} className="font-medium hover:underline">
                          {workout.name || "Activity"}
                        </Link>
                        <span className="text-muted-foreground">
                          {" "}
                          · {formatWhen(workout.start_time_local, null)} · {formatMiles(workout.distance_meters == null ? null : workout.distance_meters / 1609.344, workout.distance_meters != null)}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          </div>
          <aside className="space-y-4 min-[960px]:sticky min-[960px]:top-6 min-[960px]:max-h-[calc(100vh-3rem)] min-[960px]:overflow-y-auto">
            {runningStats ? (
              <Card>
                <CardHeader>
                  <CardTitle>Stats</CardTitle>
                  <CardDescription>Running only. The last four weeks are the four weeks before this one.</CardDescription>
                </CardHeader>
                <CardContent>
                  <AthleteStats athleteId={athleteId} stats={runningStats} onChange={setRunningStats} />
                </CardContent>
              </Card>
            ) : null}
            <Card>
              <CardHeader>
                <CardTitle>Messages</CardTitle>
                <CardDescription>What this athlete sent, and your replies.</CardDescription>
              </CardHeader>
              <CardContent>
                <MessageThread athleteId={athleteId} author="coach" />
              </CardContent>
            </Card>
          </aside>
        </div>
      ) : null}

      {ready && section === "activities" ? (
        <Card>
          <CardHeader>
            <CardTitle>Activities</CardTitle>
            <CardDescription>Open an activity for the stored analysis.</CardDescription>
          </CardHeader>
          <CardContent>
            {!activitiesReady ? (
              <p className="text-sm text-muted-foreground">Loading activities…</p>
            ) : activities.length === 0 ? (
              <p className="text-sm text-muted-foreground">No activities for this athlete.</p>
            ) : (
              <ul className="divide-y divide-border text-sm">
                {activities.map((activity) => (
                  <li key={activity.id} className="flex flex-col gap-1 py-3 sm:flex-row sm:items-center sm:justify-between">
                    <Link href={`/activities/${activity.garmin_activity_id}`} className="font-medium hover:underline">
                      {activity.name || "Activity"}
                    </Link>
                    <span className="text-muted-foreground">
                      {formatMiles(activity.distance_miles, activity.distance_miles != null)} · {activity.analysis_status.replaceAll("_", " ")}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      ) : null}

      {ready && section === "plan" ? <TrainingPlan athleteId={athleteId} /> : null}
    </div>
  );
}
