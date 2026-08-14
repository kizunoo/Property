import { NextRequest, NextResponse } from "next/server"

export const maxDuration = 30

const FASTAPI_URL = process.env.FASTAPI_URL ?? "http://localhost:8000"

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ propertyId: string }> },
) {
  const { propertyId } = await params
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 25_000)

  try {
    const upstream = await fetch(
      `${FASTAPI_URL}/api/shortlist/${propertyId}`,
      { signal: controller.signal },
    )
    clearTimeout(timer)

    const data = await upstream.json()

    if (!upstream.ok) {
      return NextResponse.json(
        { error: data?.detail ?? "Shortlist fetch failed" },
        { status: upstream.status },
      )
    }

    return NextResponse.json(data)
  } catch (err) {
    clearTimeout(timer)
    const msg =
      (err as Error).name === "AbortError"
        ? "Backend timed out"
        : "Cannot connect to scoring backend"
    return NextResponse.json({ error: msg }, { status: 502 })
  }
}
