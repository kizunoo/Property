import { buildAgentUpstreamHeaders } from "@/lib/agent-bff-auth"
import { NextRequest, NextResponse } from "next/server"

export const maxDuration = 15
const FASTAPI_URL = process.env.FASTAPI_URL ?? process.env.BACKEND_URL ?? "http://localhost:8000"

export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url)
    const to_number = searchParams.get("to_number") ?? ""
    const client_id = searchParams.get("client_id") ?? ""
    const agent_id  = searchParams.get("agent_id")  ?? ""

    const url = new URL(`${FASTAPI_URL}/api/whatsapp/messages`)
    if (to_number) url.searchParams.set("to_number", to_number)
    if (client_id) url.searchParams.set("client_id", client_id)
    if (agent_id)  url.searchParams.set("agent_id",  agent_id)

    const upstream = await fetch(url.toString(), { method: "GET" })
    const data = await upstream.json().catch(() => ({ messages: [] }))
    return NextResponse.json(data)
  } catch (err: any) {
    return NextResponse.json({ messages: [] })
  }
}
