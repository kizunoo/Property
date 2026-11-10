import { NextRequest, NextResponse } from "next/server"
import { buildAgentUpstreamHeaders } from "@/lib/agent-bff-auth"

const FASTAPI_URL = process.env.FASTAPI_URL || process.env.BACKEND_URL || "http://127.0.0.1:8000"

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> | { id: string } }
) {
  try {
    const resolved = await params
    const id = encodeURIComponent(resolved.id)
    const body = await req.text().catch(() => "{}")
    const upstream = await fetch(`${FASTAPI_URL}/api/quotes/${id}/publish-to-portal`, {
      method: "POST",
      headers: buildAgentUpstreamHeaders(req),
      body: body || "{}",
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

