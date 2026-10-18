import { buildAgentUpstreamHeaders } from "@/lib/agent-bff-auth"
import { NextRequest, NextResponse } from "next/server"

export const maxDuration = 30

const FASTAPI_URL = process.env.FASTAPI_URL ?? process.env.BACKEND_URL ?? "http://localhost:8000"

export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url)
    const agentId = searchParams.get("agent_id")
    const url = new URL(`${FASTAPI_URL}/api/pipeline_projection`)
    if (agentId && agentId !== "all" && agentId !== "null" && agentId !== "undefined") {
      url.searchParams.set("agent_id", agentId)
    }

    const res = await fetch(url.toString(), {
      cache: "no-store",
      headers: buildAgentUpstreamHeaders(req),
    })

    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      return NextResponse.json(
        { error: err?.detail ?? "Failed to fetch pipeline projection" },
        { status: res.status },
      )
    }

    const data = await res.json()
    return NextResponse.json(data)
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Internal error connecting to projection engine" },
      { status: 502 },
    )
  }
}
