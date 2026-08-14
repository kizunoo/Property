/**
 * Client-side helper for the /api/log_viewing endpoint.
 * Increments the client's past_viewings, re-scores the pair, and returns the updated metrics.
 */

export interface ViewingResult {
  clientId: string
  clientName: string
  propertyId: string
  pastViewings: number
  probability: number    // 0.0–1.0
  expectedValue: number  // RM
  tier: "TIER_1" | "TIER_2" | "TIER_3"
}

export async function logViewing(
  clientId: string,
  propertyId: string,
): Promise<ViewingResult> {
  const res = await fetch("/api/log_viewing", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ client_id: clientId, property_id: propertyId }),
  })

  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err?.error ?? `Viewing log failed (${res.status})`)
  }

  const data = await res.json()
  return {
    clientId:     data.client_id,
    clientName:   data.client_name,
    propertyId:   data.property_id,
    pastViewings: data.past_viewings,
    probability:  data.probability,
    expectedValue: data.expected_value,
    tier:         data.tier,
  }
}
