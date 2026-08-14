import { NextRequest, NextResponse } from "next/server"

export const maxDuration = 15

const FASTAPI_URL = process.env.FASTAPI_URL ?? "http://127.0.0.1:8000"

export async function PATCH(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params
    const body = await req.json().catch(() => ({}))
    const upstream = await fetch(`${FASTAPI_URL}/api/cancel_viewing/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
    const data = await upstream.json()
    if (!upstream.ok) {
      return NextResponse.json({ error: data?.detail ?? "Failed to cancel viewing" }, { status: upstream.status })
    }
    return NextResponse.json(data)
  } catch (err) {
    return NextResponse.json({ error: err instanceof Error ? err.message : "Internal error" }, { status: 500 })
  }
}
