import { NextResponse, type NextRequest } from "next/server";
import { cookies } from "next/headers";
import { loadAccountDashboard } from "@/lib/account-dashboard";
import { createClient } from "@/utils/supabase/server";

export const dynamic = "force-dynamic";

function backendBase() {
  const configured = process.env.BACKEND_URL?.replace(/\/$/, "");
  if (configured) return configured;
  if (process.env.NETLIFY) return null;
  return "http://127.0.0.1:8000";
}

async function proxyCoachingApi(request: NextRequest) {
  const base = backendBase();
  if (!base) return null;
  const url = new URL(request.url);
  try {
    const response = await fetch(`${base}/api/coach/dashboard${url.search}`, {
      headers: { Accept: "application/json" },
      cache: "no-store",
      signal: AbortSignal.timeout(8000),
    });
    return new NextResponse(await response.text(), {
      status: response.status,
      headers: {
        "content-type": response.headers.get("content-type") ?? "application/json",
        "cache-control": "no-store",
      },
    });
  } catch {
    return null;
  }
}

export async function GET(request: NextRequest) {
  const proxied = await proxyCoachingApi(request);
  if (proxied) return proxied;

  if (!process.env.NEXT_PUBLIC_SUPABASE_URL || !process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY) {
    return NextResponse.json(
      { detail: { message: "The coaching API is not running, and the account database is not configured." } },
      { status: 503 },
    );
  }

  try {
    const day = new URL(request.url).searchParams.get("day");
    const dashboard = await loadAccountDashboard(createClient(await cookies()), day);
    return NextResponse.json(dashboard, { headers: { "cache-control": "no-store" } });
  } catch (error) {
    const message = error instanceof Error ? error.message : "The roster could not be loaded.";
    return NextResponse.json({ detail: { message } }, { status: 503 });
  }
}
