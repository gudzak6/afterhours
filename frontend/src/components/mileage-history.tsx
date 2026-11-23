"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
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

function weekRange(start: string, end: string): string {
  const startDate = parseDay(start);
  const endDate = parseDay(end);
  const monthDay = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" });
  if (startDate.getFullYear() === endDate.getFullYear() && startDate.getMonth() === endDate.getMonth()) {
    return `${monthDay.format(startDate)} – ${endDate.getDate()}`;
  }
  return `${monthDay.format(startDate)} – ${monthDay.format(endDate)}`;
}

function weekTick(iso: string): string {
  return parseDay(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function labelStep(count: number, width: number): number {
  const room = width > 0 ? width : 360;
  const fit = Math.max(1, Math.floor(room / 40));
  return Math.max(1, Math.ceil(count / fit));
}

function runTick(local: string | null): string {
  if (!local || local.length < 10) return "Run";
  const date = parseDay(local.slice(0, 10));
  const day = date.toLocaleDateString("en-US", { weekday: "short" });
  const time = local.length >= 16 ? local.slice(11, 16) : "";
  return time ? `${day} ${time}` : `${day} ${date.getDate()}`;
}

export function MileageHistory({ chart, athleteId }: { chart: MileageChart; athleteId?: number | null }) {
  const router = useRouter();
  const chartFrame = useRef<HTMLDivElement>(null);
  const [view, setView] = useState<"weeks" | "runs">("weeks");
  const [chartWidth, setChartWidth] = useState(0);
  useEffect(() => {
    const node = chartFrame.current;
    if (!node) return;
    const update = () => setChartWidth(node.clientWidth);
    update();
    const observer = new ResizeObserver(update);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  const step = labelStep(chart.weeks.length, chartWidth);
  const weekPoints = chart.weeks.map((week, index) => ({
    id: week.week_start,
    label: index % step === 0 || week.current ? weekTick(week.week_start) : "",
    range: weekRange(week.week_start, week.week_end),
    miles: week.distance_miles ?? 0,
    current: week.current,
    detail: week.activity_count === 1 ? "1 run" : `${week.activity_count} runs`,
    garminId: null as number | null,
  }));
  const runPoints = chart.runs.map((run) => ({
    id: `run-${run.garmin_activity_id}`,
    label: runTick(run.start_time_local),
    range: runTick(run.start_time_local),
    miles: run.distance_miles ?? 0,
    current: true,
    detail: run.name || "Activity",
    garminId: run.garmin_activity_id,
  }));
  const points = view === "weeks" ? weekPoints : runPoints;
  const hasMiles = points.some((point) => point.miles > 0);

  return (
    <div ref={chartFrame} className="space-y-4">
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
              <XAxis
                dataKey="id"
                tickLine={false}
                axisLine={false}
                interval={0}
                height={view === "weeks" ? 52 : 30}
                tick={(tick) => {
                  const label = points[tick.index]?.label ?? "";
                  if (!label) return <g />;
                  if (view === "runs") {
                    return (
                      <text x={tick.x} y={tick.y} dy={12} textAnchor="middle" fontSize={11} fill="currentColor">
                        {label}
                      </text>
                    );
                  }
                  const y = Number(tick.y) + 8;
                  return (
                    <text x={tick.x} y={y} textAnchor="end" fontSize={10} fill="currentColor" transform={`rotate(-40 ${tick.x} ${y})`}>
                      {label}
                    </text>
                  );
                }}
              />
              <YAxis tickLine={false} axisLine={false} width={36} domain={[0, "auto"]} tick={{ fontSize: 11 }} />
              <Tooltip
                content={({ active, payload }) => {
                  const point = payload?.[0]?.payload as { detail?: string; miles?: number; range?: string } | undefined;
                  if (!active || !point || typeof point.miles !== "number") return null;
                  return (
                    <div className="rounded-md border border-border bg-card px-3 py-2 text-sm shadow-sm">
                      {point.range ? <p className="font-medium">{point.range}</p> : null}
                      <p>{point.detail}</p>
                      <p>Distance: {point.miles.toFixed(1)} mi</p>
                    </div>
                  );
                }}
              />
              <Bar
                dataKey="miles"
                radius={[3, 3, 0, 0]}
                cursor={view === "runs" ? "pointer" : undefined}
                onClick={(point) => {
                  const id = (point as { garminId?: number | null }).garminId;
                  if (id) router.push(athleteId == null ? `/activities/${id}` : `/activities/${id}?athlete=${athleteId}`);
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
