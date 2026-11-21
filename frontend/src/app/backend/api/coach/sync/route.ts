import { NextResponse, type NextRequest } from "next/server";

export const dynamic = "force-dynamic";

function backendBase() {
  const configured = process.env.BACKEND_URL?.replace(/\/$/, "");
  if (configured) return configured;
  if (process.env.NETLIFY) return null;
  return "http://127.0.0.1:8000";
}

export async function POST(request: NextRequest) {
  const base = backendBase();
  if (base) {
    try {
      const response = await fetch(`${base}/api/coach/sync`, {
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
      // The coaching server is not reachable. Fall through to a JSON reply.
    }
  }

  return NextResponse.json(
    {
      synced: 0,
      imported: 0,
      updated: 0,
      errors: ["Garmin sync runs on the coaching server. This site shows runs already saved to the account."],
    },
    { headers: { "cache-control": "no-store" } },
  );
}
