/**
 * lib/agent-bff-auth.ts
 * Helper for Next.js BFF routes to extract the agent session token from cookies
 * and forward it to FastAPI in the Authorization: Bearer <token> header,
 * along with trusted client IP and BFF internal secret for rate-limiting.
 */

import { NextRequest } from "next/server"

export function getAgentToken(req: Request | NextRequest): string | null {
  if ("cookies" in req && typeof (req as any).cookies?.get === "function") {
    const val = (req as any).cookies.get("agent_session")?.value
    if (val) return val
  }
  const cookieHeader = req.headers?.get("cookie") || ""
  const match = cookieHeader.match(/(?:^|;\s*)agent_session=([^;]+)/)
  return match ? decodeURIComponent(match[1]) : null
}

export function getClientIp(req: Request | NextRequest): string {
  // Check x-real-ip first (set by reverse proxy / ngrok to verified client)
  const realIp = req.headers?.get("x-real-ip")
  if (realIp && realIp.trim()) return realIp.trim()

  const forwardedFor = req.headers?.get("x-forwarded-for")
  if (forwardedFor) {
    // Leftmost IP is original client in proxy chain
    const parts = forwardedFor.split(",").map(p => p.trim()).filter(Boolean)
    if (parts.length > 0) return parts[0]
  }

  return (req as any).ip || "127.0.0.1"
}

export function buildAgentUpstreamHeaders(
  req: Request | NextRequest,
  extraHeaders: Record<string, string> = {}
): Record<string, string> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...extraHeaders,
  }
  const token = getAgentToken(req)
  if (token) {
    headers["Authorization"] = `Bearer ${token}`
  }

  // Forward client IP and BFF internal secret for trusted rate-limiting in FastAPI
  const clientIp = getClientIp(req)
  headers["X-Forwarded-For"] = clientIp

  const bffSecret = process.env.BFF_INTERNAL_SECRET
  if (bffSecret) {
    headers["X-BFF-Internal-Secret"] = bffSecret
  } else {
    console.warn("[BFF WARN] BFF_INTERNAL_SECRET is missing from environment. FastAPI will not trust forwarded client IPs.")
  }

  const userAgent = req.headers?.get("user-agent")
  if (userAgent) {
    headers["User-Agent"] = userAgent
  }

  return headers
}
