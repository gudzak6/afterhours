"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { accountEmail } from "@/lib/account";

export default function AthleteSettingsPage() {
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
        <h1 className="font-heading text-4xl tracking-tight">Settings</h1>
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">Your account, and the way into the coach view.</p>
      </div>
      <div className="flex flex-wrap gap-3">
        <Link href="/login" className="inline-flex border border-foreground/30 bg-background px-3 py-2 text-[11px] tracking-[0.16em] uppercase">
          {email ?? "Sign in"}
        </Link>
        <Link href="/" className="inline-flex border border-foreground/30 bg-background px-3 py-2 text-[11px] tracking-[0.16em] uppercase">
          Coach
        </Link>
      </div>
    </div>
  );
}
