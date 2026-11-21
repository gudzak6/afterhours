import { PlanUpload } from "@/components/plan-upload";

export default function PlanPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-heading text-4xl tracking-tight">Plan</h1>
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
          Upload a training plan for one athlete on the roster. The athlete sees the resulting workouts on their own plan.
        </p>
      </div>
      <PlanUpload />
    </div>
  );
}
