"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { useAthlete } from "@/components/athlete-frame";
import { fieldClass } from "@/components/athlete-ui";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { deleteAccountRace, hasAccount, loadAccountGoals, saveAccountGoal, saveAccountRace } from "@/lib/account";
import { deleteRace, errorMessage, getAthleteGoals, saveAthleteGoal, saveRace, type AthleteGoals, type RaceEntry } from "@/lib/api";

const emptyRace = { name: "", race_date: "", distance_label: "", goal_time: "", result_time: "", notes: "" };

export default function AthleteGoalsPage() {
  const { athleteId } = useAthlete();
  const [goals, setGoals] = useState<AthleteGoals | null>(null);
  const [goal, setGoal] = useState("");
  const [goalDate, setGoalDate] = useState("");
  const [target, setTarget] = useState("");
  const [race, setRace] = useState(emptyRace);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fromAccount, setFromAccount] = useState(false);

  function show(next: AthleteGoals, account: boolean) {
    setFromAccount(account);
    setGoals(next);
    setGoal(next.primary_race_goal ?? "");
    setGoalDate(next.goal_race_date ?? "");
    setTarget(next.target_time ?? "");
  }

  const load = useCallback(async () => {
    const account = await hasAccount();
    if (account) {
      const saved = await loadAccountGoals(athleteId);
      if (saved) {
        show(saved, true);
        return;
      }
      const local = await getAthleteGoals(athleteId);
      if (local.primary_race_goal || local.goal_race_date || local.target_time || local.races.length > 0) {
        await saveAccountGoal(athleteId, {
          primary_race_goal: local.primary_race_goal,
          goal_race_date: local.goal_race_date,
          target_time: local.target_time,
        });
        for (const race of local.races) {
          await saveAccountRace(athleteId, { ...race });
        }
        const copied = await loadAccountGoals(athleteId);
        if (copied) {
          show(copied, true);
          return;
        }
      }
    }
    show(await getAthleteGoals(athleteId), account);
  }, [athleteId]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void load().catch((loadError: unknown) => setError(errorMessage(loadError)));
    }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  async function onGoal(event: FormEvent) {
    event.preventDefault();
    setNotice(null);
    try {
      const body = {
        primary_race_goal: goal.trim() || null,
        goal_race_date: goalDate || null,
        target_time: target.trim() || null,
      };
      const account = await hasAccount();
      if (account) {
        setGoals(await saveAccountGoal(athleteId, body));
        setFromAccount(true);
      }
      try {
        const local = await saveAthleteGoal(athleteId, body);
        if (!account) setGoals(local);
      } catch (localError) {
        if (!account) throw localError;
      }
      setNotice(account ? "Goal saved to your account." : "Goal saved.");
    } catch (saveError) {
      setNotice(errorMessage(saveError));
    }
  }

  async function onRace(event: FormEvent) {
    event.preventDefault();
    setNotice(null);
    try {
      const body = {
        name: race.name,
        race_date: race.race_date || null,
        distance_label: race.distance_label || null,
        goal_time: race.goal_time || null,
        result_time: race.result_time || null,
        notes: race.notes || null,
      };
      const account = await hasAccount();
      if (account) await saveAccountRace(athleteId, body);
      try {
        await saveRace(athleteId, body);
      } catch (localError) {
        if (!account) throw localError;
      }
      setRace(emptyRace);
      await load();
      setNotice(account ? "Race saved to your account." : "Race added.");
    } catch (saveError) {
      setNotice(errorMessage(saveError));
    }
  }

  async function removeRace(item: RaceEntry) {
    setNotice(null);
    try {
      if (fromAccount) {
        await deleteAccountRace(item.id);
        const local = await getAthleteGoals(athleteId).catch(() => null);
        const twin = local?.races.find((raceItem) => raceItem.name === item.name && raceItem.race_date === item.race_date);
        if (twin) await deleteRace(athleteId, twin.id).catch(() => undefined);
      } else {
        await deleteRace(athleteId, item.id);
      }
      await load();
    } catch (removeError) {
      setNotice(errorMessage(removeError));
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="font-heading text-4xl tracking-tight">Goals and races</h1>
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">The goal your coach sees on the roster, plus the races you are training around.</p>
      </div>
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      {notice ? <p className="text-sm">{notice}</p> : null}
      <Card>
        <CardHeader>
          <CardTitle>Training goal</CardTitle>
          <CardDescription>Distance or event, the date, and the time you are aiming for.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={(event) => void onGoal(event)} className="grid gap-3 sm:grid-cols-3">
            <label className="text-sm sm:col-span-3">Race goal<input value={goal} onChange={(event) => setGoal(event.target.value)} className={fieldClass} /></label>
            <label className="text-sm">Date<input type="date" value={goalDate} onChange={(event) => setGoalDate(event.target.value)} className={fieldClass} /></label>
            <label className="text-sm">Target time<input value={target} onChange={(event) => setTarget(event.target.value)} placeholder="2:55:00" className={fieldClass} /></label>
            <div className="sm:col-span-3"><Button type="submit">Save goal</Button></div>
          </form>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Race calendar</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {(goals?.races ?? []).length === 0 ? <p className="text-sm text-muted-foreground">No races saved.</p> : null}
          <ul className="space-y-2 text-sm">
            {(goals?.races ?? []).map((item) => (
              <li key={item.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border px-3 py-2">
                <span>
                  <span className="font-medium">{item.name}</span>
                  <span className="text-muted-foreground">
                    {item.race_date ? ` · ${item.race_date}` : ""}
                    {item.distance_label ? ` · ${item.distance_label}` : ""}
                    {item.goal_time ? ` · goal ${item.goal_time}` : ""}
                    {item.result_time ? ` · ${item.result_time}` : ""}
                  </span>
                </span>
                <Button type="button" variant="ghost" size="sm" onClick={() => void removeRace(item)}>Remove</Button>
              </li>
            ))}
          </ul>
          <form onSubmit={(event) => void onRace(event)} className="grid gap-3 sm:grid-cols-2">
            <label className="text-sm">Race<input value={race.name} onChange={(event) => setRace({ ...race, name: event.target.value })} className={fieldClass} required /></label>
            <label className="text-sm">Date<input type="date" value={race.race_date} onChange={(event) => setRace({ ...race, race_date: event.target.value })} className={fieldClass} /></label>
            <label className="text-sm">Distance<input value={race.distance_label} onChange={(event) => setRace({ ...race, distance_label: event.target.value })} placeholder="5K, half marathon, marathon" className={fieldClass} /></label>
            <label className="text-sm">Goal time<input value={race.goal_time} onChange={(event) => setRace({ ...race, goal_time: event.target.value })} placeholder="19:30" className={fieldClass} /></label>
            <label className="text-sm">Result<input value={race.result_time} onChange={(event) => setRace({ ...race, result_time: event.target.value })} placeholder="20:00" className={fieldClass} /></label>
            <label className="text-sm">Notes<input value={race.notes} onChange={(event) => setRace({ ...race, notes: event.target.value })} className={fieldClass} /></label>
            <div className="sm:col-span-2"><Button type="submit">Add race</Button></div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
