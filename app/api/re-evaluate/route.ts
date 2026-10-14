import { buildAgentUpstreamHeaders } from "@/lib/agent-bff-auth"
import { NextResponse } from "next/server"

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000"

export async function POST(req: Request) {
  try {
    const res = await fetch(`${BACKEND}/api/run_evaluations`, {
      method: "POST",
      headers: buildAgentUpstreamHeaders(req),
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
