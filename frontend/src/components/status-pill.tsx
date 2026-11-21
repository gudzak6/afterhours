import { cn } from "cn";

const LABELS: Record<string, string> = {
  attention: "Needs attention",
  on_track: "On track",
  building: "Building",
  no_data: "No activities",
  steady: "Steady",
  completed: "Completed",
  missed: "Missed",
  planned: "Planned",
  scheduled: "Scheduled",
  partially_completed: "Partial",
  unmatched: "Unmatched",
  confirmed_missed: "Confirmed missed",
  connected: "Garmin connected",
  not_connected: "Garmin not connected",
};

const TONES: Record<string, string> = {
  attention: "bg-red-50 text-red-900 border-red-200",
  missed: "bg-red-50 text-red-900 border-red-200",
  on_track: "bg-emerald-50 text-emerald-900 border-emerald-200",
  completed: "bg-emerald-50 text-emerald-900 border-emerald-200",
  connected: "bg-emerald-50 text-emerald-900 border-emerald-200",
  building: "bg-amber-50 text-amber-950 border-amber-200",
  planned: "bg-amber-50 text-amber-950 border-amber-200",
  scheduled: "bg-amber-50 text-amber-950 border-amber-200",
  partially_completed: "bg-amber-50 text-amber-950 border-amber-200",
  unmatched: "border-border text-muted-foreground",
  confirmed_missed: "bg-red-50 text-red-900 border-red-200",
};

export function StatusPill({ status }: { status: string }) {
  return (
    <span className={cn("inline-flex rounded-full border px-2 py-0.5 text-xs", TONES[status] ?? "border-border text-muted-foreground")}>
      {LABELS[status] ?? status.replaceAll("_", " ")}
    </span>
  );
}
