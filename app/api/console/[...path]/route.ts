import { NextRequest, NextResponse } from "next/server"
import { buildAgentUpstreamHeaders } from "@/lib/agent-bff-auth"

const FASTAPI_URL = process.env.FASTAPI_URL || process.env.BACKEND_URL || "http://127.0.0.1:8000"

const ALLOWED_METHODS = new Set(["GET", "POST", "PUT", "PATCH", "DELETE"])

async function proxyRequest(req: NextRequest, { params }: { params: Promise<{ path: string[] }> | { path: string[] } }) {
  if (!ALLOWED_METHODS.has(req.method)) {
    return NextResponse.json({ error: "Method not allowed" }, { status: 405 })
  }

  const resolvedParams = await params
  const rawSegments = resolvedParams.path || []

  if (!rawSegments.length) {
    return NextResponse.json({ error: "Empty path" }, { status: 400 })
  }

  // Reject segments containing '..', '%2e', '%2f', '\' or empty segments
  for (const seg of rawSegments) {
    if (!seg || seg.trim() === "") {
      return NextResponse.json({ error: "Invalid empty path segment" }, { status: 400 })
    }
    const lower = seg.toLowerCase()
    if (
      seg.includes("..") ||
      seg.includes("\\") ||
      lower.includes("%2e") ||
      lower.includes("%2f") ||
      lower.includes("%5c")
    ) {
      return NextResponse.json({ error: "Invalid path segment: traversal detected" }, { status: 400 })
    }
  }

  // Also verify raw request URL does not attempt path traversal
  const rawUrl = req.url || ""
  if (rawUrl.includes("..") || rawUrl.toLowerCase().includes("%2e%2e")) {
    return NextResponse.json({ error: "Invalid path: traversal detected" }, { status: 400 })
  }

  const path = rawSegments.join("/")
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
