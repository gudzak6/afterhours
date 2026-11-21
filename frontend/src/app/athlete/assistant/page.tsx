"use client";

import { FormEvent, useState } from "react";
import { useAthlete } from "@/components/athlete-frame";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { askAthleteAssistant, errorMessage, type ChatMessage } from "@/lib/api";

const PROMPTS = [
  "How did my training go this week?",
  "How did I execute my latest workout?",
  "How are my pace, heart rate, and training load changing?",
  "How am I progressing toward my race goal?",
];

export default function AthleteAssistantPage() {
  const { athleteId, status } = useAthlete();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function ask(text: string) {
    const message = text.trim();
    if (!message || pending) return;
    setPending(message);
    setDraft("");
    setError(null);
    try {
      const response = await askAthleteAssistant(athleteId, message, conversationId);
      setConversationId(response.conversation_id);
      setMessages(response.messages);
    } catch (askError) {
      setDraft(message);
      setError(errorMessage(askError));
    } finally {
      setPending(null);
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="font-heading text-2xl tracking-tight sm:text-3xl">Assistant</h1>
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
          Questions are answered from your stored training and Coach Owen’s plan.
          {status.openai_configured ? "" : " The written assistant needs an OpenAI key on the server. The rest of your training is still available."}
        </p>
      </div>
      <div className="flex flex-wrap gap-2">
        {PROMPTS.map((prompt) => (
          <button key={prompt} type="button" onClick={() => void ask(prompt)} className="rounded-full border border-border px-3 py-1 text-left text-sm hover:bg-muted">
            {prompt}
          </button>
        ))}
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Training Q&A</CardTitle>
          <CardDescription>The assistant does not change your plan.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {error ? <p className="text-sm text-destructive">{error}</p> : null}
          <div className="space-y-3">
            {messages.map((message) => (
              <div key={message.id} className={message.role === "user" ? "ml-auto max-w-[85%]" : "mr-auto max-w-[85%]"}>
                <div className={`rounded-2xl px-3 py-2 text-sm ${message.role === "user" ? "bg-primary text-primary-foreground" : "bg-muted"}`}>
                  <p className="whitespace-pre-wrap">{message.content}</p>
                </div>
              </div>
            ))}
            {pending ? <p className="text-sm text-muted-foreground">Looking at your training…</p> : null}
          </div>
          <form
            onSubmit={(event: FormEvent) => {
              event.preventDefault();
              void ask(draft);
            }}
            className="space-y-2"
          >
            <textarea value={draft} onChange={(event) => setDraft(event.target.value)} className="min-h-24 w-full rounded-lg border border-input bg-card px-3 py-2 text-sm" placeholder="Ask about a workout, the week, or your goal" />
            <Button type="submit" disabled={pending !== null}>Ask</Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
