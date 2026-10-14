import { buildAgentUpstreamHeaders } from "@/lib/agent-bff-auth"
import { NextRequest, NextResponse } from "next/server"

export const maxDuration = 15

const FASTAPI_URL = process.env.FASTAPI_URL ?? process.env.BACKEND_URL ?? "http://localhost:8000"

export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url)
    const upstream = await fetch(`${FASTAPI_URL}/api/whatsapp/window_status?${searchParams.toString()}`, { headers: buildAgentUpstreamHeaders(req) })
    const data = await upstream.json().catch(() => ({}))
    return NextResponse.json(data, { status: upstream.status })
  } catch (err: any) {
    return NextResponse.json(
      { error: err?.message ?? "Failed to check window status" },
      { status: 500 },
    )
  }
}
