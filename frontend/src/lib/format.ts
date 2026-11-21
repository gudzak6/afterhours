import type { Activity } from "@/lib/api";

export function hasField(activity: Activity, field: string): boolean {
  return activity.present_fields.includes(field);
}

export function formatWhen(local: string | null, utc: string | null): string {
  if (local) {
    const [date, time] = local.split(" ");
    if (date && time) {
      return `${date} · ${time.slice(0, 5)}`;
    }
    return local;
  }
  if (!utc) {
    return "—";
  }
  const parsed = new Date(utc);
  if (Number.isNaN(parsed.getTime())) {
    return utc;
  }
  return parsed.toLocaleString();
}

export function formatMiles(miles: number | null, present: boolean): string {
  if (!present || miles == null) {
    return "—";
  }
  return `${miles.toFixed(2)} mi`;
}

export function formatDuration(seconds: number | null, present: boolean): string {
  if (!present || seconds == null) {
    return "—";
  }
  const total = Math.round(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const remainder = total % 60;
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
  }
  return `${minutes}:${String(remainder).padStart(2, "0")}`;
}

export function formatPace(secondsPerMile: number | null, speedPresent: boolean): string {
  if (!speedPresent) {
    return "—";
  }
  if (secondsPerMile == null) {
    return "No pace";
  }
  const rounded = Math.round(secondsPerMile);
  const minutes = Math.floor(rounded / 60);
  const seconds = rounded % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")} /mi`;
}

export function formatHeartRate(bpm: number | null, present: boolean): string {
  if (!present || bpm == null) {
    return "—";
  }
  return `${Math.round(bpm)} bpm`;
}

export function formatNumber(value: number | null, present: boolean, suffix = ""): string {
  if (!present || value == null) {
    return "—";
  }
  const rendered = Number.isInteger(value) ? String(value) : value.toFixed(1);
  return suffix ? `${rendered} ${suffix}` : rendered;
}

export function formatActivityType(value: string | null): string {
  if (!value) {
    return "Unknown";
  }
  return value.replaceAll("_", " ");
}

export function formatSyncTime(value: string | null): string {
  if (!value) {
    return "No sync yet";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString();
}
