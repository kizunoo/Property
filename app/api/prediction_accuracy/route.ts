import { buildAgentUpstreamHeaders } from "@/lib/agent-bff-auth"
import { NextResponse } from "next/server"

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000"

export async function GET(req: Request) {
  const res = await fetch(`${BACKEND_URL}/api/prediction_accuracy`, { headers: buildAgentUpstreamHeaders(req) })
  return NextResponse.json(await res.json(), { status: res.status })
}
