import { NextRequest, NextResponse } from "next/server"

export const maxDuration = 15

const FASTAPI_URL = process.env.FASTAPI_URL ?? process.env.BACKEND_URL ?? "http://localhost:8000"

export async function POST(req: NextRequest) {
  try {
    const body = await req.json().catch(() => ({}))

    const upstream = await fetch(`${FASTAPI_URL}/api/whatsapp/send_message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })

    const data = await upstream.json().catch(() => ({}))

    if (!upstream.ok) {
      const msg = data?.detail ?? data?.error ?? "Failed to send WhatsApp message"
      return NextResponse.json(
        { error: msg, detail: msg },
        { status: upstream.status },
      )
    }

    return NextResponse.json(data)
  } catch (err: any) {
    return NextResponse.json(
      { error: err?.message ?? "Cannot connect to backend logic engine", detail: err?.message ?? "Cannot connect to backend logic engine" },
      { status: 502 },
    )
  }
}
