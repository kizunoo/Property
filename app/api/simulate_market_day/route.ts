import { NextRequest, NextResponse } from "next/server"

export const maxDuration = 60

const FASTAPI_URL = process.env.FASTAPI_URL ?? process.env.BACKEND_URL ?? "http://localhost:8000"

export async function POST(_req: NextRequest) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 55_000)
  try {
    const upstream = await fetch(
      FASTAPI_URL + "/api/simulate_market_day",
      { method: "POST", signal: controller.signal }
    )
    clearTimeout(timer)
    const data = await upstream.json()
    if (!upstream.ok) {
      return NextResponse.json(
        { error: data?.detail ?? "Market day simulation failed" },
        { status: upstream.status }
      )
    }
    return NextResponse.json(data)
  } catch (err) {
    clearTimeout(timer)
    const msg = (err as Error).name === "AbortError" ? "Backend timed out" : "Cannot connect to scoring backend"
    return NextResponse.json({ error: msg }, { status: 502 })
  }
}
