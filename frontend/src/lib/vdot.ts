import type { RaceEntry, RunningStats } from "@/lib/api";

const MILE_METERS = 1609.344;
const MIN_DISTANCE_METERS = 1500;
const MIN_DURATION_SECONDS = 210;

const EFFORT_METERS: Record<string, number> = {
  "1 mile": 1609.344,
  "2 mile": 3218.688,
  "5K": 5000,
  "10K": 10000,
  "15K": 15000,
  "10 mile": 16093.44,
  "20K": 20000,
  "Half-Marathon": 21097.5,
  "30K": 30000,
  Marathon: 42195,
};

const RACE_DISTANCES: Array<[string, number]> = [
  ["half marathon", 21097.5],
  ["half-marathon", 21097.5],
  ["marathon", 42195],
  ["10 mile", 16093.44],
  ["10-mile", 16093.44],
  ["15k", 15000],
  ["10k", 10000],
  ["5k", 5000],
  ["1 mile", 1609.344],
  ["mile", 1609.344],
];

const ZONES = [
  { name: "Easy Aerobic", slow: 0.59, fast: 0.74 },
  { name: "Lower Threshold", slow: 0.833, fast: 0.86 },
  { name: "Upper Threshold", slow: 0.873, fast: 0.9 },
];

export type PaceEstimate = {
  vdot: number;
  meters: number;
  seconds: number;
  kind: "race" | "effort";
  zones: Array<{ name: string; range: string }>;
};

function oxygenCost(metersPerMinute: number) {
  return -4.6 + 0.182258 * metersPerMinute + 0.000104 * metersPerMinute ** 2;
}

function sustainableFraction(minutes: number) {
  return 0.8 + 0.1894393 * Math.exp(-0.012778 * minutes) + 0.2989558 * Math.exp(-0.1932605 * minutes);
}

function vdotScore(meters: number, seconds: number) {
  const minutes = seconds / 60;
  const fraction = sustainableFraction(minutes);
  if (fraction <= 0) return null;
  const score = oxygenCost(meters / minutes) / fraction;
  return Number.isFinite(score) && score > 0 ? score : null;
}

function paceSeconds(vdot: number, fraction: number) {
  const target = vdot * fraction;
  const a = 0.000104;
  const b = 0.182258;
  const c = -4.6 - target;
  const velocity = (-b + Math.sqrt(b * b - 4 * a * c)) / (2 * a);
  return MILE_METERS / (velocity / 60);
}

function formatPace(seconds: number) {
  const rounded = Math.round(seconds);
  return `${Math.floor(rounded / 60)}:${String(rounded % 60).padStart(2, "0")}`;
}

function parseClock(value: string | null | undefined) {
  if (!value) return null;
  const text = value.trim();
  if (!/^\d{1,2}(:\d{2}){1,2}$/.test(text)) return null;
  const parts = text.split(":").map(Number);
  if (parts.length === 2) return parts[0] * 60 + parts[1];
  return parts[0] * 3600 + parts[1] * 60 + parts[2];
}

function raceMeters(race: RaceEntry) {
  if (race.distance_meters != null && race.distance_meters > 0) return race.distance_meters;
  const label = (race.distance_label ?? "").trim().toLowerCase();
  if (!label) return null;
  const match = RACE_DISTANCES.find(([name]) => label.includes(name));
  return match?.[1] ?? null;
}

export function formatResultClock(seconds: number) {
  const total = Math.round(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  if (hours > 0) return `${hours}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
  return `${minutes}:${String(secs).padStart(2, "0")}`;
}

export function formatRaceDistance(meters: number) {
  return `${Math.round(meters).toLocaleString("en-US")} m`;
}

export function paceEstimateFromRecords(races: RaceEntry[], efforts: RunningStats["best_efforts"]): PaceEstimate | null {
  const candidates: Array<{ vdot: number; meters: number; seconds: number; kind: "race" | "effort" }> = [];
  for (const race of races) {
    const meters = raceMeters(race);
    const seconds = parseClock(race.result_time);
    if (meters == null || seconds == null || meters < MIN_DISTANCE_METERS || seconds < MIN_DURATION_SECONDS) continue;
    const vdot = vdotScore(meters, seconds);
    if (vdot != null) candidates.push({ vdot, meters, seconds, kind: "race" });
  }
  for (const effort of efforts) {
    const meters = EFFORT_METERS[effort.label];
    const seconds = effort.duration_seconds;
    if (meters == null || seconds == null || meters < MIN_DISTANCE_METERS || seconds < MIN_DURATION_SECONDS) continue;
    const vdot = vdotScore(meters, seconds);
    if (vdot != null) candidates.push({ vdot, meters, seconds, kind: "effort" });
  }
  const best = candidates.reduce<(typeof candidates)[number] | null>((chosen, item) => {
    if (chosen == null || item.vdot > chosen.vdot) return item;
    return chosen;
  }, null);
  if (best == null) return null;
  return {
    vdot: best.vdot,
    meters: best.meters,
    seconds: best.seconds,
    kind: best.kind,
    zones: ZONES.map((zone) => ({
      name: zone.name,
      range: `${formatPace(paceSeconds(best.vdot, zone.fast))}–${formatPace(paceSeconds(best.vdot, zone.slow))}`,
    })),
  };
}
