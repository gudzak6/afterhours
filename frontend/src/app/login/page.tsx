"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { accountEmail, prepareAccount, signIn, signOut, signUp } from "@/lib/account";
import { errorMessage } from "@/lib/api";

const fieldClass = "mt-1 h-9 w-full rounded-lg border border-input bg-card px-3 text-sm";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"sign-in" | "create">("sign-in");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [current, setCurrent] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void accountEmail().then(setCurrent).catch((loadError: unknown) => setError(errorMessage(loadError)));
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setNotice(null);
    setPending(true);
    try {
      if (mode === "create") {
        const signedIn = await signUp(email.trim(), password, name.trim() || email.trim());
        if (!signedIn) {
          setNotice("Check your email to confirm the account, then sign in.");
          setMode("sign-in");
          return;
        }
      } else {
        await signIn(email.trim(), password);
      }
      await prepareAccount();
      router.push("/athlete");
      router.refresh();
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : errorMessage(submitError));
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="mx-auto max-w-md">
      <Card>
        <CardHeader>
          <CardTitle>{mode === "create" ? "Create your athlete account" : "Sign in"}</CardTitle>
          <CardDescription>
            This account is for the athlete. Your runs, goals, and plan stay with you.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {current ? (
            <div className="space-y-3 text-sm">
              <p>Signed in as {current}.</p>
              <Button
                type="button"
                variant="outline"
                onClick={() => void signOut().then(() => {
                  setCurrent(null);
                  setNotice("Signed out.");
                })}
              >
                Sign out
              </Button>
            </div>
          ) : (
            <form onSubmit={(event) => void onSubmit(event)} className="space-y-3">
              {mode === "create" ? (
                <label className="block text-sm">
                  Name
                  <input value={name} onChange={(event) => setName(event.target.value)} className={fieldClass} />
                </label>
              ) : null}
              <label className="block text-sm">
                Email
                <input type="email" required value={email} onChange={(event) => setEmail(event.target.value)} className={fieldClass} />
              </label>
              <label className="block text-sm">
                Password
                <input type="password" required minLength={6} value={password} onChange={(event) => setPassword(event.target.value)} className={fieldClass} />
              </label>
              {error ? <p className="text-sm text-destructive">{error}</p> : null}
              {notice ? <p className="text-sm">{notice}</p> : null}
              <Button type="submit" disabled={pending}>{pending ? "Saving…" : mode === "create" ? "Create account" : "Sign in"}</Button>
            </form>
          )}
          <p className="mt-4 text-sm text-muted-foreground">
            {mode === "create" ? "Already have an account?" : "Need an account?"}{" "}
            <button type="button" className="underline" onClick={() => setMode(mode === "create" ? "sign-in" : "create")}>
              {mode === "create" ? "Sign in" : "Create one"}
            </button>
          </p>
          <p className="mt-2 text-sm">
            <Link href="/athlete" className="underline">Back to your training</Link>
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
