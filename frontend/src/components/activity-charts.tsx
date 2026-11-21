"use client";

import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { SeriesPoint } from "@/lib/api";
import { formatPace } from "@/lib/format";

const PACE_CHART_MAX_SECONDS = 15 * 60;

function minutes(seconds: number | null): number | null {
  if (seconds == null) {
    return null;
  }
  return Math.round((seconds / 60) * 100) / 100;
}

export function ActivityCharts({ series }: { series: SeriesPoint[] }) {
  const points = series.map((point) => ({
    minute: minutes(point.elapsed_seconds),
    pace:
      point.pace_seconds_per_mile != null && point.pace_seconds_per_mile <= PACE_CHART_MAX_SECONDS
        ? point.pace_seconds_per_mile
        : null,
    heart: point.heart_rate_bpm,
  }));
  const hasPace = points.some((point) => point.pace != null);
  const hasHeart = points.some((point) => point.heart != null);

  if (!hasPace && !hasHeart) {
    return <p className="text-sm text-muted-foreground">No pace or heart-rate samples are stored for this activity.</p>;
  }

  return (
    <div className="space-y-6">
      {hasPace ? (
        <div>
          <p className="mb-2 text-sm text-muted-foreground">
            Pace from sample speed. Gaps stay blank when speed is missing or zero. Samples slower than 15:00 per mile stay in the lap table and are left off this chart.
          </p>
          <div className="h-56 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={points}>
                <CartesianGrid vertical={false} stroke="oklch(0.88 0.02 80)" />
                <XAxis dataKey="minute" unit=" min" tickLine={false} axisLine={false} />
                <YAxis
                  tickLine={false}
                  axisLine={false}
                  width={48}
                  reversed
                  domain={["auto", "auto"]}
                  tickFormatter={(value) => formatPace(Number(value), true).replace(" /mi", "")}
                />
                <Tooltip formatter={(value) => [formatPace(value == null ? null : Number(value), value != null), "Pace"]} />
                <Line type="monotone" dataKey="pace" stroke="oklch(0.5 0.13 42)" dot={false} connectNulls={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      ) : null}
      {hasHeart ? (
        <div>
          <p className="mb-2 text-sm text-muted-foreground">Heart rate from the FIT record stream.</p>
          <div className="h-48 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={points}>
                <CartesianGrid vertical={false} stroke="oklch(0.88 0.02 80)" />
                <XAxis dataKey="minute" unit=" min" tickLine={false} axisLine={false} />
                <YAxis tickLine={false} axisLine={false} width={36} unit=" bpm" />
                <Tooltip />
                <Line type="monotone" dataKey="heart" stroke="oklch(0.42 0.08 150)" dot={false} connectNulls={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      ) : null}
    </div>
  );
}
