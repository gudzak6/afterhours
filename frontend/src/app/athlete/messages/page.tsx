"use client";

import { useAthlete } from "@/components/athlete-frame";
import { MessageThread } from "@/components/message-thread";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default function AthleteMessagesPage() {
  const { athleteId } = useAthlete();
  return (
    <div className="space-y-4">
      <div>
        <h1 className="font-heading text-4xl tracking-tight">Coach Owen</h1>
        <p className="mt-2 text-sm text-muted-foreground">Messages with Coach Owen. Notes on a single workout stay on that workout.</p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Messages</CardTitle>
          <CardDescription>Coach Owen sees this thread on your athlete page.</CardDescription>
        </CardHeader>
        <CardContent>
          <MessageThread athleteId={athleteId} author="athlete" />
        </CardContent>
      </Card>
    </div>
  );
}
