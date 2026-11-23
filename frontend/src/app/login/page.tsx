"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { LoginForm } from "@/components/login-form";

function LoginScreen() {
  const signup = useSearchParams().get("signup") === "1";
  return <LoginForm initialMode={signup ? "create" : "sign-in"} />;
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginScreen />
    </Suspense>
  );
}
