import { NextRequest, NextResponse } from "next/server"
import { buildPortalUpstreamHeaders } from "@/lib/portal-bff-auth"

const FASTAPI_URL = process.env.FASTAPI_URL ?? "http://127.0.0.1:8000"

export async function POST(req: NextRequest) {
  try {
    const body = await req.json()
    const upstream = await fetch(`${FASTAPI_URL}/api/portal/auth/legacy-login`, {
      method: "POST",
      headers: buildPortalUpstreamHeaders(req),
      body: JSON.stringify(body),
    })
    const data = await upstream.json()
    if (!upstream.ok) {
      return NextResponse.json(
        { error: data?.detail ?? "Invalid access code" },
        { status: upstream.status }
      )
    }

    const res = NextResponse.json(data)
    if (data.session_token) {
      res.cookies.set({
        name: "portal_session",
        value: data.session_token,
        httpOnly: true,
        secure: process.env.NODE_ENV === "production",
        sameSite: "lax",
        path: "/",
        maxAge: 7 * 24 * 60 * 60,
      })
    }
    return res
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Internal error" },
      { status: 500 }
    )
  }
}
