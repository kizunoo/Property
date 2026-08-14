/**
 * Client-side helpers for scheduled viewings.
 */

export type ViewingStatus = "upcoming" | "completed" | "cancelled"

export interface ScheduledViewing {
  id: string
  client_id: string
  property_id: string
  scheduled_at: string   // ISO-8601
  status: ViewingStatus
  cancellation_reason?: string | null
  // Joined from Supabase foreign key select
  clients?: { id: string; name: string; preferred_neighborhood: string | null }
  properties?: { id: string; address: string; neighborhood: string | null }
}

export interface CompleteViewingResult {
  viewingId: string
  clientId: string
  clientName: string
  propertyId: string
  pastViewings: number
  probability: number
  expectedValue: number
  tier: "TIER_1" | "TIER_2" | "TIER_3"
}

// ─── Schedule a future viewing ─────────────────────────────────────────────────
export async function scheduleViewing(
  clientId: string,
  propertyId: string,
  scheduledAt: string,          // ISO-8601 e.g. "2026-08-15T10:30:00"
): Promise<ScheduledViewing> {
  const res = await fetch("/api/schedule_viewing", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ client_id: clientId, property_id: propertyId, scheduled_at: scheduledAt }),
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data?.error ?? `Schedule failed (${res.status})`)
  return data.viewing
}

// ─── Mark a scheduled viewing as completed (also increments past_viewings + re-scores) ──
export async function completeViewing(viewingId: string): Promise<CompleteViewingResult> {
  const res = await fetch(`/api/complete_viewing/${viewingId}`, { method: "PATCH" })
  const data = await res.json()
  if (!res.ok) throw new Error(data?.error ?? `Complete failed (${res.status})`)
  return {
    viewingId:    data.viewing_id,
    clientId:     data.client_id,
    clientName:   data.client_name,
    propertyId:   data.property_id,
    pastViewings: data.past_viewings,
    probability:  data.probability,
    expectedValue: data.expected_value,
    tier:         data.tier,
  }
}

// ─── Cancel a scheduled viewing ────────────────────────────────────────────────
export async function cancelViewing(viewingId: string, reason: string = "agent"): Promise<{ viewingId: string; status: string; reason: string }> {
  const res = await fetch(`/api/cancel_viewing/${viewingId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason }),
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data?.error ?? `Cancel failed (${res.status})`)
  return {
    viewingId: data.viewing_id,
    status: data.status,
    reason: data.reason,
  }
}

// ─── Fetch all scheduled viewings ─────────────────────────────────────────────
export async function fetchScheduledViewings(): Promise<ScheduledViewing[]> {
  const res = await fetch("/api/scheduled_viewings", { cache: "no-store" })
  const data = await res.json()
  if (!res.ok) throw new Error(data?.error ?? `Fetch failed (${res.status})`)
  return data.viewings ?? []
}

