import { NextResponse, type NextRequest } from "next/server";

export const dynamic = "force-dynamic";

function backendBase() {
  const configured = process.env.BACKEND_URL?.replace(/\/$/, "");
  if (configured) return configured;
  if (process.env.NETLIFY) return null;
  return "http://127.0.0.1:8000";
}

function unavailable() {
  return NextResponse.json(
    {
      status: "unavailable",
      created_at: null,
      report: null,
    },
    { headers: { "cache-control": "no-store" } },
  );
}

async function proxy(request: NextRequest) {
  const base = backendBase();
  if (!base) return unavailable();
  try {
    const response = await fetch(`${base}/api/coach/brief${new URL(request.url).search}`, {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: await request.text(),
      cache: "no-store",
      signal: AbortSignal.timeout(60000),
    });
    return new NextResponse(await response.text(), {
      status: response.status,
      headers: {
        "content-type": response.headers.get("content-type") ?? "application/json",
        "cache-control": "no-store",
      },
    });
  } catch {
    return unavailable();
  }
}

export function GET() {
  return unavailable();
}

export function POST(request: NextRequest) {
  return proxy(request);
}
