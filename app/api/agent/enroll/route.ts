import { buildAgentUpstreamHeaders } from "@/lib/agent-bff-auth"
import { NextRequest, NextResponse } from "next/server"

const FASTAPI_URL = process.env.FASTAPI_URL ?? process.env.NEXT_PUBLIC_FASTAPI_URL ?? "http://127.0.0.1:8000"

export async function POST(req: NextRequest) {
  try {
    const body = await req.json()
    const res = await fetch(`${FASTAPI_URL}/api/agent/enroll`, {
      method: "POST",
      headers: buildAgentUpstreamHeaders(req),
      body: JSON.stringify(body),
    })

    const data = await res.json()
    return NextResponse.json(data, { status: res.status })
  } catch {
    return NextResponse.json({ detail: "Internal error processing enrollment" }, { status: 500 })
  }
}
