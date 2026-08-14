import { NextRequest, NextResponse } from "next/server"

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000"

export async function POST(req: NextRequest) {
  try {
    const body = await req.json()
    const res = await fetch(`${BACKEND}/api/generate_insight`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      return NextResponse.json(err, { status: res.status })
    }
    const data = await res.json()
    return NextResponse.json(data)
  } catch (err) {
    return NextResponse.json({ detail: String(err) }, { status: 502 })
  }
}
