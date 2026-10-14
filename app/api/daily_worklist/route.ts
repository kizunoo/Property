import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function GET(req: Request) {
  try {
    const url = new URL(req.url);
    const forceRefresh = url.searchParams.get("force_refresh") === "true";
    const agentId = url.searchParams.get("agent_id");

    const backendUrl = new URL(`${BACKEND_URL}/api/daily_worklist`);
    if (forceRefresh) backendUrl.searchParams.set("force_refresh", "true");
    if (agentId) backendUrl.searchParams.set("agent_id", agentId);

    const res = await fetch(backendUrl.toString(), { cache: "no-store" });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      return NextResponse.json(err, { status: res.status });
    }
    return NextResponse.json(await res.json());
  } catch (err) {
    return NextResponse.json({ detail: String(err) }, { status: 502 });
  }
}

