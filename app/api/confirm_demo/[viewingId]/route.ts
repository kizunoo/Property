import { buildAgentUpstreamHeaders } from "@/lib/agent-bff-auth"
import { NextRequest, NextResponse } from "next/server"

const FASTAPI_URL = process.env.FASTAPI_URL ?? "http://127.0.0.1:8000"

export async function PATCH(
  req: NextRequest,
  { params }: { params: Promise<{ viewingId: string }> }
) {
  const { viewingId } = await params
  try {
    const upstream = await fetch(`${FASTAPI_URL}/api/confirm_demo/${viewingId}`, {
      method: "PATCH",
      headers: buildAgentUpstreamHeaders(req),
    })
    const data = await upstream.json()
    if (!upstream.ok) {
      return NextResponse.json(
        { error: data?.detail ?? "Failed to confirm demo" },
        { status: upstream.status }
      )
    }
    return NextResponse.json(data)
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Internal error" },
      { status: 500 }
    )
  }
}
