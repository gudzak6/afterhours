"use client";

import { FormEvent, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { errorMessage, sendChat, type ChatMessage } from "@/lib/api";

const questions = [
  "Who is on the roster, and how has training looked lately?",
  "Summarize the latest runs and any saved analyses.",
  "What should I pay attention to this week?",
  "How does recent mileage compare with the last month?",
];

export function CoachChat() {
  const params = useSearchParams();
  const activityParam = params.get("activity");
  const activityId = activityParam ? Number(activityParam) : null;
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [pending, setPending] = useState<string | null>(null);

  async function submit(text: string) {
    const message = text.trim();
    if (!message || sending) {
      return;
    }
    setSending(true);
    setPending(message);
    setDraft("");
    setError(null);
    try {
      const response = await sendChat(
        message,
        conversationId,
        activityId != null && Number.isInteger(activityId) ? activityId : null,
      );
      setConversationId(response.conversation_id);
      setMessages(response.messages);
    } catch (sendError) {
      setError(errorMessage(sendError));
      setDraft(message);
    } finally {
      setPending(null);
      setSending(false);
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    void submit(draft);
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-heading text-4xl tracking-tight">AI agent</h1>
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
          Ask about the roster, a workout, or what to do next. Answers use the stored training history, plans, and analyses. A chat reply stays as advice.
          {activityId ? ` This conversation is attached to Garmin activity ${activityId}.` : ""}
        </p>
      </div>
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      <Card>
        <CardHeader>
          <CardTitle>Conversation</CardTitle>
          <CardDescription>The agent reads the saved roster before it quotes a workout or gives advice.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {messages.length === 0 && !pending ? (
            <ul className="space-y-2 text-sm">
              {questions.map((question) => (
                <li key={question}>
                  <button
                    type="button"
                    className="w-full rounded-lg bg-muted px-3 py-2 text-left text-muted-foreground hover:text-foreground"
                    onClick={() => void submit(question)}
                    disabled={sending}
                  >
                    {question}
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <div className="max-h-[32rem] space-y-3 overflow-y-auto">
              {messages.map((message) => {
                const mine = message.role === "user";
                return (
                  <div key={message.id} className={mine ? "ml-auto max-w-[85%]" : "mr-auto max-w-[85%]"}>
                    <div className={`rounded-lg px-3 py-2 text-sm ${mine ? "bg-primary text-primary-foreground" : "bg-muted"}`}>
                      <p className={`text-xs tracking-wide uppercase ${mine ? "text-primary-foreground/80" : "text-muted-foreground"}`}>
                        {mine ? "You" : "Agent"}
                      </p>
                      <p className="mt-1 whitespace-pre-wrap">{message.content}</p>
                    </div>
                  </div>
                );
              })}
              {pending ? (
                <div className="ml-auto max-w-[85%] rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground">
                  <p className="text-xs tracking-wide text-primary-foreground/80 uppercase">You</p>
                  <p className="mt-1 whitespace-pre-wrap">{pending}</p>
                </div>
              ) : null}
              {sending ? <p className="text-sm text-muted-foreground">Looking through the stored training…</p> : null}
            </div>
          )}
          <form className="flex flex-col gap-2 sm:flex-row" onSubmit={onSubmit}>
            <input
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              className="h-9 flex-1 rounded-lg border border-input bg-card px-3 text-sm"
              placeholder="Ask about an athlete, a workout, or what to do next"
              disabled={sending}
            />
            <Button type="submit" disabled={sending || !draft.trim()}>
              {sending ? "Sending…" : "Send"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
