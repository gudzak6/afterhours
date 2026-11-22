import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDuration, formatHeartRate, formatPace } from "@/lib/format";

const MILE = 1609.344;

type Repetition = {
  index: number;
  label: string;
  duration_seconds: number;
  pace_seconds_per_mile: number | null;
  average_heart_rate_bpm: number | null;
  recovery_seconds: number | null;
  recovery: string | null;
};

type BreakdownGroup = {
  heading: string | null;
  repetitions: Repetition[];
};

export type WorkoutBreakdownData = {
  label: string | null;
  kind?: string | null;
  warmup_meters: number | null;
  cooldown_meters: number | null;
  repetitions: Repetition[];
  groups: BreakdownGroup[];
};

export function workoutBreakdown(metrics: Record<string, unknown>): WorkoutBreakdownData | null {
  const value = metrics.workout_breakdown;
  if (!value || typeof value !== "object") {
    return null;
  }
  const breakdown = value as WorkoutBreakdownData;
  if (!breakdown.label || !Array.isArray(breakdown.repetitions) || breakdown.repetitions.length === 0) {
    return null;
  }
  return breakdown;
}

function miles(meters: number | null): string | null {
  if (meters == null || meters < 200) {
    return null;
  }
  return `${(meters / MILE).toFixed(2)} mi`;
}

