import { NextRequest, NextResponse } from "next/server"
import { buildAgentUpstreamHeaders } from "@/lib/agent-bff-auth"

const FASTAPI_URL = process.env.FASTAPI_URL || process.env.BACKEND_URL || "http://127.0.0.1:8000"

async function proxyRequest(req: NextRequest, { params }: { params: Promise<{ path: string[] }> | { path: string[] } }) {
  const resolvedParams = await params
  const path = resolvedParams.path.join("/")
  const url = new URL(req.url)
  const targetUrl = `${FASTAPI_URL}/api/console/${path}${url.search}`

  const headers = buildAgentUpstreamHeaders(req)
  const body = req.method !== "GET" && req.method !== "HEAD" ? await req.text() : undefined

  try {
    const upstream = await fetch(targetUrl, {
      method: req.method,
      headers,
      body,
      cache: "no-store",
    })

    const contentType = upstream.headers.get("content-type") || "application/json"
    const data = await upstream.text()

    return new NextResponse(data, {
      status: upstream.status,
      headers: {
        "Content-Type": contentType,
      },
    })
  } catch (err: any) {
    return NextResponse.json({ error: "BFF upstream error", detail: err?.message }, { status: 502 })
  }
}

export const GET = proxyRequest
export const POST = proxyRequest
export const PATCH = proxyRequest
export const PUT = proxyRequest
export const DELETE = proxyRequest
