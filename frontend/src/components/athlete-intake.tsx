"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { hasAccount, saveOwnedAthlete } from "@/lib/account";
import { errorMessage, updateAthleteById, type Athlete, type AthleteIntake, type RecentRace } from "@/lib/api";

const inputClass = "mt-1 h-9 w-full rounded-lg border border-input bg-card px-3 text-sm";
const areaClass = "mt-1 min-h-24 w-full rounded-lg border border-input bg-card px-3 py-2 text-sm";

type RaceDraft = {
  event: string;
  race_date: string;
  goal_time: string;
  result_time: string;
};

type IntakeDraft = {
  first_name: string;
  last_name: string;
  email: string;
  phone: string;
  events: string;
  outcome_goals: string;
  process_goals: string;
  personal_bests: string;
  weekly_miles_last_3_weeks: string;
  weekly_miles_last_3_months: string;
  training_stipulations: string;
  training_style: string;
  strengths: string;
  weaknesses: string;
  why_run: string;
  preferred_coach: string;
  anything_else: string;
  heard_about_us: string;
  recent_races: RaceDraft[];
};

const EMPTY_RACE: RaceDraft = { event: "", race_date: "", goal_time: "", result_time: "" };

function text(value: string | null | undefined): string {
  return value ?? "";
}

function draftFrom(athlete: Athlete): IntakeDraft {
  const intake = athlete.intake;
  const races = (intake?.recent_races ?? []).map((race) => ({
    event: text(race.event),
    race_date: text(race.race_date),
    goal_time: text(race.goal_time),
    result_time: text(race.result_time),
  }));
  return {
    first_name: text(intake?.first_name),
    last_name: text(intake?.last_name),
    email: text(intake?.email),
    phone: text(intake?.phone),
    events: text(intake?.events),
    outcome_goals: text(intake?.outcome_goals),
    process_goals: text(intake?.process_goals),
    personal_bests: text(intake?.personal_bests),
    weekly_miles_last_3_weeks: text(intake?.weekly_miles_last_3_weeks),
    weekly_miles_last_3_months: text(intake?.weekly_miles_last_3_months),
    training_stipulations: text(intake?.training_stipulations),
    training_style: text(intake?.training_style),
    strengths: text(intake?.strengths),
    weaknesses: text(intake?.weaknesses),
    why_run: text(intake?.why_run),
    preferred_coach: text(intake?.preferred_coach),
    anything_else: text(intake?.anything_else),
    heard_about_us: text(intake?.heard_about_us),
    recent_races: races.length > 0 ? races : [{ ...EMPTY_RACE }],
  };
}

function blank(value: string): string | null {
  const trimmed = value.trim();
  return trimmed || null;
}

function payloadFrom(draft: IntakeDraft): AthleteIntake {
  const recent_races: RecentRace[] = draft.recent_races
    .map((race) => ({
      event: blank(race.event),
      race_date: blank(race.race_date),
      goal_time: blank(race.goal_time),
      result_time: blank(race.result_time),
    }))
    .filter((race) => race.event || race.race_date || race.goal_time || race.result_time);
  return {
    first_name: blank(draft.first_name),
    last_name: blank(draft.last_name),
    email: blank(draft.email),
    phone: blank(draft.phone),
    events: blank(draft.events),
    outcome_goals: blank(draft.outcome_goals),
    process_goals: blank(draft.process_goals),
    personal_bests: blank(draft.personal_bests),
    weekly_miles_last_3_weeks: blank(draft.weekly_miles_last_3_weeks),
    weekly_miles_last_3_months: blank(draft.weekly_miles_last_3_months),
    training_stipulations: blank(draft.training_stipulations),
    training_style: blank(draft.training_style),
    strengths: blank(draft.strengths),
    weaknesses: blank(draft.weaknesses),
    why_run: blank(draft.why_run),
    preferred_coach: blank(draft.preferred_coach),
    anything_else: blank(draft.anything_else),
    heard_about_us: blank(draft.heard_about_us),
    recent_races,
  };
}

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block text-sm">
      <span>{label}</span>
      {hint ? <span className="mt-0.5 block text-xs font-normal text-muted-foreground">{hint}</span> : null}
      {children}
    </label>
  );
}

