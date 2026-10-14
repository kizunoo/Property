import { NextRequest, NextResponse } from "next/server"

export function getPortalAuthToken(req: NextRequest): string | null {
  const cookieToken = req.cookies.get("portal_session")?.value
  if (cookieToken) return cookieToken

  const authHeader = req.headers.get("authorization")
  if (authHeader && authHeader.startsWith("Bearer ")) {
    return authHeader.slice(7).trim()
  }

  return null
}

export function getClientIp(req: NextRequest): string {
  // Check x-real-ip first (set by ngrok / reverse proxy to the verified client)
  const realIp = req.headers.get("x-real-ip")
  if (realIp && realIp.trim()) return realIp.trim()

  const forwardedFor = req.headers.get("x-forwarded-for")
  if (forwardedFor) {
    // In standard reverse-proxy chains (client -> ngrok/tunnel -> Next.js),
    // the leftmost IP is the origin client.
    const parts = forwardedFor.split(",").map(p => p.trim()).filter(Boolean)
    if (parts.length > 0) return parts[0]
  }

  return (req as unknown as { ip?: string }).ip || "127.0.0.1"
}

export function buildPortalUpstreamHeaders(req: NextRequest): Record<string, string> {
  const token = getPortalAuthToken(req)
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  }
  if (token) {
    headers["Authorization"] = `Bearer ${token}`
  }
  const userAgent = req.headers.get("user-agent")
  if (userAgent) {
    headers["User-Agent"] = userAgent
  }

  // Forward client IP and BFF internal secret for trusted FastAPI rate-limiting
  const clientIp = getClientIp(req)
  headers["X-Forwarded-For"] = clientIp

  const bffSecret = process.env.BFF_INTERNAL_SECRET
  if (bffSecret) {
    headers["X-BFF-Internal-Secret"] = bffSecret
  }

  return headers
}

export function requirePortalAuth(req: NextRequest): NextResponse | null {
  const token = getPortalAuthToken(req)
  if (!token) {
    return NextResponse.json(
      { error: "Authentication required: No session provided" },
      { status: 401 }
    )
  }
  return null
}

