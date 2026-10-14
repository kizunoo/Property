import {
  PitchSlot,
  parseSlotLabel,
  parseSlotsFromDraft,
  slotToIso,
} from "./slot-utils"

export type { PitchSlot }

export interface InviteDetails {
  draft: string
  slots: PitchSlot[]
  cached?: boolean
}

const _cache = new Map<string, string>()
const _detailsCache = new Map<string, InviteDetails>()
const TIMEOUT_MS = 30_000

export async function fetchInviteDetails(
  clientId: string,
  propertyId: string,
  agentName = "R. Delgado",
  agentId?: string | null,
): Promise<InviteDetails> {
  const key = `${clientId}:${propertyId}:${agentId ?? ""}`

  if (_detailsCache.has(key)) {
    const cached = _detailsCache.get(key)!
    if (
      !cached.draft.includes("[Your Name]") &&
      !cached.draft.includes("[Agent Name]") &&
      cached.draft.includes("Reply 1, 2 or 3")
    ) {
      return cached
    }
  }

  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS)

  try {
    const res = await fetch("/api/invite", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        client_id: clientId,
        property_id: propertyId,
        agent_name: agentName,
        agent_id: agentId ?? null,
      }),
      signal: controller.signal,
    })

    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err?.error ?? `Request failed (${res.status})`)
    }

    const data = await res.json()
    const draft: string = data.draft

    // Build structured slots from backend or draft text
    // Backend provides slot_iso from generate_candidate_slots (always correct KL tz).
    // We also compute date+time from parseSlotLabel for UI pickers.
    let slots: PitchSlot[] = []
    if (Array.isArray(data.slots) && data.slots.length > 0) {
      slots = data.slots.map((s: any) => {
        const parsed = parseSlotLabel(s.label)
        const date = parsed?.date ?? ""
        const time = parsed?.time ?? ""
        // Prefer backend's slot_iso (already correct KL tz). Fall back to computed.
        const slot_iso = s.slot_iso || (date && time ? slotToIso(date, time) : "")
        return {
          index: s.index,
          label: s.label,
          slot_iso,
          date,
          time,
        }
      })
    }

    if (slots.length === 0 || slots.some((s) => !s.date || !s.time)) {
      slots = parseSlotsFromDraft(draft)
    }

    const result: InviteDetails = {
      draft,
      slots,
      cached: Boolean(data.cached),
    }

    _detailsCache.set(key, result)
    _cache.set(key, draft)
    return result
  } catch (err) {
    if ((err as Error).name === "AbortError") {
      throw new Error("Invite generation timed out after 30 seconds. Please try again.")
    }
    throw err
  } finally {
    clearTimeout(timer)
  }
}

export async function fetchInvite(
  clientId: string,
  propertyId: string,
  agentName = "R. Delgado",
  agentId?: string | null,
): Promise<string> {
  const details = await fetchInviteDetails(clientId, propertyId, agentName, agentId)
  return details.draft
}

