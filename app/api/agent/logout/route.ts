import { NextRequest, NextResponse } from "next/server"
import { buildAgentUpstreamHeaders } from "@/lib/agent-bff-auth"

const FASTAPI_URL = process.env.NEXT_PUBLIC_FASTAPI_URL ?? "http://127.0.0.1:8000"

export async function POST(req: NextRequest) {
  try {
    const headers = buildAgentUpstreamHeaders(req)
    await fetch(`${FASTAPI_URL}/api/agent/logout`, {
      method: "POST",
      headers,
    })
  } catch {
    // Ignore upstream error on logout
  }

  const response = NextResponse.json({ success: true, message: "Logged out" })
  response.cookies.delete("agent_session")
  return response
}
