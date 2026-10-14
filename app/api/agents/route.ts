import { NextResponse } from "next/server"

const BACKEND_URL = process.env.BACKEND_URL ?? process.env.FASTAPI_URL ?? "http://localhost:8000"

export async function GET() {
  try {
    const res = await fetch(`${BACKEND_URL}/api/agents`, { cache: "no-store" })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      return NextResponse.json(err, { status: res.status })
    }
    return NextResponse.json(await res.json())
  } catch (err) {
    return NextResponse.json({ detail: String(err) }, { status: 502 })
  }
}