export function AthleteIntakeForm({ athlete, onSaved }: { athlete: Athlete; onSaved: (athlete: Athlete) => void }) {
  const [goal, setGoal] = useState(athlete.primary_race_goal ?? "");
  const [goalDate, setGoalDate] = useState(athlete.goal_race_date ?? "");
  const [target, setTarget] = useState(athlete.target_time ?? "");
  const [notes, setNotes] = useState(athlete.coach_notes ?? "");
  const [draft, setDraft] = useState<IntakeDraft>(() => draftFrom(athlete));
  const [notice, setNotice] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setGoal(athlete.primary_race_goal ?? "");
    setGoalDate(athlete.goal_race_date ?? "");
    setTarget(athlete.target_time ?? "");
    setNotes(athlete.coach_notes ?? "");
    setDraft(draftFrom(athlete));
  }, [athlete]);

  function updateDraft<K extends keyof IntakeDraft>(key: K, value: IntakeDraft[K]) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  function updateRace(index: number, key: keyof RaceDraft, value: string) {
    setDraft((current) => ({
      ...current,
      recent_races: current.recent_races.map((race, raceIndex) => (raceIndex === index ? { ...race, [key]: value } : race)),
    }));
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setNotice(null);
    try {
      const body = {
        primary_race_goal: blank(goal),
        goal_race_date: blank(goalDate),
        target_time: blank(target),
        coach_notes: blank(notes),
        intake: payloadFrom(draft),
      };
      const account = await hasAccount();
      if (account) await saveOwnedAthlete(athlete.id, body);
      const updated = await updateAthleteById(athlete.id, body);
      onSaved(updated);
      setNotice(account ? "Profile saved to your account." : "Profile saved.");
    } catch (saveError) {
      setNotice(errorMessage(saveError));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={(event) => void onSubmit(event)} className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Contact</CardTitle>
          <CardDescription>Name, email, and phone from the intake form. A first and last name also updates the roster name.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <Field label="First name">
            <input value={draft.first_name} onChange={(event) => updateDraft("first_name", event.target.value)} className={inputClass} />
          </Field>
          <Field label="Last name">
            <input value={draft.last_name} onChange={(event) => updateDraft("last_name", event.target.value)} className={inputClass} />
          </Field>
          <Field label="Email">
            <input type="email" value={draft.email} onChange={(event) => updateDraft("email", event.target.value)} className={inputClass} />
          </Field>
          <Field label="Phone">
            <input value={draft.phone} onChange={(event) => updateDraft("phone", event.target.value)} className={inputClass} />
          </Field>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Goals</CardTitle>
          <CardDescription>The race goal, date, and target time are the short goal shown on the roster.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Race goal">
              <input value={goal} onChange={(event) => setGoal(event.target.value)} className={inputClass} />
            </Field>
            <Field label="Goal date">
              <input type="date" value={goalDate} onChange={(event) => setGoalDate(event.target.value)} className={inputClass} />
            </Field>
            <Field label="Target time">
              <input value={target} onChange={(event) => setTarget(event.target.value)} placeholder="2:55:00" className={inputClass} />
            </Field>
          </div>
          <Field label="What events are you training for?">
            <textarea value={draft.events} onChange={(event) => updateDraft("events", event.target.value)} className={areaClass} />
          </Field>
          <Field label="Do you have any specific outcome or race goals you're targeting with training?">
            <textarea value={draft.outcome_goals} onChange={(event) => updateDraft("outcome_goals", event.target.value)} className={areaClass} />
          </Field>
          <Field label="Do you have any specific process goals you're targeting with training?">
            <textarea value={draft.process_goals} onChange={(event) => updateDraft("process_goals", event.target.value)} className={areaClass} />
          </Field>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Recent races</CardTitle>
          <CardDescription>Each recent race, the time they were aiming for, and the time they ran.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {draft.recent_races.map((race, index) => (
            <div key={index} className="grid gap-3 rounded-lg border border-border p-3 sm:grid-cols-2">
              <Field label="Event">
                <input value={race.event} onChange={(event) => updateRace(index, "event", event.target.value)} className={inputClass} />
              </Field>
              <Field label="Date">
                <input type="date" value={race.race_date} onChange={(event) => updateRace(index, "race_date", event.target.value)} className={inputClass} />
              </Field>
              <Field label="Goal time">
                <input value={race.goal_time} onChange={(event) => updateRace(index, "goal_time", event.target.value)} placeholder="2:55:00" className={inputClass} />
              </Field>
              <Field label="Result time">
                <input value={race.result_time} onChange={(event) => updateRace(index, "result_time", event.target.value)} placeholder="2:58:12" className={inputClass} />
              </Field>
              {draft.recent_races.length > 1 ? (
                <div className="sm:col-span-2">
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => setDraft((current) => ({ ...current, recent_races: current.recent_races.filter((_, raceIndex) => raceIndex !== index) }))}
                  >
                    Remove race
                  </Button>
                </div>
              ) : null}
            </div>
          ))}
          <Button
            type="button"
            variant="outline"
            onClick={() => setDraft((current) => ({ ...current, recent_races: [...current.recent_races, { ...EMPTY_RACE }] }))}
          >
            Add race
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Training background</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4">
          <Field label="If you have raced before, what are a few of your personal best times or most successful races?">
            <textarea value={draft.personal_bests} onChange={(event) => updateDraft("personal_bests", event.target.value)} className={areaClass} />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="How many miles per week have you averaged over the last three weeks?">
              <input value={draft.weekly_miles_last_3_weeks} onChange={(event) => updateDraft("weekly_miles_last_3_weeks", event.target.value)} className={inputClass} />
            </Field>
            <Field label="How many miles per week have you averaged over the last three months?">
              <input value={draft.weekly_miles_last_3_months} onChange={(event) => updateDraft("weekly_miles_last_3_months", event.target.value)} className={inputClass} />
            </Field>
          </div>
          <Field label="Are there any training stipulations we should know?" hint="Required days off, max mileage, or anything else that should shape the plan.">
            <textarea value={draft.training_stipulations} onChange={(event) => updateDraft("training_stipulations", event.target.value)} className={areaClass} />
          </Field>
          <Field label="What type of training makes you click?" hint="Strength, speed, or a mixture.">
            <textarea value={draft.training_style} onChange={(event) => updateDraft("training_style", event.target.value)} className={areaClass} />
          </Field>
          <Field label="What are your biggest strengths as a runner?">
            <textarea value={draft.strengths} onChange={(event) => updateDraft("strengths", event.target.value)} className={areaClass} />
          </Field>
          <Field label="What are your biggest weaknesses as a runner?">
            <textarea value={draft.weaknesses} onChange={(event) => updateDraft("weaknesses", event.target.value)} className={areaClass} />
          </Field>
          <Field label="Why do you run?">
            <textarea value={draft.why_run} onChange={(event) => updateDraft("why_run", event.target.value)} className={areaClass} />
          </Field>
          <Field label="Do you have a coach you'd prefer to work with?" hint="Preferences are honored when fit, availability, and training goals allow it.">
            <input value={draft.preferred_coach} onChange={(event) => updateDraft("preferred_coach", event.target.value)} className={inputClass} />
          </Field>
          <Field label="Anything else we should know?">
            <textarea value={draft.anything_else} onChange={(event) => updateDraft("anything_else", event.target.value)} className={areaClass} />
          </Field>
          <Field label="How did you hear about us?">
            <input value={draft.heard_about_us} onChange={(event) => updateDraft("heard_about_us", event.target.value)} className={inputClass} />
          </Field>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Coach Owen notes</CardTitle>
          <CardDescription>Private notes for this athlete. They are separate from the intake answers.</CardDescription>
        </CardHeader>
        <CardContent>
          <label className="block text-sm">
            Notes
            <textarea value={notes} onChange={(event) => setNotes(event.target.value)} className={areaClass} />
          </label>
        </CardContent>
      </Card>

      <Button type="submit" disabled={saving}>{saving ? "Saving…" : "Save profile"}</Button>
      {notice ? <p className="text-sm">{notice}</p> : null}
    </form>
  );
}

