import { buildAgentUpstreamHeaders } from "@/lib/agent-bff-auth"
import { NextRequest, NextResponse } from "next/server"

const FASTAPI_URL = process.env.FASTAPI_URL ?? process.env.NEXT_PUBLIC_FASTAPI_URL ?? "http://127.0.0.1:8000"

export async function POST(req: NextRequest) {
  try {
    const body = await req.json()
    const res = await fetch(`${FASTAPI_URL}/api/agent/login`, {
      method: "POST",
      headers: buildAgentUpstreamHeaders(req),
      body: JSON.stringify(body),
    })

    const rawText = await res.text()
    let data: any
    try {
      data = JSON.parse(rawText)
    } catch {
      data = { detail: rawText || "Upstream auth service returned invalid response" }
    }

    if (!res.ok) {
      return NextResponse.json({ detail: data.detail || "Authentication failed" }, { status: res.status })
    }

    const response = NextResponse.json(data)
    if (data.token) {
      response.cookies.set("agent_session", data.token, {
        httpOnly: true,
        secure: process.env.NODE_ENV === "production",
        sameSite: "lax",
        path: "/",
        maxAge: 12 * 3600, // 12 hours
      })
    }

    return response
  } catch (err: any) {
    console.error("[AGENT LOGIN ERROR]", err)
    return NextResponse.json({ detail: err?.message ? `Internal error: ${err.message}` : "Internal error connecting to auth service" }, { status: 500 })
  }
}
