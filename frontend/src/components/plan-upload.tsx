"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { AthleteName, isTestAthlete } from "@/components/athlete-name";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { errorMessage, getDashboard, importTrainingProgram, type ProgramImportResult, type RosterAthlete } from "@/lib/api";

export function PlanUpload() {
  const [athletes, setAthletes] = useState<RosterAthlete[]>([]);
  const [athleteId, setAthleteId] = useState<number | null>(null);
  const [startDate, setStartDate] = useState(nextMonday);
  const [file, setFile] = useState<File | null>(null);
  const [request, setRequest] = useState("");
  const [fileKey, setFileKey] = useState(0);
  const fileInput = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState<"file" | "generate" | "saved" | null>(null);
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
    setBusy("file");
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
      setBusy(null);
    }
  }

  async function onGenerate() {
    const ask = request.trim();
    if (!athleteId || !ask || busy) return;
    setBusy("generate");
    setError(null);
    setResult(null);
    try {
      const imported = await importTrainingProgram(athleteId, { request: ask, start_date: startDate });
      setResult(imported);
      setRequest("");
    } catch (generateError) {
      setError(errorMessage(generateError));
    } finally {
      setBusy(null);
    }
  }

  async function onApplySaved() {
    if (!athleteId || busy) return;
    setBusy("saved");
    setError(null);
    setResult(null);
    try {
      const response = await fetch(SAVED_PROGRAM.href);
      if (!response.ok) throw new Error("The Flight School plan could not be loaded.");
      const content_base64 = bytesToBase64(new Uint8Array(await response.arrayBuffer()));
      const imported = await importTrainingProgram(athleteId, {
        filename: SAVED_PROGRAM.filename,
        content_base64,
        start_date: startDate,
      });
      setResult(imported);
    } catch (applyError) {
      setError(errorMessage(applyError));
    } finally {
      setBusy(null);
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
                disabled={busy !== null || athletes.length === 0}
              >
                {athletes.length === 0 ? <option value="">No athletes</option> : null}
                {athletes.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.display_name}{isTestAthlete(item.display_name) ? " (test data)" : ""}
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
                disabled={busy !== null}
              />
            </label>
          </div>
          <div className="block text-sm">
            <span className="text-muted-foreground">Program file</span>
            <div className="mt-1 flex flex-wrap items-center gap-3">
              <input
                ref={fileInput}
                key={fileKey}
                type="file"
                accept=".csv,.xlsx,.txt,.md,.text"
                className="sr-only"
                disabled={busy !== null}
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              />
              <Button type="button" variant="outline" disabled={busy !== null} onClick={() => fileInput.current?.click()}>
                Choose file
              </Button>
              <span className="text-muted-foreground">{file ? file.name : "No file chosen"}</span>
            </div>
          </div>
          <Button type="submit" disabled={busy !== null || !athleteId || !file}>
            {busy === "file" ? "Reading the program…" : "Update plan"}
          </Button>
          <div className="space-y-2 border-t border-border pt-3">
            <p className="text-sm font-medium">{SAVED_PROGRAM.name}</p>
            <p className="text-sm text-muted-foreground">{SAVED_PROGRAM.detail}</p>
            <Button type="button" variant="outline" className="min-h-11" disabled={busy !== null || !athleteId} onClick={() => void onApplySaved()}>
              {busy === "saved" ? "Applying the plan…" : `Apply to ${athlete?.display_name ?? "athlete"}`}
            </Button>
          </div>
          <div className="space-y-2 border-t border-border pt-3">
            <label className="block text-sm">
              <span className="text-muted-foreground">Or ask for a plan</span>
              <textarea
                className="mt-1 min-h-20 w-full rounded-lg border border-input bg-card px-3 py-2"
                value={request}
                placeholder="I want a plan for training for the mile"
                disabled={busy !== null}
                onChange={(event) => setRequest(event.target.value)}
              />
            </label>
            <Button type="button" variant="outline" disabled={busy !== null || !athleteId || request.trim().length < 8} onClick={() => void onGenerate()}>
              {busy === "generate" ? "Writing the plan…" : "Use AI to generate a plan"}
            </Button>
          </div>
        </form>
        {error ? <p className="mt-3 text-sm text-destructive">{error}</p> : null}
        {result && athlete ? (
          <div className="mt-4 space-y-2 text-sm">
            <p>
              {result.created} {result.created === 1 ? "workout was" : "workouts were"} written onto <AthleteName name={athlete.display_name} />’s plan for {formatDay(result.start)} through {formatDay(result.end)}. {result.replaced} planned {result.replaced === 1 ? "workout" : "workouts"} in those dates {result.replaced === 1 ? "was" : "were"} replaced.
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

const SAVED_PROGRAM = {
  name: "Flight School NYCM 50–60 mpw",
  href: "/plans/flight-school-nycm-50-60.xlsx",
  filename: "Flight School_NYCM_50-60mpw.xlsx",
  detail: "The weekly mileage and workouts through the New York City Marathon. Apply uses the athlete and start date above, and the weeks shift so the first workout lands on that day.",
};

function bytesToBase64(bytes: Uint8Array) {
  let binary = "";
  const size = 0x8000;
  for (let index = 0; index < bytes.length; index += size) {
    binary += String.fromCharCode(...bytes.subarray(index, index + size));
  }
  return btoa(binary);
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
