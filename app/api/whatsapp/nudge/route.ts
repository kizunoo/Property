import { buildAgentUpstreamHeaders } from "@/lib/agent-bff-auth"
import { NextRequest, NextResponse } from "next/server"

export const maxDuration = 15
const FASTAPI_URL = process.env.FASTAPI_URL ?? process.env.BACKEND_URL ?? "http://localhost:8000"

export async function POST(req: NextRequest) {
  try {
    const body = await req.json()
    const upstream = await fetch(`${FASTAPI_URL}/api/whatsapp/nudge`, {
      method: "POST",
      headers: buildAgentUpstreamHeaders(req),
      body: JSON.stringify(body),
    })
    const data = await upstream.json().catch(() => ({ success: false }))
    return NextResponse.json(data, { status: upstream.status })
  } catch (err: any) {
    return NextResponse.json({ success: false, error: String(err) }, { status: 500 })
  }
}
