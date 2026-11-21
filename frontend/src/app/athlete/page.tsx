"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useAthlete } from "@/components/athlete-frame";
import { ActivityLine, durationLabel, milesLabel, paceLabel, planText } from "@/components/athlete-ui";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { errorMessage, getAthleteHome, syncAthleteGarmin, type PortalActivity, type PortalHome } from "@/lib/api";
import { formatWhen } from "@/lib/format";

export default function AthleteHomePage() {
  const { athleteId, status, reload, openGarmin } = useAthlete();
  const [home, setHome] = useState<PortalHome | null>(null);
  const [runs, setRuns] = useState<PortalActivity[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);

  const load = useCallback(async () => {
    const nextHome = await getAthleteHome(athleteId);
    setHome(nextHome);
    setRuns(nextHome.recent ?? []);
  }, [athleteId]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void load().catch((loadError: unknown) => setError(errorMessage(loadError)));
    }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  async function onSync() {
    setSyncing(true);
    setError(null);
    try {
      await syncAthleteGarmin(athleteId);
      await reload();
      await load();
    } catch (syncError) {
      setError(errorMessage(syncError));
    } finally {
      setSyncing(false);
    }
  }

  const goal = [home?.goal.primary_race_goal, home?.goal.target_time, home?.goal.goal_race_date].filter(Boolean).join(" · ");

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-heading text-4xl tracking-tight">{home ? `Hello, ${home.name}` : "Home"}</h1>
          <p className="mt-2 text-sm text-muted-foreground">Runs imported from Garmin, plus whatever is on the plan.</p>
        </div>
        {status.garmin.key_saved ? (
          <Button type="button" variant="outline" onClick={() => void onSync()} disabled={syncing}>
            {syncing ? "Syncing…" : "Sync Garmin"}
          </Button>
        ) : (
          <Button type="button" variant="outline" onClick={() => {
            window.sessionStorage.removeItem("trainingcoach-garmin-skipped");
            openGarmin();
          }}>
            Connect Garmin
          </Button>
        )}
      </div>
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      {!status.garmin.connected && runs.length === 0 ? (
        <p className="text-sm text-muted-foreground">Connect Garmin to import your runs.</p>
      ) : null}
      {!home && !error ? <p className="text-sm text-muted-foreground">Loading today…</p> : null}
      {home ? (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]">
          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle>Recent runs</CardTitle>
              <CardDescription>
                {runs.length === 0 ? "Nothing imported yet." : `${runs.length} most recent ${runs.length === 1 ? "activity" : "activities"} from Garmin.`}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {runs.length === 0 ? (
                <p className="text-sm text-muted-foreground">Connect Garmin and sync to pull in your activities.</p>
              ) : (
                <ul className="divide-y divide-border">
                  {runs.map((activity) => (
                    <li key={activity.garmin_activity_id}>
                      <Link href={`/athlete/activities/${activity.garmin_activity_id}`} className="flex flex-wrap items-baseline justify-between gap-2 py-3 hover:bg-muted">
                        <span>
                          <span className="font-medium">{activity.name || "Run"}</span>
                          <span className="mt-1 block text-sm text-muted-foreground">{formatWhen(activity.start_time_local, null)}</span>
                        </span>
                        <span className="text-sm text-muted-foreground">
                          {milesLabel(activity.distance_miles)} · {paceLabel(activity.pace_seconds_per_mile)} · {durationLabel(activity.duration_seconds)}
                          {activity.average_heart_rate_bpm == null ? "" : ` · ${Math.round(activity.average_heart_rate_bpm)} bpm`}
                        </span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
          <div className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle>Today</CardTitle>
                <CardDescription>{home.today}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {home.workouts.length === 0 ? <p className="text-sm text-muted-foreground">No workout is scheduled for today.</p> : null}
                {home.workouts.map((workout) => (
                  <Link key={workout.id} href={`/athlete/workouts/${workout.id}`} className="block rounded-lg border border-border p-3 hover:bg-muted">
                    <p className="whitespace-pre-wrap font-medium">{planText(workout)}</p>
                    <p className="mt-1 text-sm text-muted-foreground">{workout.status.replaceAll("_", " ")}</p>
                  </Link>
                ))}
                {home.activities.length > 0 ? (
                  <div className="space-y-2">
                    <p className="text-sm font-medium">Logged today</p>
                    {home.activities.map((activity) => (
                      <ActivityLine key={activity.garmin_activity_id} activity={activity} />
                    ))}
                  </div>
                ) : null}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Coming up</CardTitle>
              </CardHeader>
              <CardContent>
                {home.upcoming.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No later workouts are on the plan.</p>
                ) : (
                  <ul className="space-y-2 text-sm">
                    {home.upcoming.map((workout) => (
                      <li key={workout.id}>
                        <Link href={`/athlete/workouts/${workout.id}`} className="font-medium whitespace-pre-wrap hover:underline">{planText(workout)}</Link>
                        <span className="text-muted-foreground"> · {workout.scheduled_date}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          </div>
          <div className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle>This week</CardTitle>
                <CardDescription>
                  <Link href="/athlete/week" className="underline">Open the plan</Link>
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-1 text-sm">
                {home.week ? (
                  <>
                    <p>{milesLabel(home.week.actual_miles)} completed · {milesLabel(home.week.planned_miles)} planned</p>
                    <p className="text-muted-foreground">
                      {home.week.completed_workouts} of {home.week.planned_workouts} workouts done · {home.week.still_scheduled} still scheduled
                    </p>
                  </>
                ) : (
                  <p className="text-muted-foreground">A weekly plan appears after your coach schedules workouts.</p>
                )}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Goal</CardTitle>
              </CardHeader>
              <CardContent className="text-sm">
                {goal ? <p>{goal}</p> : <p className="text-muted-foreground">Add a race goal when you are ready.</p>}
                <Link href="/athlete/goals" className="mt-2 inline-block underline">Goals and races</Link>
              </CardContent>
            </Card>
          </div>
        </div>
      ) : null}
    </div>
  );
}