function formatRaceDate(value: string | null | undefined): string {
  if (!value) return "";
  const [year, month, day] = value.split("-");
  if (!year || !month || !day) return value;
  const date = new Date(Number(year), Number(month) - 1, Number(day));
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function hasIntake(athlete: Athlete): boolean {
  const intake = athlete.intake;
  if (!intake) return false;
  const answers = [
    intake.first_name,
    intake.last_name,
    intake.email,
    intake.phone,
    intake.events,
    intake.outcome_goals,
    intake.process_goals,
    intake.personal_bests,
    intake.weekly_miles_last_3_weeks,
    intake.weekly_miles_last_3_months,
    intake.training_stipulations,
    intake.training_style,
    intake.strengths,
    intake.weaknesses,
    intake.why_run,
    intake.preferred_coach,
    intake.anything_else,
    intake.heard_about_us,
  ];
  return answers.some((value) => Boolean(value && value.trim())) || (intake.recent_races ?? []).length > 0;
}

export function IntakeSummary({ athlete }: { athlete: Athlete | null }) {
  if (!athlete) return null;
  const intake = athlete.intake;
  const races = intake?.recent_races ?? [];
  const goalLine = [
    athlete.primary_race_goal,
    athlete.target_time,
    athlete.goal_race_date ? formatRaceDate(athlete.goal_race_date) : null,
  ].filter(Boolean).join(" · ");
  const rows: Array<[string, string | null | undefined]> = [
    ["Events", intake?.events],
    ["Outcome goals", intake?.outcome_goals],
    ["Process goals", intake?.process_goals],
    ["Personal bests", intake?.personal_bests],
    ["Miles, last 3 weeks", intake?.weekly_miles_last_3_weeks],
    ["Miles, last 3 months", intake?.weekly_miles_last_3_months],
    ["Stipulations", intake?.training_stipulations],
    ["Training that clicks", intake?.training_style],
    ["Strengths", intake?.strengths],
    ["Weaknesses", intake?.weaknesses],
    ["Why they run", intake?.why_run],
    ["Preferred coach", intake?.preferred_coach],
    ["Anything else", intake?.anything_else],
    ["Heard about us", intake?.heard_about_us],
    ["Coach Owen notes", athlete.coach_notes],
  ];
  const filled = rows.filter((row) => row[1] && row[1].trim());
  const contact = [intake?.email, intake?.phone].filter(Boolean).join(" · ");

  return (
    <Card>
      <CardHeader>
        <CardTitle>Intake</CardTitle>
        <CardDescription>
          {goalLine || "No race goal saved"}
          {contact ? ` · ${contact}` : ""}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        {!hasIntake(athlete) && !goalLine && !athlete.coach_notes ? (
          <p className="text-muted-foreground">
            No intake saved yet.{" "}
            <Link href={`/athletes/${athlete.id}?section=profile`} className="underline">
              Add it on the profile
            </Link>
            .
          </p>
        ) : null}
        {races.length > 0 ? (
          <div>
            <p className="font-medium">Recent races</p>
            <ul className="mt-2 space-y-2">
              {races.map((race, index) => (
                <li key={`${race.event ?? "race"}-${index}`}>
                  <span className="font-medium">{race.event || "Race"}</span>
                  <span className="text-muted-foreground">
                    {race.race_date ? ` · ${formatRaceDate(race.race_date)}` : ""}
                    {race.goal_time ? ` · goal ${race.goal_time}` : ""}
                    {race.result_time ? ` · ran ${race.result_time}` : ""}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        {filled.length > 0 ? (
          <dl className="space-y-3">
            {filled.map(([label, value]) => (
              <div key={label}>
                <dt className="font-medium">{label}</dt>
                <dd className="whitespace-pre-wrap text-muted-foreground">{value}</dd>
              </div>
            ))}
          </dl>
        ) : null}
      </CardContent>
    </Card>
  );
}
