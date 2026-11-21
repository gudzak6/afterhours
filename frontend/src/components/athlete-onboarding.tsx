"use client";

import { FormEvent, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { areaClass, fieldClass } from "@/components/athlete-ui";
import { connectAthleteGarmin, errorMessage, joinAthlete, type AthleteIntake, type PortalStatus } from "@/lib/api";

const QUESTIONS: Array<{ key: keyof AthleteIntake; label: string; long?: boolean; required?: boolean }> = [
  { key: "events", label: "What events are you training for?", long: true, required: true },
  { key: "outcome_goals", label: "Do you have any specific outcome or race goals you're targeting with training?", long: true, required: true },
  { key: "process_goals", label: "Do you have any specific process goals you're targeting with training?", long: true, required: true },
  { key: "personal_bests", label: "If you have raced before, what are a few of your personal best times or most successful races?", long: true, required: true },
  { key: "weekly_miles_last_3_weeks", label: "How many miles per week have you averaged over the last three weeks?", required: true },
  { key: "weekly_miles_last_3_months", label: "How many miles per week have you averaged over the last three months?", required: true },
  { key: "training_stipulations", label: "Are there any training stipulations we should know?", long: true, required: true },
  { key: "training_style", label: "What type of training makes you click? Strength, speed, or a mixture?", long: true, required: true },
  { key: "strengths", label: "What are your biggest strengths as a runner?", long: true, required: true },
  { key: "weaknesses", label: "What are your biggest weaknesses as a runner?", long: true, required: true },
  { key: "why_run", label: "Why do you run?", long: true, required: true },
  { key: "preferred_coach", label: "Do you have a coach you'd prefer to work with?", long: true, required: true },
  { key: "anything_else", label: "Anything else we should know?", long: true },
  { key: "heard_about_us", label: "How did you hear about us?" },
];

function text(value: string | null | undefined): string {
  return value ?? "";
}

export function AthleteSignup({
  athleteId,
  initial,
  onJoined,
}: {
  athleteId: number | null;
  initial: AthleteIntake | null;
  onJoined: (status: PortalStatus) => void;
}) {
  const [first, setFirst] = useState(text(initial?.first_name));
  const [last, setLast] = useState(text(initial?.last_name));
  const [email, setEmail] = useState(text(initial?.email));
  const [phone, setPhone] = useState(text(initial?.phone));
  const [answers, setAnswers] = useState<Record<string, string>>(() => {
    const draft: Record<string, string> = {};
    for (const question of QUESTIONS) {
      const value = initial?.[question.key];
      draft[question.key] = typeof value === "string" ? value : "";
    }
    return draft;
  });
  const [notice, setNotice] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setNotice(null);
    const intake: AthleteIntake = {
      first_name: first.trim() || null,
      last_name: last.trim() || null,
      email: email.trim() || null,
      phone: phone.trim() || null,
      recent_races: initial?.recent_races ?? [],
    };
    for (const question of QUESTIONS) {
      const value = answers[question.key]?.trim() || null;
      (intake as Record<string, unknown>)[question.key] = value;
    }
    try {
      onJoined(await joinAthlete(intake, athleteId));
    } catch (saveError) {
      setNotice(errorMessage(saveError));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={(event) => void onSubmit(event)} className="space-y-4">
      <div>
        <h1 className="font-heading text-4xl tracking-tight">Let’s build.</h1>
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
          Tell us about your running before you connect Garmin. This is the same intake After Hours uses for new athletes.
        </p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Contact</CardTitle>
          <CardDescription>First name, last name, email, and phone are required.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <label className="text-sm">First name<input value={first} onChange={(event) => setFirst(event.target.value)} className={fieldClass} required /></label>
          <label className="text-sm">Last name<input value={last} onChange={(event) => setLast(event.target.value)} className={fieldClass} required /></label>
          <label className="text-sm">Email<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} className={fieldClass} required /></label>
          <label className="text-sm">Phone<input value={phone} onChange={(event) => setPhone(event.target.value)} className={fieldClass} required /></label>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Training</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4">
          {QUESTIONS.map((question) => (
            <label key={question.key} className="text-sm">
              {question.label}
              {question.long ? (
                <textarea
                  value={answers[question.key]}
                  onChange={(event) => setAnswers((current) => ({ ...current, [question.key]: event.target.value }))}
                  className={areaClass}
                  required={question.required}
                />
              ) : (
                <input
                  value={answers[question.key]}
                  onChange={(event) => setAnswers((current) => ({ ...current, [question.key]: event.target.value }))}
                  className={fieldClass}
                  required={question.required}
                />
              )}
            </label>
          ))}
        </CardContent>
      </Card>
      <Button type="submit" disabled={saving}>{saving ? "Saving…" : "Continue"}</Button>
      {notice ? <p className="text-sm text-destructive">{notice}</p> : null}
    </form>
  );
}

export function GarminConnect({
  athleteId,
  lastError,
  onConnected,
}: {
  athleteId: number;
  lastError: string | null;
  onConnected: (status: PortalStatus) => void;
}) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [needsCode, setNeedsCode] = useState(false);
  const [notice, setNotice] = useState<string | null>(lastError);
  const [saving, setSaving] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setNotice(null);
    try {
      const status = await connectAthleteGarmin(athleteId, email.trim(), password, needsCode ? code.trim() : undefined);
      if (status.mfa_required) {
        setNeedsCode(true);
        setNotice(status.garmin.last_error || "Garmin sent a verification code. Enter it to finish signing in.");
        return;
      }
      setPassword("");
      setCode("");
      if (!status.garmin.connected) {
        setNotice(status.garmin.last_error || status.sync?.error_message || "Garmin did not accept that sign-in.");
        return;
      }
      onConnected(status);
    } catch (connectError) {
      setNotice(errorMessage(connectError));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={(event) => void onSubmit(event)} className="space-y-4">
      <div>
        <h1 className="font-heading text-4xl tracking-tight">Connect Garmin</h1>
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
          Sign in with the email and password you use for Garmin Connect. Your password is used to sign in and is not saved. The coach API key is not part of this step.
        </p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Garmin Connect</CardTitle>
          <CardDescription>Use the same sign-in as the Garmin Connect app.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <label className="grid gap-1 text-sm">
            Email
            <input
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              type="email"
              autoComplete="username"
              placeholder="you@email.com"
              className={fieldClass}
              required
            />
          </label>
          <label className="grid gap-1 text-sm">
            Password
            <input
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              type="password"
              autoComplete="current-password"
              className={fieldClass}
              required
            />
          </label>
          {needsCode ? (
            <label className="grid gap-1 text-sm">
              Verification code
              <input
                value={code}
                onChange={(event) => setCode(event.target.value)}
                inputMode="numeric"
                autoComplete="one-time-code"
                className={fieldClass}
                required
              />
            </label>
          ) : null}
          <Button type="submit" disabled={saving}>{saving ? "Signing in…" : needsCode ? "Verify and import" : "Sign in and import"}</Button>
          {notice ? <p className="text-sm text-destructive">{notice}</p> : null}
        </CardContent>
      </Card>
    </form>
  );
}
