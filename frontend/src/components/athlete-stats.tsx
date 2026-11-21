import Link from "next/link";
import type { RunningStats } from "@/lib/api";

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

export function AthleteStats({ stats }: { stats: RunningStats }) {
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
      <div>
        <h3 className="font-medium">Best efforts</h3>
        <p className="mt-1 text-muted-foreground">Fastest stretch found in the stored runs. A distance with no recording is left blank.</p>
        <div className="mt-1 divide-y divide-border">
          {stats.best_efforts.map((effort) => (
            <div key={effort.label} className="flex items-center justify-between gap-4 py-2">
              <span>{effort.label}</span>
              {effort.garmin_activity_id != null && effort.duration_seconds != null ? (
                <Link href={`/activities/${effort.garmin_activity_id}`} className="font-medium text-primary hover:underline">
                  {effortLabel(effort.duration_seconds)}
                </Link>
              ) : (
                <span className="text-muted-foreground">—</span>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
