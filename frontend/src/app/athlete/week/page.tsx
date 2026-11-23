"use client";

import { AthleteTrainingPlan } from "@/components/athlete-training-plan";
import { useAthlete } from "@/components/athlete-frame";

export default function AthleteWeekPage() {
  const { athleteId } = useAthlete();
  return (
    <div className="space-y-4">
      <h1 className="font-heading text-2xl tracking-tight sm:text-3xl">Training plan</h1>
      <AthleteTrainingPlan athleteId={athleteId} />
    </div>
  );
}
