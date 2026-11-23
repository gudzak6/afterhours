"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useAthlete } from "@/components/athlete-frame";
import { accountEmail } from "@/lib/account";

export default function AthleteSettingsPage() {
  const { openGarmin } = useAthlete();
  const [email, setEmail] = useState<string | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void accountEmail().then(setEmail).catch(() => setEmail(null));
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="font-heading text-2xl tracking-tight sm:text-3xl">Settings</h1>
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">Your account, and the way into the coach view.</p>
      </div>
      <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap">
        <Link href="/login" className="inline-flex min-h-11 items-center justify-center border border-foreground/30 bg-background px-4 text-[11px] tracking-[0.14em] uppercase sm:justify-start">
          {email ?? "Sign in"}
        </Link>
        <Link href="/" className="inline-flex min-h-11 items-center justify-center border border-foreground/30 bg-background px-4 text-[11px] tracking-[0.14em] uppercase sm:justify-start">
          Coach
        </Link>
        <button
          type="button"
          className="inline-flex min-h-11 items-center justify-center border border-foreground/30 bg-background px-4 text-[11px] tracking-[0.14em] uppercase sm:justify-start"
          onClick={() => {
            window.sessionStorage.removeItem("trainingcoach-garmin-skipped");
            openGarmin();
          }}
        >
          Reconnect Garmin
        </button>
      </div>
    </div>
  );
}
