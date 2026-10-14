import { NextRequest, NextResponse } from "next/server"

export const maxDuration = 15
const FASTAPI_URL = process.env.FASTAPI_URL ?? process.env.BACKEND_URL ?? "http://localhost:8000"

export async function POST(req: NextRequest) {
  try {
    const body = await req.json()
    const upstream = await fetch(`${FASTAPI_URL}/api/whatsapp/suggest_reply`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
    const data = await upstream.json().catch(() => ({ suggested_text: "" }))
    return NextResponse.json(data, { status: upstream.status })
  } catch (err: any) {
    return NextResponse.json({ suggested_text: "", error: String(err) }, { status: 500 })
  }
}
