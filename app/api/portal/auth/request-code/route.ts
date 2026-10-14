import { NextRequest, NextResponse } from "next/server"
import { buildPortalUpstreamHeaders } from "@/lib/portal-bff-auth"

const FASTAPI_URL = process.env.FASTAPI_URL ?? "http://127.0.0.1:8000"

export async function POST(req: NextRequest) {
  try {
    const body = await req.json()
    const upstream = await fetch(`${FASTAPI_URL}/api/portal/auth/request-code`, {
      method: "POST",
      headers: buildPortalUpstreamHeaders(req),
      body: JSON.stringify(body),
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
