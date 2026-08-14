import { NextRequest, NextResponse } from "next/server"

export const maxDuration = 15

const FASTAPI_URL = process.env.FASTAPI_URL ?? "http://localhost:8000"

export async function POST(req: NextRequest) {
  try {
    const body = await req.json()

    const upstream = await fetch(`${FASTAPI_URL}/api/log_viewing`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })

    const data = await upstream.json()

    if (!upstream.ok) {
      return NextResponse.json(
        { error: data?.detail ?? "Failed to log viewing" },
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
