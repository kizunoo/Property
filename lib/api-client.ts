/**
 * lib/api-client.ts
 * ─────────────────
 * Shared authenticated fetch wrapper for the agent dashboard.
 * - HTTP 401 (Unauthorized / Session Expired):
 *   Automatically redirects to /login?session_expired=true so the user is prompted
 *   to re-authenticate instead of leaving blank or silently failed UI panels.
 * - HTTP 403 (Forbidden / Access Denied):
 *   Dispatches a global toast/event and surfaces a visible user-friendly error message.
 */

export interface ApiClientOptions extends RequestInit {
  skipAuthRedirect?: boolean
}

export async function fetchWithAuth(
  input: RequestInfo | URL,
  init?: ApiClientOptions
): Promise<Response> {
  const options = { ...init }
  const skipRedirect = options.skipAuthRedirect ?? false
  delete options.skipAuthRedirect

  try {
    const res = await fetch(input, options)

    if (res.status === 401 && !skipRedirect) {
      if (typeof window !== "undefined") {
        const currentPath = window.location.pathname + window.location.search
        const redirectUrl = `/login?session_expired=true&returnUrl=${encodeURIComponent(currentPath)}`
        // Avoid redirect loop if already on login page
        if (!window.location.pathname.startsWith("/login")) {
          console.warn("[ApiClient] 401 Unauthorized: Session expired. Redirecting to login.")
          window.location.href = redirectUrl
        }
      }
    }

    if (res.status === 403) {
      if (typeof window !== "undefined") {
        console.warn("[ApiClient] 403 Forbidden: Insufficient permissions for this action.")
        window.dispatchEvent(
          new CustomEvent("api:forbidden", {
            detail: {
              url: typeof input === "string" ? input : input.toString(),
              status: 403,
              message: "Access Denied: You do not have permission to view or modify this resource.",
            },
          })
        )
      }
    }

    return res
  } catch (err) {
    console.error("[ApiClient] Network exception during fetch:", err)
    throw err
  }
}

/**
 * Convenience typed JSON wrapper
 */
export async function fetchJsonWithAuth<T = any>(
  input: RequestInfo | URL,
  init?: ApiClientOptions
): Promise<T> {
  const res = await fetchWithAuth(input, init)
  if (!res.ok) {
    const errBody = await res.json().catch(() => ({ detail: res.statusText }))
    const error: any = new Error(errBody.detail || errBody.error || `HTTP ${res.status}`)
    error.status = res.status
    error.body = errBody
    throw error
  }
  return res.json()
}
