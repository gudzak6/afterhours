"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { useAthlete } from "@/components/athlete-frame";
import { fieldClass, milesLabel } from "@/components/athlete-ui";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { errorMessage, getPortalActivities, logManualActivity, type PortalActivity } from "@/lib/api";

export default function AthleteLogPage() {
  const { athleteId } = useAthlete();
  const router = useRouter();
  const [activities, setActivities] = useState<PortalActivity[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({
    name: "Run",
    start_day: new Date().toISOString().slice(0, 10),
    start_time: "07:00",
    distance_miles: "",
    duration: "",
    heart_rate: "",
    notes: "",
    workout_type: "easy",
  });

  const load = useCallback(async () => {
    const list = await getPortalActivities(athleteId, 20);
    setActivities(list.activities);
  }, [athleteId]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void load().catch((loadError: unknown) => setError(errorMessage(loadError)));
    }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      const logged = await logManualActivity(athleteId, {
        name: form.name,
        start_day: form.start_day,
        start_time: form.start_time,
        distance_miles: form.distance_miles.trim() ? Number(form.distance_miles) : null,
        duration_seconds: parseDuration(form.duration),
        average_heart_rate_bpm: form.heart_rate.trim() ? Number(form.heart_rate) : null,
        notes: form.notes,
        workout_type: form.workout_type,
      });
      router.push(`/athlete/activities/${logged.garmin_activity_id}`);
    } catch (saveError) {
      setError(errorMessage(saveError));
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="font-heading text-4xl tracking-tight">Log a run</h1>
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">Use this when a run was not recorded on Garmin. You can correct it afterward.</p>
      </div>
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      <Card>
        <CardHeader>
          <CardTitle>Manual entry</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={(event) => void onSubmit(event)} className="grid gap-3 sm:grid-cols-2">
            <label className="text-sm">Name<input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} className={fieldClass} /></label>
            <label className="text-sm">Type
              <select value={form.workout_type} onChange={(event) => setForm({ ...form, workout_type: event.target.value })} className={fieldClass}>
                {["easy", "recovery", "long_run", "tempo", "threshold", "intervals", "race", "other"].map((type) => (
                  <option key={type} value={type}>{type.replaceAll("_", " ")}</option>
                ))}
              </select>
            </label>
            <label className="text-sm">Date<input type="date" value={form.start_day} onChange={(event) => setForm({ ...form, start_day: event.target.value })} className={fieldClass} required /></label>
            <label className="text-sm">Start<input type="time" value={form.start_time} onChange={(event) => setForm({ ...form, start_time: event.target.value })} className={fieldClass} required /></label>
            <label className="text-sm">Distance, miles<input value={form.distance_miles} onChange={(event) => setForm({ ...form, distance_miles: event.target.value })} inputMode="decimal" className={fieldClass} /></label>
            <label className="text-sm">Duration<input value={form.duration} onChange={(event) => setForm({ ...form, duration: event.target.value })} placeholder="45:00" className={fieldClass} /></label>
            <label className="text-sm">Heart rate<input value={form.heart_rate} onChange={(event) => setForm({ ...form, heart_rate: event.target.value })} inputMode="numeric" className={fieldClass} /></label>
            <label className="text-sm sm:col-span-2">Notes<textarea value={form.notes} onChange={(event) => setForm({ ...form, notes: event.target.value })} className="mt-1 min-h-20 w-full rounded-lg border border-input bg-card px-3 py-2 text-sm" /></label>
            <div className="sm:col-span-2"><Button type="submit">Save run</Button></div>
          </form>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Recent runs</CardTitle>
          <CardDescription>Open one to match it, edit it, or leave feedback.</CardDescription>
        </CardHeader>
        <CardContent>
          {activities.length === 0 ? <p className="text-sm text-muted-foreground">No runs stored yet.</p> : null}
          <ul className="space-y-2 text-sm">
            {activities.slice(0, 20).map((activity) => (
              <li key={activity.garmin_activity_id}>
                <Link href={`/athlete/activities/${activity.garmin_activity_id}`} className="font-medium hover:underline">{activity.name || "Run"}</Link>
                <span className="text-muted-foreground"> · {milesLabel(activity.distance_miles)} · {activity.start_time_local?.slice(0, 10)}</span>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}

function parseDuration(value: string): number | null {
  const text = value.trim();
  if (!text) return null;
  const parts = text.split(":").map(Number);
  if (parts.some((part) => !Number.isFinite(part))) return null;
  if (parts.length === 1) return parts[0] * 60;
  if (parts.length === 2) return parts[0] * 60 + parts[1];
  return parts[0] * 3600 + parts[1] * 60 + parts[2];
}
