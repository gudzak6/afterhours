import { PlanUpload } from "@/components/plan-upload";

export default function PlanPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-heading text-2xl tracking-tight sm:text-3xl">Plans</h1>
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
          Choose one way to write a plan for an athlete. The athlete sees the resulting workouts on their own plan.
        </p>
      </div>
      <PlanUpload />
    </div>
  );
}
