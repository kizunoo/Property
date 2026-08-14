import { initialsOf, type Tier } from "@/lib/pipeline-data"

export interface ShortlistEntry {
  clientId:      string
  name:          string
  initials:      string
  probability:   number
  tier:          Tier
  expectedValue: number
  confidence:    "HIGH" | "MEDIUM" | "LOW"
}

const TIMEOUT_MS = 30_000

export async function fetchShortlist(propertyId: string): Promise<ShortlistEntry[]> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS)

  try {
    const res = await fetch(`/api/shortlist/${propertyId}`, {
      signal: controller.signal,
    })

    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err?.error ?? `Request failed (${res.status})`)
    }

    const raw: Array<{
      client_id:      string
      name:           string
      probability:    number
      tier:           Tier
      expected_value: number
      confidence:     "HIGH" | "MEDIUM" | "LOW"
    }> = await res.json()

    return raw.map((r) => ({
      clientId:      r.client_id,
      name:          r.name,
      initials:      initialsOf(r.name),
      probability:   r.probability,
      tier:          r.tier,
      expectedValue: r.expected_value,
      confidence:    r.confidence,
    }))
  } catch (err) {
    if ((err as Error).name === "AbortError") {
      throw new Error("Shortlist timed out. Please try again.")
    }
    throw err
  } finally {
    clearTimeout(timer)
  }
}
