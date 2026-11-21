import { Suspense } from "react";
import AthleteView from "./athlete-view";

export default function AthletePage() {
  return (
    <Suspense fallback={<p className="text-sm text-muted-foreground">Loading athlete…</p>}>
      <AthleteView />
    </Suspense>
  );
}
