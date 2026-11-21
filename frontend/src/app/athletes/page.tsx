"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { AthleteName } from "@/components/athlete-name";
import { Button } from "@/components/ui/button";
import { hasAccount } from "@/lib/account";
import { deleteAthlete, errorMessage, getDashboard, type CoachDashboard } from "@/lib/api";

export default function AthletesPage() {
  const [dashboard, setDashboard] = useState<CoachDashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [signedIn, setSignedIn] = useState<boolean | null>(null);
  const [removingId, setRemovingId] = useState<number | null>(null);

  const load = useCallback(async () => {
    try {
      setDashboard(await getDashboard());
      setError(null);
    } catch (loadError) {
      setError(errorMessage(loadError));
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void load();
      void hasAccount().then(setSignedIn).catch(() => setSignedIn(false));
    }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  const coachName = dashboard?.coach.display_name || "Coach Owen";

  async function onRemove(athleteId: number, name: string) {
    const confirmed = window.confirm(`Remove ${name}? Their activities, training plan, and reports are deleted with them.`);
    if (!confirmed) return;
    setRemovingId(athleteId);
    setError(null);
    try {
      await deleteAthlete(athleteId);
      if (window.sessionStorage.getItem("trainingcoach-athlete") === String(athleteId)) {
        window.sessionStorage.removeItem("trainingcoach-athlete");
      }
      await load();
    } catch (removeError) {
      setError(errorMessage(removeError));
    } finally {
      setRemovingId(null);
    }
  }

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
          <p className="text-sm text-muted-foreground">
            {signedIn === false ? (
              <>
                <Link href="/login" className="underline">Sign in</Link> to see athletes saved on your account.
              </>
            ) : (
              "No athletes on the roster."
            )}
          </p>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-border">
            <table className="w-full min-w-[32rem] text-left text-sm">
              <thead className="text-xs tracking-wide text-muted-foreground uppercase">
                <tr className="border-b border-border">
                  <th className="px-4 py-3 font-medium">Athlete</th>
                  <th className="px-4 py-3 font-medium">Coach</th>
                  <th className="px-4 py-3 text-right font-medium">Remove</th>
                </tr>
              </thead>
              <tbody>
                {dashboard.athletes.map((athlete) => (
                  <tr key={athlete.id} className="border-b border-border/70 last:border-0">
                    <td className="px-4 py-3">
                      <Link href={`/athletes/${athlete.id}`} className="font-medium hover:underline">
                        <AthleteName name={athlete.display_name} />
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{coachName}</td>
                    <td className="px-4 py-3 text-right">
                      <Button
                        type="button"
                        size="sm"
                        variant="destructive"
                        disabled={removingId !== null}
                        onClick={() => void onRemove(athlete.id, athlete.display_name)}
                      >
                        {removingId === athlete.id ? "Removing…" : "Remove"}
                      </Button>
                    </td>
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
