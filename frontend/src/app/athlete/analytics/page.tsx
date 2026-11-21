"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useAthlete } from "@/components/athlete-frame";
import { fieldClass, milesLabel, paceLabel } from "@/components/athlete-ui";
import { WeeklyChart } from "@/components/weekly-chart";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { errorMessage, getAthleteAnalytics, saveLactate, type AthleteAnalytics } from "@/lib/api";
import { formatDuration } from "@/lib/format";

export default function AthleteAnalyticsPage() {
  const { athleteId } = useAthlete();
  const [report, setReport] = useState<AthleteAnalytics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lactate, setLactate] = useState({ measured_on: "", mmol: "", pace: "", heart_rate: "", notes: "" });

  const load = useCallback(async () => {
    setReport(await getAthleteAnalytics(athleteId));
  }, [athleteId]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void load().catch((loadError: unknown) => setError(errorMessage(loadError)));
    }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  async function onLactate(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await saveLactate(athleteId, {
        measured_on: lactate.measured_on,
        mmol: Number(lactate.mmol),
        pace_seconds_per_mile: paceToSeconds(lactate.pace),
        heart_rate_bpm: lactate.heart_rate.trim() ? Number(lactate.heart_rate) : null,
        notes: lactate.notes || null,
      });
      setLactate({ measured_on: "", mmol: "", pace: "", heart_rate: "", notes: "" });
      await load();
    } catch (saveError) {
      setError(errorMessage(saveError));
    }
  }

  const pacePoints = (report?.pace_trends ?? [])
    .filter((week) => week.pace_seconds_per_mile != null)
    .map((week) => ({ label: week.week_start.slice(5), pace: week.pace_seconds_per_mile }));

  return (
    <div className="space-y-4">
      <div>
        <h1 className="font-heading text-2xl tracking-tight sm:text-3xl">Analytics</h1>
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">Mileage, pace, heart rate, load, records, and lactate from the runs and races stored here.</p>
      </div>
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      {!report && !error ? <p className="text-sm text-muted-foreground">Loading your training…</p> : null}
      {report ? (
        <>
          <Card>
            <CardHeader>
              <CardTitle>Mileage</CardTitle>
              <CardDescription>Weekly volume, then the months that have stored distance.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <WeeklyChart weeks={report.weekly_mileage} />
              {report.monthly_mileage.length > 0 ? (
                <ul className="grid gap-1 text-sm sm:grid-cols-3">
                  {report.monthly_mileage.map((month) => (
                    <li key={month.month}>{month.month}: {milesLabel(month.distance_miles)}</li>
                  ))}
                </ul>
              ) : null}
            </CardContent>
          </Card>
          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Pace</CardTitle>
                <CardDescription>Average pace of runs longer than a kilometer, by week.</CardDescription>
              </CardHeader>
              <CardContent>
                {pacePoints.length === 0 ? <p className="text-sm text-muted-foreground">Pace shows up after a run with distance and time is stored.</p> : (
                  <div className="h-48 min-w-0">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={pacePoints}>
                        <CartesianGrid vertical={false} stroke="oklch(0.88 0.02 80)" />
                        <XAxis dataKey="label" tickLine={false} axisLine={false} />
                        <YAxis tickLine={false} axisLine={false} width={36} reversed />
                        <Tooltip formatter={(value) => [paceLabel(Number(value)), "Pace"]} />
                        <Bar dataKey="pace" fill="oklch(0.5 0.13 42)" radius={[6, 6, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Heart rate</CardTitle>
                <CardDescription>Average heart rate over the last {report.heart_rate.window_days} days, split by the stored workout type.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <p>Easy runs: {bpm(report.heart_rate.easy_average_bpm)} across {report.heart_rate.easy_count}</p>
                <p>Workouts: {bpm(report.heart_rate.workout_average_bpm)} across {report.heart_rate.workout_count}</p>
                {report.threshold ? <p className="text-muted-foreground">Saved LT2: {paceLabel(report.threshold.pace_seconds_per_mile)} · {bpm(report.threshold.heart_rate_bpm)}</p> : null}
              </CardContent>
            </Card>
          </div>
          <Card>
            <CardHeader>
              <CardTitle>Training load</CardTitle>
              <CardDescription>This week’s miles compared with the average of the previous four weeks that have distance.</CardDescription>
            </CardHeader>
            <CardContent className="text-sm">
              <p>{milesLabel(report.training_load.this_week_miles)} this week · {milesLabel(report.training_load.previous_four_week_average)} recent average</p>
              <p className="text-muted-foreground">
                {report.training_load.acute_chronic_ratio == null
                  ? "The ratio appears after this week and an earlier week both have distance."
                  : `Acute to chronic ratio ${report.training_load.acute_chronic_ratio.toFixed(2)}.`}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Planned vs actual</CardTitle>
            </CardHeader>
            <CardContent>
              {report.planned_vs_actual.length === 0 ? <p className="text-sm text-muted-foreground">Comparisons appear after a scheduled workout is matched to a run.</p> : (
                <ul className="space-y-2 text-sm">
                  {report.planned_vs_actual.map((workout) => (
                    <li key={workout.id}>
                      <Link href={`/athlete/workouts/${workout.id}`} className="font-medium hover:underline">{workout.title}</Link>
                      <span className="text-muted-foreground"> · {workout.scheduled_date} · {workout.summary || workout.execution}</span>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Personal records</CardTitle>
              <CardDescription>Best efforts from stored runs, and race results you entered.</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-4 text-sm lg:grid-cols-2">
              <ul className="space-y-1">
                {report.personal_records.best_efforts.filter((effort) => effort.duration_seconds != null).map((effort) => (
                  <li key={effort.label}>{effort.label}: {formatDuration(effort.duration_seconds, true)}</li>
                ))}
                {report.personal_records.best_efforts.every((effort) => effort.duration_seconds == null) ? <li className="text-muted-foreground">No best efforts calculated yet.</li> : null}
              </ul>
              <ul className="space-y-1">
                {report.personal_records.races.map((race) => (
                  <li key={race.id}>{race.name}: {race.result_time}</li>
                ))}
                {report.personal_records.races.length === 0 ? <li className="text-muted-foreground">No race results saved.</li> : null}
              </ul>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Lactate</CardTitle>
              <CardDescription>Enter a measurement to see it beside the saved threshold.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <ul className="space-y-1 text-sm">
                {report.lactate.map((reading) => (
                  <li key={reading.id}>{reading.measured_on}: {reading.mmol} mmol/L{reading.pace_seconds_per_mile ? ` · ${paceLabel(reading.pace_seconds_per_mile)}` : ""}</li>
                ))}
                {report.lactate.length === 0 ? <li className="text-muted-foreground">No lactate readings saved.</li> : null}
              </ul>
              <form onSubmit={(event) => void onLactate(event)} className="grid gap-3 sm:grid-cols-2">
                <label className="text-sm">Date<input type="date" value={lactate.measured_on} onChange={(event) => setLactate({ ...lactate, measured_on: event.target.value })} className={fieldClass} required /></label>
                <label className="text-sm">mmol/L<input value={lactate.mmol} onChange={(event) => setLactate({ ...lactate, mmol: event.target.value })} inputMode="decimal" className={fieldClass} required /></label>
                <label className="text-sm">Pace<input value={lactate.pace} onChange={(event) => setLactate({ ...lactate, pace: event.target.value })} placeholder="6:30" className={fieldClass} /></label>
                <label className="text-sm">Heart rate<input value={lactate.heart_rate} onChange={(event) => setLactate({ ...lactate, heart_rate: event.target.value })} className={fieldClass} /></label>
                <div className="sm:col-span-2"><Button type="submit">Add reading</Button></div>
              </form>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Race estimates</CardTitle>
              <CardDescription>{report.predictions.note}</CardDescription>
            </CardHeader>
            <CardContent className="text-sm">
              {report.predictions.source ? <p className="mb-2">From {report.predictions.source.name}, {report.predictions.source.result_time}.</p> : null}
              <ul className="space-y-1">
                {report.predictions.estimates.map((estimate) => (
                  <li key={estimate.label}>{estimate.label}: {estimate.time}</li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </>
      ) : null}
    </div>
  );
}

function bpm(value: number | null): string {
  if (value == null) return "—";
  return `${Math.round(value)} bpm`;
}

function paceToSeconds(value: string): number | null {
  const text = value.trim();
  if (!text) return null;
  const [minutes, seconds] = text.split(":");
  const minuteNumber = Number(minutes);
  const secondNumber = seconds == null ? 0 : Number(seconds);
  if (!Number.isFinite(minuteNumber) || !Number.isFinite(secondNumber)) return null;
  return minuteNumber * 60 + secondNumber;
}
