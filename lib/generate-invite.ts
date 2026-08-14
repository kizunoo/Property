/**
 * Client-side helper for fetching AI-generated invite drafts for a client-property pair.
 *
 * Two-level caching:
 *  1. In-memory Map (module-level) — instant on re-click within same session
 *  2. Supabase `invite_drafts` table — survives page reloads (backend handles this)
 */

const _cache = new Map<string, string>()
const TIMEOUT_MS = 30_000

export async function fetchInvite(
  clientId: string,
  propertyId: string,
  agentName = "R. Delgado",
): Promise<string> {
  const key = `${clientId}:${propertyId}`

  if (_cache.has(key)) {
    const cached = _cache.get(key)!
    if (!cached.includes("[Your Name]") && !cached.includes("[Agent Name]")) {
      return cached
    }
  }

  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS)

  try {
    const res = await fetch("/api/invite", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ client_id: clientId, property_id: propertyId, agent_name: agentName }),
      signal: controller.signal,
    })

    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err?.error ?? `Request failed (${res.status})`)
    }

    const data = await res.json()
    const draft: string = data.draft

    _cache.set(key, draft)
    return draft
  } catch (err) {
    if ((err as Error).name === "AbortError") {
      throw new Error("Invite generation timed out after 30 seconds. Please try again.")
    }
    throw err
  } finally {
    clearTimeout(timer)
  }
}
