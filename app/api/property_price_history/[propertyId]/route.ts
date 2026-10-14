import { buildAgentUpstreamHeaders } from "@/lib/agent-bff-auth"
import { NextRequest, NextResponse } from "next/server"

export const maxDuration = 15

const FASTAPI_URL = process.env.FASTAPI_URL ?? process.env.BACKEND_URL ?? "http://localhost:8000"

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ propertyId: string }> }
) {
  const { propertyId } = await params
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 10_000)

  try {
    const upstream = await fetch(
      `${FASTAPI_URL}/api/property_price_history/${encodeURIComponent(propertyId)}`,
      {
        signal: controller.signal,
        headers: buildAgentUpstreamHeaders(req),
      }
    )
    clearTimeout(timer)

    if (!upstream.ok) {
      const err = await upstream.json().catch(() => ({ detail: upstream.statusText }))
      return NextResponse.json(err, { status: upstream.status })
    }

    const data = await upstream.json()
    return NextResponse.json(data)
  } catch (err) {
    clearTimeout(timer)
    return NextResponse.json(
      { error: "Cannot connect to property price history service" },
      { status: 502 }
    )
  }
}
