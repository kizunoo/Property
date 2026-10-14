import { NextRequest, NextResponse } from "next/server"

export const maxDuration = 15

const FASTAPI_URL = process.env.FASTAPI_URL ?? process.env.BACKEND_URL ?? "http://localhost:8000"

export async function POST(req: NextRequest) {
  try {
    const body = await req.json().catch(() => ({}))

    const upstream = await fetch(`${FASTAPI_URL}/api/invite/mark_sent`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })

    const data = await upstream.json()

    if (!upstream.ok) {
      return NextResponse.json(
        { error: data?.detail ?? "Failed to mark invite as sent" },
        { status: upstream.status },
      )
    }

    return NextResponse.json(data)
  } catch {
    return NextResponse.json({ error: "Cannot connect to backend logic engine" }, { status: 502 })
  }
}
