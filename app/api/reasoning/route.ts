import { buildAgentUpstreamHeaders } from "@/lib/agent-bff-auth"
import { NextRequest, NextResponse } from "next/server"

export const maxDuration = 30 // Next.js route timeout: 30 seconds

const FASTAPI_URL = process.env.FASTAPI_URL ?? "http://localhost:8000"
const UPSTREAM_TIMEOUT_MS = 25_000 // 25s — slightly less than the client timeout

export async function POST(req: NextRequest) {
  try {
    const body = await req.json()

    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), UPSTREAM_TIMEOUT_MS)

    let upstream: Response
    try {
      upstream = await fetch(`${FASTAPI_URL}/api/generate_reasoning`, {
        method: "POST",
        headers: buildAgentUpstreamHeaders(req),
        body: JSON.stringify(body),
        signal: controller.signal,
      })
    } catch (fetchErr) {
      clearTimeout(timer)
      const msg = (fetchErr as Error).name === "AbortError"
        ? "Backend timed out generating reasoning"
        : "Cannot connect to reasoning backend"
      return NextResponse.json({ error: msg }, { status: 502 })
    } finally {
      clearTimeout(timer)
    }

    const text = await upstream.text()
    let data: any = {}
    try {
      data = JSON.parse(text)
    } catch {
      // Upstream returned non-JSON (e.g. 500 HTML/plain text)
    }

    if (!upstream.ok) {
      return NextResponse.json(
        { error: data?.detail || data?.error || (text && text.length < 200 ? text : "Reasoning generation failed") },
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
