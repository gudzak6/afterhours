"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { signedInAthleteId } from "@/lib/account";
import { AthleteName } from "@/components/athlete-name";
import { GarminConnect } from "@/components/athlete-onboarding";
import { errorMessage, getAthlete, getPortal, type PortalStatus } from "@/lib/api";

const ID_KEY = "trainingcoach-athlete";
const SKIP_KEY = "trainingcoach-garmin-skipped";

type AthleteContextValue = {
  athleteId: number;
  status: PortalStatus;
  reload: () => Promise<void>;
  openGarmin: () => void;
};

const AthleteContext = createContext<AthleteContextValue | null>(null);

export function useAthlete() {
  const value = useContext(AthleteContext);
  if (!value) {
    throw new Error("Athlete pages render inside the athlete frame.");
  }
  return value;
}

export function clearAthleteSession() {
  window.sessionStorage.removeItem(ID_KEY);
  window.sessionStorage.removeItem(SKIP_KEY);
}

export function AthleteFrame({ children }: { children: React.ReactNode }) {
  const [athleteId, setAthleteId] = useState<number | null>(null);
  const [status, setStatus] = useState<PortalStatus | null>(null);
  const [phase, setPhase] = useState<"loading" | "connect" | "app">("loading");
  const [error, setError] = useState<string | null>(null);

  function remember(next: PortalStatus) {
    window.sessionStorage.setItem(ID_KEY, String(next.athlete.id));
    setAthleteId(next.athlete.id);
    setStatus(next);
    // New athletes stay here until their own Garmin sign-in is accepted.
    const linked = next.garmin.connected || next.garmin.status === "connected";
    setPhase(linked ? "app" : "connect");
  }

  async function reload() {
    if (athleteId == null) return;
    remember(await getPortal(athleteId));
  }

  useEffect(() => {
    const raw = window.sessionStorage.getItem(ID_KEY);
    const stored = raw ? Number(raw) : NaN;
    void (async () => {
      try {
        const owned = await signedInAthleteId();
        let id = owned ?? (Number.isFinite(stored) ? stored : (await getAthlete()).id);
        let next: PortalStatus;
        try {
          next = await getPortal(id);
        } catch (portalError) {
          if (owned != null || !Number.isFinite(stored)) throw portalError;
          window.sessionStorage.removeItem(ID_KEY);
          id = (await getAthlete()).id;
          next = await getPortal(id);
        }
        remember(next);
      } catch (loadError: unknown) {
        window.sessionStorage.removeItem(ID_KEY);
        setError(errorMessage(loadError));
        setPhase("connect");
      }
    })();
  }, []);

  if (phase === "loading") {
    return <p className="text-sm text-muted-foreground">Loading your training…</p>;
  }
  if (phase === "connect" && athleteId != null) {
    return (
      <GarminConnect
        athleteId={athleteId}
        lastError={status?.garmin.last_error ?? null}
        onConnected={(next) => remember(next)}
      />
    );
  }
  if (phase === "connect") {
    return error ? <p className="text-sm text-destructive">{error}</p> : <p className="text-sm text-muted-foreground">Loading your training…</p>;
  }
  if (!status || athleteId == null) {
    return <p className="text-sm text-muted-foreground">Loading your training…</p>;
  }
  return (
    <AthleteContext.Provider value={{ athleteId, status, reload, openGarmin: () => setPhase("connect") }}>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-2 text-sm text-muted-foreground">
        <p><AthleteName name={status.athlete.display_name} /> · Coach Owen</p>
        <button
          type="button"
          className="underline"
          onClick={() => {
            window.sessionStorage.removeItem(SKIP_KEY);
            setPhase("connect");
          }}
        >
          Reconnect Garmin
        </button>
      </div>
      {children}
    </AthleteContext.Provider>
  );
}
