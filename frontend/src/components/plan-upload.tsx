"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { errorMessage, getDashboard, importTrainingProgram, type ProgramImportResult, type RosterAthlete } from "@/lib/api";

export function PlanUpload() {
  const [athletes, setAthletes] = useState<RosterAthlete[]>([]);
  const [athleteId, setAthleteId] = useState<number | null>(null);
  const [startDate, setStartDate] = useState(nextMonday);
  const [file, setFile] = useState<File | null>(null);
  const [fileKey, setFileKey] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ProgramImportResult | null>(null);

  useEffect(() => {
    let active = true;
    getDashboard()
      .then((dashboard) => {
        if (!active) return;
        setAthletes(dashboard.athletes);
        setAthleteId((current) => current ?? dashboard.athletes[0]?.id ?? null);
      })
      .catch((loadError: unknown) => {
        if (active) setError(errorMessage(loadError));
      });
    return () => {
      active = false;
    };
  }, []);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!athleteId || !file || busy) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const body = await readProgramFile(file);
      const imported = await importTrainingProgram(athleteId, { ...body, start_date: startDate });
      setResult(imported);
      setFile(null);
      setFileKey((value) => value + 1);
    } catch (importError) {
      setError(errorMessage(importError));
    } finally {
      setBusy(false);
    }
  }

  const athlete = athletes.find((item) => item.id === athleteId);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Upload a plan</CardTitle>
        <CardDescription>
          Choose an athlete and the day the plan should begin. Dates written in the file are ignored, and the weeks move so the first workout lands on that day. A written program is read by the agent. Workouts already planned between the new first and last date are replaced.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form className="space-y-3" onSubmit={onSubmit}>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block text-sm">
              <span className="text-muted-foreground">Athlete</span>
              <select
                className="mt-1 h-9 w-full rounded-lg border border-input bg-card px-3"
                value={athleteId ?? ""}
                onChange={(event) => setAthleteId(Number(event.target.value))}
                disabled={busy || athletes.length === 0}
              >
                {athletes.length === 0 ? <option value="">No athletes</option> : null}
                {athletes.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.display_name}
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-sm">
              <span className="text-muted-foreground">Plan start date</span>
              <input
                type="date"
                className="mt-1 h-9 w-full rounded-lg border border-input bg-card px-3"
                value={startDate}
                onChange={(event) => setStartDate(event.target.value)}
                disabled={busy}
              />
            </label>
          </div>
          <label className="block text-sm">
            <span className="text-muted-foreground">Program file</span>
            <input
              key={fileKey}
              type="file"
              accept=".csv,.xlsx,.txt,.md,.text"
              className="mt-1 block w-full text-sm"
              disabled={busy}
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
          </label>
          <Button type="submit" disabled={busy || !athleteId || !file}>
            {busy ? "Reading the program…" : "Update plan"}
          </Button>
        </form>
        {error ? <p className="mt-3 text-sm text-destructive">{error}</p> : null}
        {result && athlete ? (
          <div className="mt-4 space-y-2 text-sm">
            <p>
              {result.created} {result.created === 1 ? "workout was" : "workouts were"} written onto {athlete.display_name}’s plan for {formatDay(result.start)} through {formatDay(result.end)}. {result.replaced} planned {result.replaced === 1 ? "workout" : "workouts"} in those dates {result.replaced === 1 ? "was" : "were"} replaced.
            </p>
            <ul className="space-y-1 text-muted-foreground">
              {result.workouts.map((workout) => (
                <li key={`${workout.scheduled_date}-${workout.title}`}>
                  {formatDay(workout.scheduled_date)} · {workout.title}
                </li>
              ))}
            </ul>
            {result.notes.length > 0 ? <p className="text-muted-foreground">{result.notes.join(" ")}</p> : null}
            <Link href={`/athletes/${athlete.id}?section=plan`} className="inline-block text-primary">
              Open the plan
            </Link>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function nextMonday() {
  const today = new Date();
  const delta = (8 - today.getDay()) % 7;
  const monday = new Date(today.getFullYear(), today.getMonth(), today.getDate() + delta);
  const month = String(monday.getMonth() + 1).padStart(2, "0");
  const day = String(monday.getDate()).padStart(2, "0");
  return `${monday.getFullYear()}-${month}-${day}`;
}

function formatDay(iso: string) {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(year, month - 1, day).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function readProgramFile(file: File) {
  return new Promise<{ filename: string; text?: string; content_base64?: string }>((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error);
    const name = file.name.toLowerCase();
    if (name.endsWith(".csv") || name.endsWith(".txt") || name.endsWith(".md") || name.endsWith(".text")) {
      reader.onload = () => resolve({ filename: file.name, text: String(reader.result ?? "") });
      reader.readAsText(file);
      return;
    }
    reader.onload = () => {
      const value = String(reader.result ?? "");
      resolve({ filename: file.name, content_base64: value.split(",")[1] || "" });
    };
    reader.readAsDataURL(file);
  });
}