export function WorkoutBreakdown({ metrics }: { metrics: Record<string, unknown> }) {
  const breakdown = workoutBreakdown(metrics);
  if (!breakdown) {
    if (metrics.workout_intelligence) {
      return null;
    }
    return (
      <Card>
        <CardHeader>
          <CardTitle>Workout reps</CardTitle>
          <CardDescription>This recording does not split into repeated faster efforts.</CardDescription>
        </CardHeader>
      </Card>
    );
  }
  const mileSplits = breakdown.kind === "miles";
  const showJog = breakdown.repetitions.some((rep) => rep.recovery_seconds != null && rep.recovery_seconds >= 15);
  const before = miles(breakdown.warmup_meters);
  const after = miles(breakdown.cooldown_meters);
  const context = [
    before ? `${before} before the reps` : null,
    after ? `${after} after the last rep` : null,
  ].filter(Boolean);

  return (
    <Card>
      <CardHeader>
        <CardTitle>{mileSplits ? "Miles" : "Workout reps"}</CardTitle>
        <CardDescription>
          {mileSplits
            ? "Each row is one mile of the run. The watch split these automatically."
            : "Each pace is the fast portion of that rep. A mile auto-lap does not split a rep that stays fast."}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {mileSplits ? null : <p className="font-heading text-2xl tracking-tight">{breakdown.label}</p>}
        {context.length > 0 ? <p className="text-sm text-muted-foreground">{context.join(" · ")}</p> : null}
        <div className="space-y-5">
          {breakdown.groups.map((group, groupIndex) => (
            <div key={`${group.heading ?? "reps"}-${groupIndex}`} className="space-y-2">
              {group.heading ? <p className="text-sm font-medium">{group.heading}</p> : null}
              <ul className="divide-y divide-border sm:hidden">
                {group.repetitions.map((rep) => (
                  <li key={rep.index} className="py-2">
                    <p className="font-medium">{rep.label}</p>
                    <p className="mt-1 text-sm text-muted-foreground">
                      {formatDuration(rep.duration_seconds, true)}
                      {" · "}
                      {formatPace(rep.pace_seconds_per_mile, rep.pace_seconds_per_mile != null)}
                      {" · "}
                      {formatHeartRate(rep.average_heart_rate_bpm, rep.average_heart_rate_bpm != null)}
                      {showJog && rep.recovery_seconds != null && rep.recovery_seconds >= 15
                        ? ` · jog ${formatDuration(rep.recovery_seconds, true)}`
                        : ""}
                    </p>
                  </li>
                ))}
              </ul>
              <div className="hidden overflow-x-auto sm:block">
                <table className="w-full text-left text-sm">
                  <thead className="text-xs tracking-wide text-muted-foreground uppercase">
                    <tr className="border-b border-border">
                      <th className="px-2 py-2">{mileSplits ? "Mile" : "Rep"}</th>
                      <th className="px-2 py-2">Time</th>
                      <th className="px-2 py-2">Pace</th>
                      <th className="px-2 py-2">Heart rate</th>
                      {showJog ? <th className="px-2 py-2">Jog after</th> : null}
                    </tr>
                  </thead>
                  <tbody>
                    {group.repetitions.map((rep) => (
                      <tr key={rep.index} className="border-b border-border/70">
                        <td className="px-2 py-2 font-medium">{rep.label}</td>
                        <td className="px-2 py-2">{formatDuration(rep.duration_seconds, true)}</td>
                        <td className="px-2 py-2">{formatPace(rep.pace_seconds_per_mile, rep.pace_seconds_per_mile != null)}</td>
                        <td className="px-2 py-2">
                          {formatHeartRate(rep.average_heart_rate_bpm, rep.average_heart_rate_bpm != null)}
                        </td>
                        {showJog ? (
                          <td className="px-2 py-2 text-muted-foreground">
                            {rep.recovery_seconds != null && rep.recovery_seconds >= 15
                              ? formatDuration(rep.recovery_seconds, true)
                              : "—"}
                          </td>
                        ) : null}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

const WORKOUT_LABELS: Record<string, string> = {
  hill_sprints: "Hill sprints",
  strides: "Strides",
  intervals: "Intervals",
  threshold: "Threshold",
  tempo: "Tempo",
  progression: "Progression",
  easy: "Easy run",
  long_run: "Long run",
  recovery: "Recovery",
  unknown: "Unknown",
};

type EffortRow = {
  index?: number;
  duration_seconds?: number;
  distance_meters?: number;
  pace_seconds_per_mile?: number | null;
  elevation_change_meters?: number | null;
  average_heart_rate_bpm?: number | null;
  heart_rate_usable?: boolean;
  recovery_seconds?: number | null;
};

export function DetectedWorkout({ metrics }: { metrics: Record<string, unknown> }) {
  const value = metrics.workout_intelligence;
  if (!value || typeof value !== "object") {
    return null;
  }
  const intelligence = value as {
    classification?: { workout_type?: string; confidence?: number; repetitions?: number | null; ambiguous?: boolean; evidence?: string[] };
    observed?: { efforts?: EffortRow[]; moving_seconds?: number | null; elapsed_seconds?: number | null; pause_count?: number };
    data_quality?: { limitations?: string[]; missing_fields?: string[] };
  };
  const classification = intelligence.classification;
  if (!classification?.workout_type) {
    return null;
  }
  const label = WORKOUT_LABELS[classification.workout_type] ?? classification.workout_type;
  const confidence = typeof classification.confidence === "number" ? Math.round(classification.confidence * 100) : null;
  const efforts = intelligence.observed?.efforts ?? [];
  const limitations = intelligence.data_quality?.limitations ?? [];
  const pauses = intelligence.observed?.pause_count ?? 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Detected workout</CardTitle>
        <CardDescription>
          {label}
          {confidence != null ? ` · ${confidence}% confidence` : ""}
          {classification.repetitions ? ` · ${classification.repetitions} efforts` : ""}
          {pauses > 0 ? ` · ${pauses} pause${pauses === 1 ? "" : "s"}` : ""}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {classification.ambiguous || classification.workout_type === "unknown" ? (
          <p>The recording does not identify a workout. Missing evidence is listed below.</p>
        ) : null}
        {efforts.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead className="text-xs tracking-wide text-muted-foreground uppercase">
                <tr>
                  <th className="py-2 pr-3">Rep</th>
                  <th className="py-2 pr-3">Time</th>
                  <th className="py-2 pr-3">Distance</th>
                  <th className="py-2 pr-3">Pace</th>
                  <th className="py-2 pr-3">Climb</th>
                  <th className="py-2 pr-3">Heart rate</th>
                  <th className="py-2">Recovery</th>
                </tr>
              </thead>
              <tbody>
                {efforts.map((effort, index) => (
                  <tr key={effort.index ?? index} className="border-t">
                    <td className="py-2 pr-3">{effort.index ?? index + 1}</td>
                    <td className="py-2 pr-3">{formatDuration(effort.duration_seconds ?? null, effort.duration_seconds != null)}</td>
                    <td className="py-2 pr-3">{effort.distance_meters != null ? `${Math.round(effort.distance_meters)} m` : "—"}</td>
                    <td className="py-2 pr-3">{formatPace(effort.pace_seconds_per_mile ?? null, effort.pace_seconds_per_mile != null)}</td>
                    <td className="py-2 pr-3">{effort.elevation_change_meters != null ? `${effort.elevation_change_meters.toFixed(1)} m` : "—"}</td>
                    <td className="py-2 pr-3">
                      {effort.heart_rate_usable
                        ? formatHeartRate(effort.average_heart_rate_bpm ?? null, effort.average_heart_rate_bpm != null)
                        : "not usable"}
                    </td>
                    <td className="py-2">{effort.recovery_seconds != null ? formatDuration(effort.recovery_seconds, true) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
        {limitations.length > 0 ? <p className="text-muted-foreground">{limitations[0]}</p> : null}
      </CardContent>
    </Card>
  );
}
