"use client";

import { useState } from "react";
import { errorMessage, saveBestEffort, type RunningStats } from "@/lib/api";

function countLabel(value: number | null): string {
  if (value == null) return "—";
  const rounded = value.toFixed(1);
  return rounded.endsWith(".0") ? String(Math.round(value)) : rounded;
}

function hoursLabel(seconds: number | null): string {
  if (seconds == null) return "—";
  const total = Math.round(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

function effortLabel(seconds: number | null): string {
  if (seconds == null) return "—";
  const total = Math.round(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const remainder = total % 60;
  if (hours > 0) return `${hours}:${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
  if (total >= 60) return `${minutes}:${String(remainder).padStart(2, "0")}`;
  return `${remainder}s`;
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4 py-2">
      <span>{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  );
}

function parseClock(value: string): number | null {
  const text = value.trim();
  if (!text || text === "—") return null;
  if (!/^\d{1,2}(:\d{2}){1,2}$/.test(text)) return null;
  const parts = text.split(":").map(Number);
  if (parts.length === 2) {
    if (parts[1] > 59) return null;
    return parts[0] * 60 + parts[1];
  }
  if (parts[1] > 59 || parts[2] > 59) return null;
  return parts[0] * 3600 + parts[1] * 60 + parts[2];
}

function EffortTime({
  athleteId,
  effort,
  onSaved,
}: {
  athleteId: number;
  effort: RunningStats["best_efforts"][number];
  onSaved: (stats: RunningStats) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function save() {
    const seconds = parseClock(draft);
    if (draft.trim() && seconds == null) {
      setError("Use a time like 5:05.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      onSaved(await saveBestEffort(athleteId, effort.label, seconds));
      setEditing(false);
    } catch (saveError) {
      setError(errorMessage(saveError));
    } finally {
      setBusy(false);
    }
  }

  if (editing) {
    return (
      <span className="text-right">
        <input
          autoFocus
          value={draft}
          disabled={busy}
          aria-label={`${effort.label} time`}
          placeholder="5:05"
          onChange={(event) => setDraft(event.target.value)}
          onBlur={() => void save()}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              void save();
            }
            if (event.key === "Escape") setEditing(false);
          }}
          className="w-20 rounded border border-input bg-card px-2 py-1 text-right"
        />
        {error ? <span className="mt-1 block text-xs text-destructive">{error}</span> : null}
      </span>
    );
  }

  const time = effortLabel(effort.duration_seconds);
  return (
    <span className="flex items-center gap-2">
      <span className={effort.duration_seconds == null ? "text-muted-foreground" : "font-medium"}>{effort.duration_seconds == null ? "—" : time}</span>
      <button
        type="button"
        className="inline-flex min-h-11 items-center px-2 text-sm text-muted-foreground underline"
        onClick={() => {
          setDraft(effort.duration_seconds == null ? "" : time);
          setError(null);
          setEditing(true);
        }}
      >
        Edit
      </button>
    </span>
  );
}

export function BestEfforts({
  athleteId,
  efforts,
  onSaved,
}: {
  athleteId: number;
  efforts: RunningStats["best_efforts"];
  onSaved: (stats: RunningStats) => void;
}) {
  return (
    <div>
      <h3 className="font-medium">Best efforts</h3>
      <p className="mt-1 text-muted-foreground">Fastest stretch found in the stored runs. Edit a time to replace it. Clear the time to use the calculated one again.</p>
      <div className="mt-1 divide-y divide-border">
        {efforts.map((effort) => (
          <div key={effort.label} className="flex items-center justify-between gap-4 py-2">
            <span>{effort.label}</span>
            <EffortTime athleteId={athleteId} effort={effort} onSaved={onSaved} />
          </div>
        ))}
      </div>
    </div>
  );
}

export function AthleteStats({
  athleteId,
  stats,
  onChange,
}: {
  athleteId: number;
  stats: RunningStats;
  onChange: (stats: RunningStats) => void;
}) {
  const recent = stats.last_4_weeks;
  return (
    <div className="space-y-5 text-sm">
      <div>
        <h3 className="font-medium">Last 4 weeks</h3>
        <div className="mt-1 divide-y divide-border">
          <Row label="Activities / week" value={countLabel(recent.activities_per_week)} />
          <Row label="Avg distance / week" value={recent.distance_miles == null ? "—" : `${recent.distance_miles.toFixed(1)} mi`} />
          <Row label="Avg time / week" value={hoursLabel(recent.duration_seconds)} />
          <Row label="Elev gain / week" value={recent.elevation_feet == null ? "—" : `${Math.round(recent.elevation_feet)} ft`} />
        </div>
      </div>
      <BestEfforts athleteId={athleteId} efforts={stats.best_efforts} onSaved={onChange} />
    </div>
  );
}
