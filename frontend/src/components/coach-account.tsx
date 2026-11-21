"use client";

import { FormEvent, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { errorMessage, getCoach, updateCoach, type CoachAccount } from "@/lib/api";

export function CoachAccountCard() {
  const [coach, setCoach] = useState<CoachAccount | null>(null);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [timezone, setTimezone] = useState("America/New_York");
  const [enabled, setEnabled] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void getCoach()
        .then((account) => {
          setCoach(account);
          setName(account.display_name);
          setEmail(account.email || "");
          setTimezone(account.timezone);
          setEnabled(account.email_notifications_enabled);
        })
        .catch((loadError: unknown) => setNotice(errorMessage(loadError)));
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    try {
      const body = {
        display_name: name.trim() || "Coach",
        email: email.trim() || null,
        timezone,
        email_notifications_enabled: enabled,
      };
      const updated = await updateCoach(body);
      setCoach(updated);
      setNotice(updated.email_notifications_enabled ? "Daily email is on." : "Daily email is off.");
    } catch (saveError) {
      setNotice(errorMessage(saveError));
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Coach account</CardTitle>
        <CardDescription>
          Email notifications are off until you turn them on. {coach?.email_configured ? "Mail is configured on the server." : "Mail is not configured, so a saved preference will not send anything."}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={(event) => void onSubmit(event)} className="grid gap-3 sm:grid-cols-2">
          <label className="text-sm">
            Name
            <input value={name} onChange={(event) => setName(event.target.value)} className="mt-1 h-9 w-full rounded-lg border border-input bg-card px-3" />
          </label>
          <label className="text-sm">
            Email
            <input value={email} onChange={(event) => setEmail(event.target.value)} className="mt-1 h-9 w-full rounded-lg border border-input bg-card px-3" />
          </label>
          <label className="text-sm">
            Timezone
            <input value={timezone} onChange={(event) => setTimezone(event.target.value)} className="mt-1 h-9 w-full rounded-lg border border-input bg-card px-3" />
          </label>
          <label className="flex items-end gap-2 text-sm">
            <input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} />
            Send the daily coaching brief
          </label>
          <div className="sm:col-span-2">
            <Button type="submit">Save coach settings</Button>
          </div>
          {notice ? <p className="text-sm sm:col-span-2">{notice}</p> : null}
        </form>
      </CardContent>
    </Card>
  );
}
