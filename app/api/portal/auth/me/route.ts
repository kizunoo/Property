import { NextRequest, NextResponse } from "next/server"
import { buildPortalUpstreamHeaders, requirePortalAuth } from "@/lib/portal-bff-auth"

const FASTAPI_URL = process.env.FASTAPI_URL ?? "http://127.0.0.1:8000"

export async function GET(req: NextRequest) {
  const authErr = requirePortalAuth(req)
  if (authErr) return authErr

  try {
    const upstream = await fetch(`${FASTAPI_URL}/api/portal/auth/me`, {
      headers: buildPortalUpstreamHeaders(req),
    })
    const data = await upstream.json()
    return NextResponse.json(data, { status: upstream.status })
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Internal error" },
      { status: 500 }
    )
  }
}
