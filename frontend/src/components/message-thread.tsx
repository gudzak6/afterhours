"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { areaClass } from "@/components/athlete-ui";
import { errorMessage, getMessages, sendMessage, type WorkoutNote } from "@/lib/api";

export function MessageThread({ athleteId, author }: { athleteId: number; author: "athlete" | "coach" }) {
  const [messages, setMessages] = useState<WorkoutNote[]>([]);
  const [body, setBody] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  const load = useCallback(async () => {
    const response = await getMessages(athleteId);
    setMessages(response.messages);
  }, [athleteId]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void load().catch((loadError: unknown) => setError(errorMessage(loadError)));
    }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setSending(true);
    setError(null);
    try {
      const sent = await sendMessage(athleteId, author, body);
      setBody("");
      setMessages((current) => [...current, sent]);
    } catch (sendError) {
      setError(errorMessage(sendError));
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="space-y-3">
      {messages.length === 0 ? <p className="text-sm text-muted-foreground">No messages yet.</p> : null}
      <ul className="space-y-2">
        {messages.map((message) => {
          const mine = message.author === author;
          return (
            <li key={message.id} className={mine ? "ml-auto max-w-[85%]" : "mr-auto max-w-[85%]"}>
              <div className={`rounded-2xl px-3 py-2 text-sm ${mine ? "bg-primary text-primary-foreground" : "bg-muted"}`}>
                <p className="text-[11px] tracking-wide uppercase opacity-70">{message.author}</p>
                <p className="mt-1 whitespace-pre-wrap">{message.body}</p>
              </div>
            </li>
          );
        })}
      </ul>
      <form onSubmit={(event) => void onSubmit(event)} className="space-y-2">
        <textarea value={body} onChange={(event) => setBody(event.target.value)} className={areaClass} placeholder="Write a message" />
        <Button type="submit" disabled={sending}>{sending ? "Sending…" : "Send"}</Button>
        {error ? <p className="text-sm text-destructive">{error}</p> : null}
      </form>
    </div>
  );
}
