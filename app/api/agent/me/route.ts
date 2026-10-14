import { NextRequest, NextResponse } from "next/server"
import { buildAgentUpstreamHeaders } from "@/lib/agent-bff-auth"

const FASTAPI_URL = process.env.NEXT_PUBLIC_FASTAPI_URL ?? "http://127.0.0.1:8000"

export async function GET(req: NextRequest) {
  try {
    const headers = buildAgentUpstreamHeaders(req)
    const res = await fetch(`${FASTAPI_URL}/api/agent/me`, {
      method: "GET",
      headers,
    })
    const data = await res.json()
    return NextResponse.json(data, { status: res.status })
  } catch {
    return NextResponse.json({ detail: "Error fetching agent profile" }, { status: 500 })
  }
}
