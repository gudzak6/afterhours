"use client";

import { Flag, Star } from "lucide-react";
import { FormEvent, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { errorMessage, getAthleteGoals, saveAthleteGoal, saveRace, type AthleteGoals, type RaceEntry } from "@/lib/api";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function parseDay(iso: string) {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(year, (month || 1) - 1, day || 1);
}

function dateLabel(iso: string) {
  const date = parseDay(iso);
  return `${MONTHS[date.getMonth()]} ${date.getDate()}, ${date.getFullYear()}`;
}

function distanceLabel(race: RaceEntry) {
  if (race.distance_meters != null && race.distance_meters > 0) {
    const miles = race.distance_meters / 1609.344;
    return `${miles.toFixed(1)} mi`;
  }
  return race.distance_label;
}

function isGoal(race: RaceEntry, goals: AthleteGoals | null) {
  if (!goals?.primary_race_goal) return false;
  return race.name.trim().toLowerCase() === goals.primary_race_goal.trim().toLowerCase();
}

export function AthleteRaces({
  athleteId,
  goal,
  races,
}: {
  athleteId: number;
  goal: AthleteGoals | null;
  races: RaceEntry[];
}) {
  const [saved, setSaved] = useState<AthleteGoals | null>(null);
  const goals = saved ?? { primary_race_goal: goal?.primary_race_goal ?? null, goal_race_date: goal?.goal_race_date ?? null, target_time: goal?.target_time ?? null, races };
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [raceDate, setRaceDate] = useState("");
  const [distance, setDistance] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const trainingFor = goals.races.find((race) => isGoal(race, goals)) ?? null;

  async function refresh() {
    setSaved(await getAthleteGoals(athleteId));
  }

  async function choose(race: RaceEntry) {
    setBusy(true);
    setError(null);
    try {
      setSaved(await saveAthleteGoal(athleteId, {
        primary_race_goal: race.name,
        goal_race_date: race.race_date,
        target_time: race.goal_time || goals.target_time || null,
      }));
    } catch (saveError) {
      setError(errorMessage(saveError));
    } finally {
      setBusy(false);
    }
  }

  async function onAdd(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const created = await saveRace(athleteId, {
        name: name.trim(),
        race_date: raceDate || null,
        distance_label: distance.trim() || null,
      });
      if (goals.races.length === 0) {
        await saveAthleteGoal(athleteId, {
          primary_race_goal: created.name,
          goal_race_date: created.race_date,
          target_time: goals.target_time || null,
        });
      }
      setName("");
      setRaceDate("");
      setDistance("");
      setAdding(false);
      await refresh();
    } catch (saveError) {
      setError(errorMessage(saveError));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-3">
        <div>
          <CardTitle className="flex items-center gap-2">
            <Flag className="size-4" />
            Races
          </CardTitle>
          <p className="mt-1 text-sm text-muted-foreground">
            {trainingFor ? `Training for ${trainingFor.name}.` : "Choose the race this athlete is training for."}
          </p>
        </div>
        {goals.races.length > 0 ? (
          <Button type="button" variant="outline" size="sm" onClick={() => setAdding((open) => !open)}>
            Add
          </Button>
        ) : null}
      </CardHeader>
      <CardContent className="space-y-3">
        {goals.races.length === 0 && !adding ? (
          <button type="button" onClick={() => setAdding(true)} className="inline-flex min-h-11 items-center text-sm font-medium underline">
            Add a race
          </button>
        ) : null}
        <ul className="space-y-2">
          {goals.races.map((race) => {
            const goal = isGoal(race, goals);
            const when = race.race_date ? parseDay(race.race_date) : null;
            return (
              <li key={race.id} className="rounded-lg border border-border px-3 py-2">
                <div className="flex items-start gap-3">
                  <div className="flex size-11 shrink-0 flex-col items-center justify-center rounded-md border border-border text-center">
                    <span className="text-[9px] tracking-wide uppercase">{when ? MONTHS[when.getMonth()] : "—"}</span>
                    <span className="text-sm font-semibold leading-none">{when ? when.getDate() : "?"}</span>
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-sm text-muted-foreground">{race.race_date ? dateLabel(race.race_date) : "Date not set"}</p>
                      <p className="shrink-0 text-sm text-muted-foreground">{distanceLabel(race) || ""}</p>
                    </div>
                    <div className="mt-1 flex items-center gap-2">
                      <p className="font-semibold">{race.name}</p>
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => void choose(race)}
                        aria-pressed={goal}
                        aria-label={goal ? `${race.name} is the race they are training for` : `Train for ${race.name}`}
                        className={`inline-flex size-11 shrink-0 items-center justify-center ${goal ? "text-foreground" : "text-muted-foreground hover:text-foreground"}`}
                      >
                        <Star className={`size-4 ${goal ? "fill-current" : ""}`} />
                      </button>
                    </div>
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
        {adding ? (
          <form onSubmit={(event) => void onAdd(event)} className="grid gap-2 sm:grid-cols-3">
            <label className="text-sm sm:col-span-3">
              Race
              <input value={name} onChange={(event) => setName(event.target.value)} className="mt-1 h-9 w-full rounded-lg border border-input bg-card px-3" required />
            </label>
            <label className="text-sm">
              Date
              <input type="date" value={raceDate} onChange={(event) => setRaceDate(event.target.value)} className="mt-1 h-9 w-full rounded-lg border border-input bg-card px-3" />
            </label>
            <label className="text-sm sm:col-span-2">
              Distance
              <input value={distance} onChange={(event) => setDistance(event.target.value)} placeholder="Marathon, mile, 5K" className="mt-1 h-9 w-full rounded-lg border border-input bg-card px-3" />
            </label>
            <div className="sm:col-span-3">
              <Button type="submit" disabled={busy || name.trim().length === 0}>{busy ? "Saving…" : "Save race"}</Button>
            </div>
          </form>
        ) : null}
        {error ? <p className="text-sm text-destructive">{error}</p> : null}
      </CardContent>
    </Card>
  );
}
