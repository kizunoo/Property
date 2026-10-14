import { buildAgentUpstreamHeaders } from "@/lib/agent-bff-auth"
import { NextRequest, NextResponse } from "next/server"

export const maxDuration = 15

const FASTAPI_URL = process.env.FASTAPI_URL ?? "http://localhost:8000"

export async function PATCH(
  req: NextRequest,
  { params }: { params: Promise<{ propertyId: string }> },
) {
  const { propertyId } = await params
  const body = await req.json().catch(() => ({}))

  try {
    const upstream = await fetch(`${FASTAPI_URL}/api/properties/${propertyId}`, {
      method: "PATCH",
      headers: buildAgentUpstreamHeaders(req),
      body: JSON.stringify(body),
    })
    const data = await upstream.json()
    if (!upstream.ok) {
      return NextResponse.json(
        { error: data?.detail ?? "Property update failed" },
        { status: upstream.status },
      )
    }
    return NextResponse.json(data)
  } catch {
    return NextResponse.json({ error: "Cannot connect to scoring backend" }, { status: 502 })
  }
}
