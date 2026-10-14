import { NextRequest, NextResponse } from "next/server"
import { buildPortalUpstreamHeaders } from "@/lib/portal-bff-auth"

const FASTAPI_URL = process.env.FASTAPI_URL ?? "http://127.0.0.1:8000"

export async function POST(req: NextRequest) {
  try {
    const upstream = await fetch(`${FASTAPI_URL}/api/portal/auth/logout`, {
      method: "POST",
      headers: buildPortalUpstreamHeaders(req),
    })
    const data = await upstream.json().catch(() => ({}))
    const res = NextResponse.json(data, { status: upstream.status })
    // Clear cookie
    res.cookies.delete("portal_session")
    return res
  } catch (err) {
    const res = NextResponse.json(
      { error: err instanceof Error ? err.message : "Internal error" },
      { status: 500 }
    )
    res.cookies.delete("portal_session")
    return res
  }
}
