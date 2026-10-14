import { NextRequest, NextResponse } from "next/server"
import { buildPortalUpstreamHeaders, requirePortalAuth } from "@/lib/portal-bff-auth"

const FASTAPI_URL = process.env.FASTAPI_URL ?? "http://127.0.0.1:8000"

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ clientId: string }> }
) {
  const authErr = requirePortalAuth(req)
  if (authErr) return authErr

  const { clientId } = await params
  let body: unknown
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 })
  }

  try {
    const upstream = await fetch(
      `${FASTAPI_URL}/api/portal/${clientId}/inquiry`,
      {
        method: "POST",
        headers: buildPortalUpstreamHeaders(req),
        body: JSON.stringify(body),
      }
    )
    const data = await upstream.json()
    if (!upstream.ok) {
      return NextResponse.json(
        { error: data?.detail ?? "Failed to submit inquiry" },
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
