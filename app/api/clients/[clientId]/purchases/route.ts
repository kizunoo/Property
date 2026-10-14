import { NextRequest, NextResponse } from "next/server"

export const maxDuration = 15

const FASTAPI_URL = process.env.FASTAPI_URL ?? "http://localhost:8000"

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ clientId: string }> },
) {
  const { clientId } = await params
  try {
    const upstream = await fetch(`${FASTAPI_URL}/api/clients/${clientId}/purchases`, {
      method: "GET",
    })
    const data = await upstream.json()
    return NextResponse.json(data)
  } catch {
    return NextResponse.json([])
  }
}

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ clientId: string }> },
) {
  const { clientId } = await params
  const body = await req.json().catch(() => ({}))

  try {
    const upstream = await fetch(`${FASTAPI_URL}/api/clients/${clientId}/purchases`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
    const data = await upstream.json()
    if (!upstream.ok) {
      return NextResponse.json(
        { error: data?.detail ?? "Failed to save past purchase" },
        { status: upstream.status },
      )
    }
    return NextResponse.json(data)
  } catch {
    return NextResponse.json({ error: "Cannot connect to backend" }, { status: 502 })
  }
}
