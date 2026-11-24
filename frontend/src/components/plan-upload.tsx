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
  const [source, setSource] = useState<PlanSource | null>(null);
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
        <CardTitle>Choose a plan</CardTitle>
        <CardDescription>
          Pick one way to write it. A spreadsheet that already has calendar dates keeps those dates, and every workout from the first of those dates onward is replaced. A file that only lists week numbers starts on the date you pick.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form className="space-y-4" onSubmit={onSubmit}>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block text-sm">
              <span className="text-muted-foreground">Athlete</span>
              <select
                className="mt-1 h-11 w-full rounded-lg border border-input bg-card px-3 text-base sm:h-9 sm:text-sm"
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
                className="mt-1 h-11 w-full rounded-lg border border-input bg-card px-3 text-base sm:h-9 sm:text-sm"
                value={startDate}
                onChange={(event) => setStartDate(event.target.value)}
                disabled={busy !== null}
              />
            </label>
          </div>
          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">How should this plan be written?</legend>
            <div className="grid gap-2">
              {PLAN_SOURCES.map((item) => {
                const selected = source === item.id;
                return (
                  <label
                    key={item.id}
                    className={`flex cursor-pointer items-start gap-3 rounded-lg border px-3 py-3 ${selected ? "border-primary bg-muted" : "border-border bg-card"}`}
                  >
                    <input
                      type="radio"
                      name="plan-source"
                      className="mt-1 size-4"
                      checked={selected}
                      disabled={busy !== null}
                      onChange={() => setSource(item.id)}
                    />
                    <span>
                      <span className="block text-sm font-medium">{item.title}</span>
                      <span className="mt-0.5 block text-sm text-muted-foreground">{item.detail}</span>
                    </span>
                  </label>
                );
              })}
            </div>
          </fieldset>
          {source === "file" ? (
            <div className="space-y-3 rounded-lg border border-border p-3">
              <p className="text-sm font-medium">Choose a file to upload</p>
              <div className="flex flex-wrap items-center gap-3">
                <input
                  ref={fileInput}
                  key={fileKey}
                  type="file"
                  accept=".csv,.xlsx,.txt,.md,.text"
                  className="sr-only"
                  disabled={busy !== null}
                  onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                />
                <Button type="button" variant="outline" className="min-h-11" disabled={busy !== null} onClick={() => fileInput.current?.click()}>
                  Choose file
                </Button>
                <span className="text-sm text-muted-foreground">{file ? file.name : "No file chosen"}</span>
              </div>
              <Button type="submit" className="min-h-11" disabled={busy !== null || !athleteId || !file}>
                {busy === "file" ? "Reading the file…" : `Upload onto ${athlete?.display_name ?? "this athlete"}`}
              </Button>
            </div>
          ) : null}
          {source === "saved" ? (
            <div className="space-y-3 rounded-lg border border-border p-3">
              <p className="text-sm font-medium">{SAVED_PROGRAM.name}</p>
              <p className="text-sm text-muted-foreground">{SAVED_PROGRAM.detail}</p>
              <Button type="button" className="min-h-11" disabled={busy !== null || !athleteId} onClick={() => void onApplySaved()}>
                {busy === "saved" ? "Applying the spreadsheet…" : `Apply this spreadsheet to ${athlete?.display_name ?? "this athlete"}`}
              </Button>
            </div>
          ) : null}
          {source === "ask" ? (
            <div className="space-y-3 rounded-lg border border-border p-3">
              <label className="block text-sm">
                <span className="font-medium">Ask AI</span>
                <textarea
                  className="mt-1 min-h-24 w-full rounded-lg border border-input bg-card px-3 py-2 text-base sm:text-sm"
                  value={request}
                  placeholder="A 16-week plan for the mile, starting from 30 miles a week."
                  disabled={busy !== null}
                  onChange={(event) => setRequest(event.target.value)}
                />
              </label>
              <Button type="button" className="min-h-11" disabled={busy !== null || !athleteId || request.trim().length < 8} onClick={() => void onGenerate()}>
                {busy === "generate" ? "Writing the plan…" : `Ask AI to write ${athlete?.display_name ?? "this athlete"}’s plan`}
              </Button>
            </div>
          ) : null}
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

type PlanSource = "file" | "saved" | "ask";

const PLAN_SOURCES: Array<{ id: PlanSource; title: string; detail: string }> = [
  { id: "file", title: "Choose a file to upload", detail: "A spreadsheet or text file from this computer." },
  { id: "saved", title: "Apply the existing spreadsheet", detail: "The saved Flight School plan for the New York City Marathon." },
  { id: "ask", title: "Ask AI", detail: "Describe the race, and a plan is written for this athlete." },
];

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
