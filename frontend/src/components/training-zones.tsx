"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { errorMessage, getAthleteById, getAthleteOverview, updateAthleteById } from "@/lib/api";
import { formatRaceDistance, formatResultClock, paceEstimateFromRecords, type PaceEstimate } from "@/lib/vdot";

const fieldClass = "mt-1 w-full rounded-lg border border-input bg-card px-3 py-2 text-sm";
const TRAINING_PACES = [
  { name: "easy", label: "Easy" },
  { name: "marathon", label: "Marathon" },
  { name: "lt2", label: "Threshold" },
  { name: "interval", label: "Interval" },
  { name: "repetition", label: "Repetition" },
];

function paceText(seconds: number | null | undefined) {
  if (seconds == null || !Number.isFinite(seconds)) return "";
  const rounded = Math.round(seconds);
  return `${Math.floor(rounded / 60)}:${String(rounded % 60).padStart(2, "0")}`;
}

function paceSeconds(value: string) {
  const text = value.trim().toLowerCase().replace("/mi", "").replace("per mile", "").trim();
  if (!text) return null;
  const clock = /^(\d+):(\d{1,2})$/.exec(text);
  if (clock) {
    const seconds = Number(clock[1]) * 60 + Number(clock[2]);
    return Number(clock[2]) > 59 || seconds <= 0 ? Number.NaN : seconds;
  }
  if (/^\d+(\.\d+)?$/.test(text)) {
    const seconds = Number(text);
    return seconds > 0 ? seconds : Number.NaN;
  }
  return Number.NaN;
}

export function TrainingZones({ athleteId }: { athleteId: number }) {
  const [estimate, setEstimate] = useState<PaceEstimate | null>(null);
  const [maxHeart, setMaxHeart] = useState<number | null>(null);
  const [ready, setReady] = useState(false);
  const [values, setValues] = useState<Record<string, string>>({});
  const [heart, setHeart] = useState<Record<string, number | null>>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const load = useCallback(async () => {
    const [overview, athlete] = await Promise.all([getAthleteOverview(athleteId), getAthleteById(athleteId)]);
    setEstimate(paceEstimateFromRecords(overview.races ?? [], overview.running_stats?.best_efforts ?? []));
    setMaxHeart(overview.athlete?.max_heart_rate_bpm ?? athlete.max_heart_rate_bpm ?? null);
    const next: Record<string, string> = {};
    const rates: Record<string, number | null> = {};
    for (const field of TRAINING_PACES) {
      const row = athlete.thresholds?.find((item) => item.name === field.name);
      next[field.name] = paceText(row?.pace_seconds_per_mile);
      rates[field.name] = row?.heart_rate_bpm ?? null;
    }
    setValues(next);
    setHeart(rates);
    setReady(true);
  }, [athleteId]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void load().catch((loadError: unknown) => {
        setError(errorMessage(loadError));
        setReady(true);
      });
    }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  async function onSave(event: FormEvent) {
    event.preventDefault();
    const thresholds = [];
    for (const field of TRAINING_PACES) {
      const seconds = paceSeconds(values[field.name] ?? "");
      if (Number.isNaN(seconds)) {
        setSaved(false);
        setError(`${field.label} needs a pace like 7:30.`);
        return;
      }
      thresholds.push({
        name: field.name,
        pace_seconds_per_mile: seconds,
        heart_rate_bpm: heart[field.name] ?? null,
      });
    }
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const athlete = await updateAthleteById(athleteId, { thresholds });
      const next: Record<string, string> = {};
      const rates: Record<string, number | null> = {};
      for (const field of TRAINING_PACES) {
        const row = athlete.thresholds?.find((item) => item.name === field.name);
        next[field.name] = paceText(row?.pace_seconds_per_mile);
        rates[field.name] = row?.heart_rate_bpm ?? null;
      }
      setValues(next);
      setHeart(rates);
      setSaved(true);
    } catch (saveError: unknown) {
      setError(errorMessage(saveError));
    } finally {
      setSaving(false);
    }
  }

  if (estimate) {
    return (
      <Card className="max-w-xl">
        <CardHeader>
          <div className="flex items-center justify-between gap-3">
            <CardTitle className="text-xs tracking-[0.14em] uppercase">Training zones</CardTitle>
            <p className="text-sm text-muted-foreground">Race PR estimate</p>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {estimate.zones.map((zone) => (
            <div key={zone.name} className="border-b border-border pb-4 last:border-b-0 last:pb-0">
              <div className="flex items-center justify-between gap-3">
                <p className="font-medium">{zone.name}</p>
                <span className="inline-flex rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-xs text-amber-950">Estimate</span>
              </div>
              <p className="mt-1 text-2xl font-semibold tracking-tight">{zone.range} <span className="text-base font-medium text-muted-foreground">/mi</span></p>
            </div>
          ))}
          <div className="space-y-2 text-sm text-muted-foreground">
            <p>Daniels VDOT {estimate.vdot.toFixed(1)} from {formatRaceDistance(estimate.meters)} in {formatResultClock(estimate.seconds)}</p>
            <p>
              {estimate.kind === "race"
                ? "Estimated from a race result — provisional until a supervised lactate test."
                : "Estimated from a stored best effort — provisional until a supervised lactate test."}
            </p>
            {maxHeart == null ? <p>Heart-rate guidance stays hidden until a max heart rate is saved. It is never guessed.</p> : null}
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="max-w-xl">
      <CardHeader>
        <CardTitle>Training zones</CardTitle>
        <CardDescription>{ready ? "Add a race result to estimate these from a recent PR. Until then, save the paces directly." : "Loading paces…"}</CardDescription>
      </CardHeader>
      <CardContent>
        {ready ? (
          <form onSubmit={(event) => void onSave(event)} className="grid gap-3">
            {TRAINING_PACES.map((field) => (
              <label key={field.name} className="text-sm">
                {field.label}
                <input
                  value={values[field.name] ?? ""}
                  onChange={(event) => {
                    setSaved(false);
                    setValues((current) => ({ ...current, [field.name]: event.target.value }));
                  }}
                  placeholder="7:30"
                  inputMode="decimal"
                  className={fieldClass}
                />
              </label>
            ))}
            <div className="flex items-center gap-3">
              <Button type="submit" disabled={saving}>{saving ? "Saving…" : "Save paces"}</Button>
              {saved ? <p className="text-sm text-muted-foreground">Saved.</p> : null}
            </div>
            {error ? <p className="text-sm text-destructive">{error}</p> : null}
          </form>
        ) : null}
      </CardContent>
    </Card>
  );
}
