import { NextRequest, NextResponse } from "next/server"
import { buildPortalUpstreamHeaders, requirePortalAuth } from "@/lib/portal-bff-auth"

const FASTAPI_URL = process.env.FASTAPI_URL ?? "http://127.0.0.1:8000"

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ clientId: string }> }
) {
  const authErr = requirePortalAuth(req)
  if (authErr) return authErr

  const { clientId } = await params
  try {
    const upstream = await fetch(`${FASTAPI_URL}/api/portal/${clientId}/demos`, {
      headers: buildPortalUpstreamHeaders(req),
    })
    const data = await upstream.json()
    if (!upstream.ok) {
      return NextResponse.json(
        { error: data?.detail ?? "Failed to fetch demonstrations" },
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
