import { NextRequest, NextResponse } from "next/server"
import { buildAgentUpstreamHeaders } from "@/lib/agent-bff-auth"

const FASTAPI_URL = process.env.FASTAPI_URL || process.env.BACKEND_URL || "http://127.0.0.1:8000"

export async function POST(req: NextRequest) {
  try {
    const body = await req.text()
    const upstream = await fetch(`${FASTAPI_URL}/api/quotes/request`, {
      method: "POST",
      headers: buildAgentUpstreamHeaders(req),
      body,
      cache: "no-store",
    })
    const data = await upstream.text()
    return new NextResponse(data, {
      status: upstream.status,
      headers: { "Content-Type": upstream.headers.get("content-type") || "application/json" },
    })
  } catch (err: any) {
    return NextResponse.json({ error: "BFF upstream error", detail: err?.message }, { status: 502 })
  }
}

