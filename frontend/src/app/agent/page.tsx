import { Suspense } from "react";
import { CoachChat } from "@/components/coach-chat";

export default function AgentPage() {
  return (
    <Suspense fallback={<p className="text-sm text-muted-foreground">Loading the agent.</p>}>
      <CoachChat />
    </Suspense>
  );
}
