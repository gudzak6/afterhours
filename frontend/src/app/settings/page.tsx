"use client";

import { CoachAccountCard } from "@/components/coach-account";

export default function SettingsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-heading text-4xl tracking-tight">Settings</h1>
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
          Coach name, timezone, and the daily brief. Athlete profiles and Garmin sign-in stay on the athlete side.
        </p>
      </div>
      <CoachAccountCard />
    </div>
  );
}
