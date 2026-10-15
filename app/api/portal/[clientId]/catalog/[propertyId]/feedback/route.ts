import { NextRequest, NextResponse } from "next/server"
import { buildPortalUpstreamHeaders, requirePortalAuth } from "@/lib/portal-bff-auth"

const FASTAPI_URL = process.env.FASTAPI_URL ?? "http://127.0.0.1:8000"

export async function PUT(
  req: NextRequest,
  { params }: { params: Promise<{ clientId: string; propertyId: string }> }
) {
  const authErr = requirePortalAuth(req)
  if (authErr) return authErr

  const { clientId, propertyId } = await params
  try {
    const body = await req.json()
    const upstream = await fetch(
      `${FASTAPI_URL}/api/portal/${clientId}/catalog/${propertyId}/feedback`,
      {
        method: "PUT",
        headers: buildPortalUpstreamHeaders(req),
        body: JSON.stringify(body),
      }
    )
    const data = await upstream.json()
    if (!upstream.ok) {
      return NextResponse.json(
        { error: data?.detail ?? "Failed to save feedback" },
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
