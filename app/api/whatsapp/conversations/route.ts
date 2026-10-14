import { buildAgentUpstreamHeaders } from "@/lib/agent-bff-auth"
import { NextRequest, NextResponse } from "next/server"

export const maxDuration = 15
const FASTAPI_URL = process.env.FASTAPI_URL ?? process.env.BACKEND_URL ?? "http://localhost:8000"

export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url)
    const agent_id = searchParams.get("agent_id") ?? ""

    const url = new URL(`${FASTAPI_URL}/api/whatsapp/conversations`)
    if (agent_id) url.searchParams.set("agent_id", agent_id)

    const upstream = await fetch(url.toString(), { method: "GET" })
    const data = await upstream.json().catch(() => ({ conversations: [] }))
    return NextResponse.json(data, { status: upstream.status })
  } catch (err: any) {
    return NextResponse.json({ conversations: [], error: String(err) }, { status: 500 })
  }
}
