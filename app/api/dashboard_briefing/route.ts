import { NextRequest, NextResponse } from "next/server"

const FASTAPI_URL = process.env.FASTAPI_URL ?? process.env.BACKEND_URL ?? "http://localhost:8000"

export async function GET(req: NextRequest) {
  try {
    const agentId = req.nextUrl.searchParams.get("agent_id")
    const url = new URL(`${FASTAPI_URL}/api/dashboard_briefing`)
    if (agentId) url.searchParams.set("agent_id", agentId)

    const res = await fetch(url.toString(), { cache: "no-store" })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      return NextResponse.json(
        { error: err?.detail ?? "Failed to fetch dashboard briefing" },
        { status: res.status },
      )
    }
    const data = await res.json()
    return NextResponse.json(data)
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Internal error" },
      { status: 500 },
    )
  }
}

