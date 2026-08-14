/**
 * Client-side helper for fetching AI reasoning for a client-property pair.
 *
 * Two-level caching:
 *  1. In-memory Map (module-level) — instant on modal re-open within same session
 *  2. Supabase `reasoning_cache` table — survives page reloads (backend handles this)
 */

const _cache = new Map<string, string>()

const TIMEOUT_MS = 30_000 // 30 seconds

export async function fetchReasoning(
  clientId: string,
  propertyId: string,
): Promise<string> {
  const key = `${clientId}:${propertyId}`

  // Level 1: in-memory cache — instant
  if (_cache.has(key)) return _cache.get(key)!

  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS)

  try {
    const res = await fetch("/api/reasoning", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ client_id: clientId, property_id: propertyId }),
      signal: controller.signal,
    })

    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err?.error ?? `Request failed (${res.status})`)
    }

    const data = await res.json()
    const reasoning: string = data.reasoning

    // Store in level-1 cache
    _cache.set(key, reasoning)
    return reasoning
  } catch (err) {
    if ((err as Error).name === "AbortError") {
      throw new Error("Analysis timed out after 30 seconds. Please try again.")
    }
    throw err
  } finally {
    clearTimeout(timer)
  }
}
