"use client";

import Link from "next/link";
import { CoachAccountCard } from "@/components/coach-account";

export default function SettingsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-heading text-2xl tracking-tight sm:text-3xl">Settings</h1>
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
          Coach Owen’s name, timezone, and the daily brief. Athlete profiles and Garmin sign-in stay on the athlete side.
        </p>
      </div>
      <Link
        href="/athlete"
        className="inline-flex border border-foreground/30 bg-background px-3 py-2 text-[11px] tracking-[0.16em] uppercase"
      >
        Athletes view
      </Link>
      <CoachAccountCard />
    </div>
  );
}
