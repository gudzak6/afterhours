"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { MileageChart } from "@/lib/api";

const PAST = "oklch(0.72 0.11 230)";
const CURRENT = "oklch(0.42 0.13 250)";

function parseDay(iso: string): Date {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(year, (month || 1) - 1, day || 1);
}

function rangeLabel(start: string, end: string): string {
  const format = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" });
  return `${format.format(parseDay(start))} – ${format.format(parseDay(end))}`;
}

function hoursLabel(seconds: number | null): string {
  if (seconds == null) return "—";
  const total = Math.round(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

function monthTick(iso: string, previous: string | null): string {
  const date = parseDay(iso);
  const month = date.toLocaleDateString("en-US", { month: "short" });
  if (!previous) return `${month} ${date.getFullYear()}`;
  const prior = parseDay(previous);
  if (prior.getFullYear() === date.getFullYear() && prior.getMonth() === date.getMonth()) return "";
  if (prior.getFullYear() !== date.getFullYear()) return `${month} ${date.getFullYear()}`;
  return month;
}

function runTick(local: string | null): string {
  if (!local || local.length < 10) return "Run";
  const date = parseDay(local.slice(0, 10));
  const day = date.toLocaleDateString("en-US", { weekday: "short" });
  const time = local.length >= 16 ? local.slice(11, 16) : "";
  return time ? `${day} ${time}` : `${day} ${date.getDate()}`;
}

export function MileageHistory({ chart }: { chart: MileageChart }) {
  const router = useRouter();
  const [view, setView] = useState<"weeks" | "runs">("weeks");
  const weekPoints = chart.weeks.map((week, index) => ({
    label: monthTick(week.week_start, index === 0 ? null : chart.weeks[index - 1].week_start),
    miles: week.distance_miles ?? 0,
    current: week.current,
    detail: week.activity_count === 1 ? "1 run" : `${week.activity_count} runs`,
    garminId: null as number | null,
  }));
  const runPoints = chart.runs.map((run) => ({
    label: runTick(run.start_time_local),
    miles: run.distance_miles ?? 0,
    current: true,
    detail: run.name || "Activity",
    garminId: run.garmin_activity_id,
  }));
  const points = view === "weeks" ? weekPoints : runPoints;
  const hasMiles = points.some((point) => point.miles > 0);

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-sm font-medium">Activities for {rangeLabel(chart.week_start, chart.week_end)}</p>
          <p className="mt-2 flex flex-wrap gap-x-2 text-lg font-semibold tracking-tight">
            {chart.distance_miles == null ? "—" : `${chart.distance_miles.toFixed(1)} mi`}
            <span className="font-normal text-muted-foreground">|</span>
            {hoursLabel(chart.duration_seconds)}
            <span className="font-normal text-muted-foreground">|</span>
            {chart.elevation_feet == null ? "—" : `${Math.round(chart.elevation_feet)} ft`}
          </p>
        </div>
        <div className="flex w-fit rounded-lg border border-border p-1">
          <button
            type="button"
            aria-pressed={view === "weeks"}
            onClick={() => setView("weeks")}
            className={`rounded-md px-3 py-1.5 text-sm ${view === "weeks" ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted"}`}
          >
            All weeks
          </button>
          <button
            type="button"
            aria-pressed={view === "runs"}
            onClick={() => setView("runs")}
            className={`rounded-md px-3 py-1.5 text-sm ${view === "runs" ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted"}`}
          >
            Runs this week
          </button>
        </div>
      </div>
      {!hasMiles ? (
        <p className="text-sm text-muted-foreground">
          {view === "weeks" ? "Weekly mileage appears after activities with distance are imported." : "No runs with distance are stored for this week."}
        </p>
      ) : (
        <div className="h-64 w-full min-w-0">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={points} barCategoryGap={view === "weeks" ? "20%" : "30%"}>
              <CartesianGrid vertical={false} stroke="oklch(0.88 0.02 80)" />
              <XAxis dataKey="label" tickLine={false} axisLine={false} interval={0} tick={{ fontSize: 11 }} />
              <YAxis tickLine={false} axisLine={false} width={36} domain={[0, "auto"]} tick={{ fontSize: 11 }} />
              <Tooltip
                formatter={(value) => [`${Number(value).toFixed(1)} mi`, "Distance"]}
                labelFormatter={(_label, payload) => {
                  const detail = payload?.[0]?.payload?.detail;
                  return typeof detail === "string" ? detail : "";
                }}
              />
              <Bar
                dataKey="miles"
                radius={[3, 3, 0, 0]}
                cursor={view === "runs" ? "pointer" : undefined}
                onClick={(point) => {
                  const id = (point as { garminId?: number | null }).garminId;
                  if (id) router.push(`/activities/${id}`);
                }}
              >
                {points.map((point, index) => (
                  <Cell key={`${point.garminId ?? "week"}-${index}`} fill={point.current ? CURRENT : PAST} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
