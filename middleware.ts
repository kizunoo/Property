/**
 * middleware.ts
 * Next.js Edge Middleware implementing:
 * 1. CSRF/Origin enforcement on browser-facing state-changing /api/* requests.
 * 2. Strict Default-Deny gate over all pages and API routes.
 * 
 * ALLOWLIST:
 * - /api/whatsapp/webhook (Meta signature verified)
 * - /api/calendar/*.ics (signed HMAC token)
 * - /portal/* and /api/portal/* (Portal v2 session authenticated)
 * - /login (Agent public login & enrollment UI)
 * - /api/agent/login, /api/agent/enroll, /api/agent/reset-password, /api/agent/logout
 * - /api/health
 * 
 * ALL OTHER PAGES & APIS:
 * - Blocked unless valid agent_session cookie is present.
 * - API routes return 401 Unauthorized JSON.
 * - Page routes redirect to /login.
 * - /preview/* returns 404 in production, requires agent_session otherwise.
 */

import { NextResponse } from "next/server"
import type { NextRequest } from "next/server"

const PUBLIC_EXEMPT_PATHS = new Set([
  "/api/whatsapp/webhook",
  "/api/health",
  "/api/agent/login",
  "/api/agent/enroll",
  "/api/agent/reset-password",
  "/api/agent/logout",
  "/login",
])

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl
  const isProd = (process.env.ENVIRONMENT || "").toLowerCase() === "production"

  // 1. Static Next.js internals & assets pass through
  if (
    pathname.startsWith("/_next") ||
    pathname.startsWith("/static") ||
    pathname === "/favicon.ico" ||
    (pathname.includes(".") && !pathname.endsWith(".ics"))
  ) {
    return NextResponse.next()
  }

  // 2. Gate dev-only /preview/* route
  if (pathname.startsWith("/preview")) {
    if (isProd) {
      return new NextResponse("Not Found", { status: 404 })
    }
  }

  // 3. CSRF / Origin Check on state-changing API routes
  if (["POST", "PUT", "PATCH", "DELETE"].includes(req.method) && pathname.startsWith("/api/")) {
    if (pathname !== "/api/whatsapp/webhook") {
      const origin = req.headers.get("origin")
      const secFetchSite = req.headers.get("sec-fetch-site")

      // Cross-site browser requests are rejected
      if (secFetchSite === "cross-site") {
        return NextResponse.json(
          { detail: "CSRF verification failed: Cross-site request rejected." },
          { status: 403 }
        )
      }

      if (origin) {
        let originHost = ""
        try {
          originHost = new URL(origin).host
        } catch {
          return NextResponse.json(
            { detail: "CSRF verification failed: Malformed Origin header." },
            { status: 403 }
          )
        }

        const reqHost = req.headers.get("host") || ""
        const allowedHosts = new Set<string>()
        if (reqHost) allowedHosts.add(reqHost)

        if (!isProd) {
          allowedHosts.add("localhost:3000")
          allowedHosts.add("127.0.0.1:3000")
          allowedHosts.add("localhost:8000")
          allowedHosts.add("127.0.0.1:8000")
        }

        const envOrigins = (process.env.ALLOWED_ORIGINS || "")
          .split(",")
          .map(o => o.trim())
          .filter(Boolean)
        for (const eo of envOrigins) {
          try {
            allowedHosts.add(new URL(eo.startsWith("http") ? eo : `https://${eo}`).host)
          } catch {
            allowedHosts.add(eo)
          }
        }

        if (!allowedHosts.has(originHost)) {
          return NextResponse.json(
            { detail: `CSRF verification failed: Untrusted Origin '${originHost}'.` },
            { status: 403 }
          )
        }
      }
    }
  }

  // 4. Signed calendar .ics link pass-through
  if (pathname.startsWith("/api/calendar/") && pathname.endsWith(".ics")) {
    return NextResponse.next()
  }

  // 5. Client Portal v2 routes pass-through (handled by portal_session auth)
  if (pathname.startsWith("/portal") || pathname.startsWith("/api/portal")) {
    return NextResponse.next()
  }

  // 6. Check explicit public paths
  if (PUBLIC_EXEMPT_PATHS.has(pathname)) {
    return NextResponse.next()
  }

  // 7. Coarse session check: agent_session cookie must be present
  const sessionToken = req.cookies.get("agent_session")?.value

  if (!sessionToken) {
    if (pathname.startsWith("/api/")) {
      return NextResponse.json(
        { detail: "Authentication required. Please log in to access agent services." },
        { status: 401 }
      )
    }

    const loginUrl = new URL("/login", req.url)
    if (pathname !== "/") {
      loginUrl.searchParams.set("returnUrl", pathname)
    }
    return NextResponse.redirect(loginUrl)
  }

  return NextResponse.next()
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico).*)",
  ],
}
