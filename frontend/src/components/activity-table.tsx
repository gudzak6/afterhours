"use client";

import Link from "next/link";
import { AthleteName } from "@/components/athlete-name";
import { Badge } from "@/components/ui/badge";
import type { Activity } from "@/lib/api";
import {
  formatActivityType,
  formatMiles,
  formatPace,
  formatWhen,
  hasField,
} from "@/lib/format";

export function ActivityTable({ activities }: { activities: Activity[] }) {
  if (activities.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-border px-4 py-10 text-center text-sm text-muted-foreground">
        No activities stored for the roster.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[760px] text-left text-sm">
        <thead className="text-xs tracking-wide text-muted-foreground uppercase">
          <tr className="border-b border-border">
            <th className="px-3 py-2 font-medium">Date</th>
            <th className="px-3 py-2 font-medium">Athlete</th>
            <th className="px-3 py-2 font-medium">Activity</th>
            <th className="px-3 py-2 font-medium">Distance</th>
            <th className="px-3 py-2 font-medium">Pace</th>
            <th className="px-3 py-2 font-medium">Workout</th>
            <th className="px-3 py-2 font-medium">Analysis</th>
          </tr>
        </thead>
        <tbody>
          {activities.map((activity) => (
            <tr key={activity.garmin_activity_id} className="border-b border-border/70 last:border-0">
              <td className="px-3 py-3 whitespace-nowrap">
                {formatWhen(activity.start_time_local, activity.start_time_utc)}
              </td>
              <td className="px-3 py-3 whitespace-nowrap">
                {activity.athlete_id ? (
                  <Link href={`/athletes/${activity.athlete_id}`} className="hover:underline">
                    <AthleteName name={activity.athlete_name || "Athlete"} />
                  </Link>
                ) : (
                  activity.athlete_name ? <AthleteName name={activity.athlete_name} /> : "—"
                )}
              </td>
              <td className="px-3 py-3">
                <Link href={`/activities/${activity.garmin_activity_id}`} className="font-medium hover:underline">
                  {activity.name || "Untitled activity"}
                </Link>
                <div className="text-xs text-muted-foreground capitalize">
                  {formatActivityType(activity.activity_type_key)}
                </div>
              </td>
              <td className="px-3 py-3 whitespace-nowrap">
                {formatMiles(activity.distance_miles, hasField(activity, "distance_meters"))}
              </td>
              <td className="px-3 py-3 whitespace-nowrap">
                {formatPace(activity.average_pace_seconds_per_mile, hasField(activity, "average_speed_mps"))}
              </td>
              <td className="px-3 py-3">
                <Badge variant="outline">{formatActivityType(activity.workout_type || "not classified")}</Badge>
              </td>
              <td className="px-3 py-3">
                <Badge variant="secondary">{formatActivityType(activity.analysis_status)}</Badge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
