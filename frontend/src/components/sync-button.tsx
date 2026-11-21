"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { errorMessage, syncGarmin, type SyncJob } from "@/lib/api";

export function SyncButton({ onSynced }: { onSynced: (job: SyncJob) => void }) {
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  async function onClick() {
    setPending(true);
    setMessage(null);
    setFailed(false);
    try {
      const job = await syncGarmin();
      setMessage(
        `Imported ${job.activities_imported}, updated ${job.activities_updated}, skipped ${job.activities_skipped}.`,
      );
      onSynced(job);
    } catch (error) {
      setFailed(true);
      setMessage(errorMessage(error));
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="flex flex-col items-start gap-2">
      <Button type="button" size="lg" onClick={onClick} disabled={pending}>
        {pending ? "Syncing Garmin…" : "Sync from Garmin"}
      </Button>
      {message ? (
        <p className={failed ? "max-w-xl text-sm text-destructive" : "max-w-xl text-sm text-muted-foreground"}>
          {message}
        </p>
      ) : null}
    </div>
  );
}
