import { NextRequest, NextResponse } from "next/server"

export const maxDuration = 30

const FASTAPI_URL = process.env.FASTAPI_URL ?? "http://localhost:8000"
const UPSTREAM_TIMEOUT_MS = 25_000

export async function POST(req: NextRequest) {
  try {
    const body = await req.json()

    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), UPSTREAM_TIMEOUT_MS)

    let upstream: Response
    try {
      upstream = await fetch(`${FASTAPI_URL}/api/generate_invite`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      })
    } catch (fetchErr) {
      clearTimeout(timer)
      const msg = (fetchErr as Error).name === "AbortError"
        ? "Backend timed out generating invite"
        : "Cannot connect to backend logic engine"
      return NextResponse.json({ error: msg }, { status: 502 })
    } finally {
      clearTimeout(timer)
    }

    const data = await upstream.json()

    if (!upstream.ok) {
      return NextResponse.json(
        { error: data?.detail ?? "Invite generation failed" },
        { status: upstream.status },
      )
    }

    return NextResponse.json(data)
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Internal error" },
      { status: 500 },
    )
  }
}
