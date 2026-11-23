"use client";

import { Flag, Star } from "lucide-react";
import { FormEvent, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { deleteRace, errorMessage, getAthleteGoals, saveAthleteGoal, saveRace, type AthleteGoals, type RaceEntry } from "@/lib/api";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const fieldClass = "mt-1 h-9 w-full rounded-lg border border-input bg-card px-3";

type RaceForm = {
  name: string;
  raceDate: string;
  distance: string;
  goalTime: string;
};

const emptyForm: RaceForm = { name: "", raceDate: "", distance: "", goalTime: "" };

function parseDay(iso: string) {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(year, (month || 1) - 1, day || 1);
}

function dateLabel(iso: string) {
  const date = parseDay(iso);
  return `${MONTHS[date.getMonth()]} ${date.getDate()}, ${date.getFullYear()}`;
}

function distanceLabel(race: RaceEntry) {
  if (race.distance_label) return race.distance_label;
  if (race.distance_meters != null && race.distance_meters > 0) {
    const miles = race.distance_meters / 1609.344;
    return `${miles.toFixed(1)} mi`;
  }
  return "";
}

function isGoal(race: RaceEntry, goals: AthleteGoals | null) {
  if (!goals?.primary_race_goal) return false;
  return race.name.trim().toLowerCase() === goals.primary_race_goal.trim().toLowerCase();
}

function formFrom(race: RaceEntry): RaceForm {
  return {
    name: race.name,
    raceDate: race.race_date ?? "",
    distance: race.distance_label ?? "",
    goalTime: race.goal_time ?? "",
  };
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
  const [form, setForm] = useState<RaceForm>(emptyForm);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const trainingFor = goals.races.find((race) => isGoal(race, goals)) ?? null;

  async function refresh() {
    setSaved(await getAthleteGoals(athleteId));
  }

  function openAdd() {
    setAdding(true);
    setEditingId(null);
    setForm(emptyForm);
    setError(null);
  }

  function openEdit(race: RaceEntry) {
    setAdding(false);
    setEditingId(race.id);
    setForm(formFrom(race));
    setError(null);
  }

  function closeForm() {
    setAdding(false);
    setEditingId(null);
    setForm(emptyForm);
  }

  async function choose(race: RaceEntry) {
    setBusy(true);
    setError(null);
    try {
      setSaved(await saveAthleteGoal(athleteId, {
        primary_race_goal: race.name,
        goal_race_date: race.race_date,
        target_time: race.goal_time || null,
      }));
    } catch (saveError) {
      setError(errorMessage(saveError));
    } finally {
      setBusy(false);
    }
  }

  async function onSave(event: FormEvent) {
    event.preventDefault();
    const editing = editingId == null ? null : goals.races.find((race) => race.id === editingId) ?? null;
    setBusy(true);
    setError(null);
    try {
      const savedRace = await saveRace(athleteId, {
        name: form.name.trim(),
        race_date: form.raceDate || null,
        distance_label: form.distance.trim() || null,
        goal_time: form.goalTime.trim() || null,
        result_time: editing?.result_time ?? null,
        notes: editing?.notes ?? null,
      }, editing?.id);
      const wasGoal = editing != null && isGoal(editing, goals);
      const firstRace = editing == null && goals.races.length === 0;
      if (wasGoal || firstRace) {
        await saveAthleteGoal(athleteId, {
          primary_race_goal: savedRace.name,
          goal_race_date: savedRace.race_date,
          target_time: savedRace.goal_time,
        });
      }
      closeForm();
      await refresh();
    } catch (saveError) {
      setError(errorMessage(saveError));
    } finally {
      setBusy(false);
    }
  }

  async function remove(race: RaceEntry) {
    setBusy(true);
    setError(null);
    try {
      await deleteRace(athleteId, race.id);
      if (isGoal(race, goals)) {
        await saveAthleteGoal(athleteId, {
          primary_race_goal: null,
          goal_race_date: null,
          target_time: null,
        });
      }
      if (editingId === race.id) closeForm();
      await refresh();
    } catch (removeError) {
      setError(errorMessage(removeError));
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
            {trainingFor
              ? `Training for ${trainingFor.name}${trainingFor.goal_time ? `, goal ${trainingFor.goal_time}` : ""}.`
              : "Choose the race this athlete is training for."}
          </p>
        </div>
        {goals.races.length > 0 ? (
          <Button type="button" variant="outline" size="sm" onClick={() => (adding ? closeForm() : openAdd())}>
            {adding ? "Cancel" : "Add"}
          </Button>
        ) : null}
      </CardHeader>
      <CardContent className="space-y-3">
        {goals.races.length === 0 && !adding ? (
          <button type="button" onClick={openAdd} className="inline-flex min-h-11 items-center text-sm font-medium underline">
            Add a race
          </button>
        ) : null}
        <ul className="space-y-2">
          {goals.races.map((race) => {
            const goalRace = isGoal(race, goals);
            const when = race.race_date ? parseDay(race.race_date) : null;
            if (editingId === race.id) {
              return (
                <li key={race.id}>
                  <RaceFormFields form={form} setForm={setForm} busy={busy} submitLabel="Save race" onSubmit={onSave} onCancel={closeForm} />
                </li>
              );
            }
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
                        aria-pressed={goalRace}
                        aria-label={goalRace ? `${race.name} is the race they are training for` : `Train for ${race.name}`}
                        className={`inline-flex size-8 shrink-0 items-center justify-center ${goalRace ? "text-foreground" : "text-muted-foreground hover:text-foreground"}`}
                      >
                        <Star className={`size-4 ${goalRace ? "fill-current" : ""}`} />
                      </button>
                    </div>
                    {race.goal_time ? <p className="text-sm text-muted-foreground">Goal {race.goal_time}</p> : null}
                    <div className="mt-1 flex gap-3 text-sm">
                      <button type="button" className="text-muted-foreground underline hover:text-foreground" disabled={busy} onClick={() => openEdit(race)}>
                        Edit
                      </button>
                      <button type="button" className="text-muted-foreground underline hover:text-foreground" disabled={busy} onClick={() => void remove(race)}>
                        Delete
                      </button>
                    </div>
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
        {adding ? <RaceFormFields form={form} setForm={setForm} busy={busy} submitLabel="Save race" onSubmit={onSave} onCancel={closeForm} /> : null}
        {error ? <p className="text-sm text-destructive">{error}</p> : null}
      </CardContent>
    </Card>
  );
}

function RaceFormFields({
  form,
  setForm,
  busy,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  form: RaceForm;
  setForm: (update: (form: RaceForm) => RaceForm) => void;
  busy: boolean;
  submitLabel: string;
  onSubmit: (event: FormEvent) => void;
  onCancel: () => void;
}) {
  return (
    <form onSubmit={(event) => void onSubmit(event)} className="grid gap-2 rounded-lg border border-border px-3 py-3 sm:grid-cols-2">
      <label className="text-sm sm:col-span-2">
        Race
        <input value={form.name} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} className={fieldClass} required />
      </label>
      <label className="text-sm">
        Date
        <input type="date" value={form.raceDate} onChange={(event) => setForm((current) => ({ ...current, raceDate: event.target.value }))} className={fieldClass} />
      </label>
      <label className="text-sm">
        Distance
        <input value={form.distance} onChange={(event) => setForm((current) => ({ ...current, distance: event.target.value }))} placeholder="Marathon, mile, 5K" className={fieldClass} />
      </label>
      <label className="text-sm sm:col-span-2">
        Goal time
        <input value={form.goalTime} onChange={(event) => setForm((current) => ({ ...current, goalTime: event.target.value }))} placeholder="2:55:00" className={fieldClass} />
      </label>
      <div className="flex gap-2 sm:col-span-2">
        <Button type="submit" disabled={busy || form.name.trim().length === 0}>{busy ? "Saving…" : submitLabel}</Button>
        <Button type="button" variant="outline" onClick={onCancel} disabled={busy}>Cancel</Button>
      </div>
    </form>
  );
}
