import { buildAgentUpstreamHeaders } from "@/lib/agent-bff-auth"
import { NextResponse } from "next/server"

export const maxDuration = 15

const FASTAPI_URL = process.env.FASTAPI_URL ?? "http://127.0.0.1:8000"

export async function GET(req: Request) {
  try {
    const upstream = await fetch(`${FASTAPI_URL}/api/scheduled_viewings`, { cache: "no-store", headers: buildAgentUpstreamHeaders(req) })
    const data = await upstream.json()
    if (!upstream.ok) {
      return NextResponse.json({ error: data?.detail ?? "Failed to fetch viewings" }, { status: upstream.status })
    }
    return NextResponse.json(data)
  } catch (err) {
    return NextResponse.json({ error: err instanceof Error ? err.message : "Internal error" }, { status: 500 })
  }
}
