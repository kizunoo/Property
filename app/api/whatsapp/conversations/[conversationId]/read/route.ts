import { buildAgentUpstreamHeaders } from "@/lib/agent-bff-auth"
import { NextRequest, NextResponse } from "next/server"

export const maxDuration = 15
const FASTAPI_URL = process.env.FASTAPI_URL ?? process.env.BACKEND_URL ?? "http://localhost:8000"

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ conversationId: string }> }
) {
  try {
    const { conversationId } = await params
    const upstream = await fetch(
      `${FASTAPI_URL}/api/whatsapp/conversations/${encodeURIComponent(conversationId)}/read`,
      {
        method: "POST",
        headers: buildAgentUpstreamHeaders(req),
      }
    )
    const data = await upstream.json().catch(() => ({ success: false }))
    return NextResponse.json(data, { status: upstream.status })
  } catch (err: any) {
    return NextResponse.json({ success: false, error: String(err) }, { status: 500 })
  }
}
