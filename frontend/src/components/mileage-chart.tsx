"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { TrainingSummary } from "@/lib/api";

export function MileageChart({ summary }: { summary: TrainingSummary }) {
  const points = [
    {
      label: "7 days",
      miles: summary.last_7_days.distance_miles,
    },
    {
      label: "28 days",
      miles: summary.last_28_days.distance_miles,
    },
  ].filter((point): point is { label: string; miles: number } => point.miles != null);

  if (points.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        Mileage appears after a sync returns activities that include Garmin distance.
      </p>
    );
  }

  return (
    <div className="h-48 w-full min-w-0">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={points} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke="oklch(0.88 0.02 80)" />
          <XAxis dataKey="label" tickLine={false} axisLine={false} />
          <YAxis tickLine={false} axisLine={false} width={36} unit=" mi" />
          <Tooltip formatter={(value) => [`${Number(value).toFixed(2)} mi`, "Distance"]} />
          <Bar dataKey="miles" fill="oklch(0.5 0.13 42)" radius={[6, 6, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
