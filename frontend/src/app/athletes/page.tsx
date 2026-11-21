"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { errorMessage, getDashboard, type CoachDashboard } from "@/lib/api";

export default function AthletesPage() {
  const [dashboard, setDashboard] = useState<CoachDashboard | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setDashboard(await getDashboard());
      setError(null);
    } catch (loadError) {
      setError(errorMessage(loadError));
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  const coachName = dashboard?.coach.display_name || "Coach";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-heading text-4xl tracking-tight">Athletes</h1>
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
          Everyone on the roster. Open an athlete to see their training.
        </p>
      </div>
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      {!dashboard && !error ? <p className="text-sm text-muted-foreground">Loading the roster…</p> : null}
      {dashboard ? (
        dashboard.athletes.length === 0 ? (
          <p className="text-sm text-muted-foreground">No athletes on the roster.</p>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-border">
            <table className="w-full min-w-[32rem] text-left text-sm">
              <thead className="text-xs tracking-wide text-muted-foreground uppercase">
                <tr className="border-b border-border">
                  <th className="px-4 py-3 font-medium">Athlete</th>
                  <th className="px-4 py-3 font-medium">Coach</th>
                </tr>
              </thead>
              <tbody>
                {dashboard.athletes.map((athlete) => (
                  <tr key={athlete.id} className="border-b border-border/70 last:border-0">
                    <td className="px-4 py-3">
                      <Link href={`/athletes/${athlete.id}`} className="font-medium hover:underline">
                        {athlete.display_name}
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{coachName}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      ) : null}
    </div>
  );
}
