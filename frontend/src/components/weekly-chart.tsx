"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { WeeklyMileage } from "@/lib/api";

export function WeeklyChart({ weeks }: { weeks: WeeklyMileage[] }) {
  const points = weeks
    .filter((week) => week.distance_miles != null)
    .map((week) => ({
      label: week.week_start.slice(5),
      miles: week.distance_miles,
    }));
  if (points.length === 0) {
    return <p className="text-sm text-muted-foreground">Weekly mileage appears after activities with distance are imported.</p>;
  }
  return (
    <div className="h-48 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={points}>
          <CartesianGrid vertical={false} stroke="oklch(0.88 0.02 80)" />
          <XAxis dataKey="label" tickLine={false} axisLine={false} />
          <YAxis tickLine={false} axisLine={false} width={36} />
          <Tooltip formatter={(value) => [`${Number(value).toFixed(2)} mi`, "Distance"]} />
          <Bar dataKey="miles" fill="oklch(0.42 0.08 150)" radius={[6, 6, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
