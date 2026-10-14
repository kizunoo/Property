/**
 * Slot utilities for WhatsApp pitch auto-scheduling.
 * Generates and parses deterministic slot strings in format:
 *   "Mon 5 Oct, 10:00 AM"
 * aligned with Asia/Kuala_Lumpur business hours and backend parsing regex.
 */

export interface PitchSlot {
  index: number
  date: string    // "YYYY-MM-DD"
  time: string    // "HH:MM" (24-hour)
  label: string   // e.g. "Mon 5 Oct, 10:00 AM"
  slot_iso: string // ISO-8601 with +08:00 — required, never omitted when sending to backend
}

/**
 * Meta-approved viewing_slots_pitch template specification.
 * Single source of truth for sending, previewing, and storing messages.
 * Variable {{2}} is strictly the unit name/address.
 */
export const VIEWING_SLOTS_PITCH_TEMPLATE = {
  name: "viewing_slots_pitch",
  body: "Hello {{1}}, this is PIPELINE.EV regarding the robotics unit at {{2}}. We would like to invite your team for an on-site demonstration. Proposed slots: 1) {{3}}  2) {{4}}  3) {{5}}. Please choose a slot below or reply with a convenient time.",
  variables: [
    { position: 1, name: "client_name", description: "Prospect / Client full name", example: "Sarah Jenkins" },
    { position: 2, name: "unit_name", description: "Unit or property address/name", example: "Unit 12-A, The Horizon" },
    { position: 3, name: "slot_1", description: "First proposed slot label", example: "Thu 10 Oct, 2:00 PM" },
    { position: 4, name: "slot_2", description: "Second proposed slot label", example: "Fri 11 Oct, 10:00 AM" },
    { position: 5, name: "slot_3", description: "Third proposed slot label", example: "Fri 11 Oct, 3:30 PM" },
  ],
  buttons: [
    { position: 1, label: "Slot 1", payloadPattern: "slot_pick:{offer_id}:1" },
    { position: 2, label: "Slot 2", payloadPattern: "slot_pick:{offer_id}:2" },
    { position: 3, label: "Slot 3", payloadPattern: "slot_pick:{offer_id}:3" },
  ],
} as const

export function renderViewingSlotsPitchTemplate(params: {
  clientName?: string | null
  unitName?: string | null
  slot1?: string | null
  slot2?: string | null
  slot3?: string | null
}): string {
  return VIEWING_SLOTS_PITCH_TEMPLATE.body
    .replace("{{1}}", params.clientName || "Valued Partner")
    .replace("{{2}}", params.unitName || "Robotics Unit")
    .replace("{{3}}", params.slot1 || "Option 1")
    .replace("{{4}}", params.slot2 || "Option 2")
    .replace("{{5}}", params.slot3 || "Option 3")
}

const MONTH_NAMES = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]

const MONTH_MAP: Record<string, number> = {
  Jan: 1, Feb: 2, Mar: 3, Apr: 4, May: 5, Jun: 6,
  Jul: 7, Aug: 8, Sep: 9, Oct: 10, Nov: 11, Dec: 12,
}

const DAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

export function pad2(n: number): string {
  return n < 10 ? `0${n}` : `${n}`
}

/**
 * Converts a date string (YYYY-MM-DD) and 24h time (HH:MM) to an ISO-8601
 * timestamp in Asia/Kuala_Lumpur (+08:00) — the canonical form stored in DB.
 */
export function slotToIso(dateStr: string, timeStr: string): string {
  const [y, m, d] = dateStr.split("-").map(Number)
  const [h, min] = timeStr.split(":").map(Number)
  return `${y}-${pad2(m)}-${pad2(d)}T${pad2(h)}:${pad2(min)}:00+08:00`
}

/**
 * Formats a date string (YYYY-MM-DD) and 24h time string (HH:MM)
 * into a slot label matching the backend format, e.g. "Thu 8 Oct, 2:00 PM".
 */
export function formatSlotLabel(dateStr: string, timeStr: string): string {
  if (!dateStr || !timeStr) return ""
  const [y, m, d] = dateStr.split("-").map(Number)
  const [h, min] = timeStr.split(":").map(Number)
  if (isNaN(y) || isNaN(m) || isNaN(d) || isNaN(h) || isNaN(min)) return ""

  const dt = new Date(y, m - 1, d)
  const dayName = DAY_NAMES[dt.getDay()] ?? "Mon"
  const monthName = MONTH_NAMES[m - 1] ?? "Oct"

  const ampm = h >= 12 ? "PM" : "AM"
  const h12 = h % 12 === 0 ? 12 : h % 12
  const minStr = pad2(min)

  return `${dayName} ${d} ${monthName}, ${h12}:${minStr} ${ampm}`
}

/**
 * Parses a slot label (e.g. "Mon 5 Oct, 10:00 AM") into { date, time }.
 * Uses nearest-future-date logic: tries current year then next year,
 * picking the first one that produces a future datetime.
 * This fixes December→January cross-year rollover bugs.
 */
export function parseSlotLabel(label: string): { date: string; time: string } | null {
  if (!label) return null
  const regex = /^[A-Za-z]{3}\s+(\d{1,2})\s+([A-Za-z]{3}),\s+(\d{1,2}):(\d{2})\s+(AM|PM)$/
  const match = label.trim().match(regex)
  if (!match) return null

  const [, dStr, mStr, hStr, minStr, ampm] = match
  const m = MONTH_MAP[mStr]
  if (!m) return null

  let h = parseInt(hStr, 10)
  if (ampm === "PM" && h < 12) h += 12
  if (ampm === "AM" && h === 12) h = 0

  const now = new Date()
  const currentYear = now.getFullYear()

  // Try current year first, then next year — nearest future date wins
  for (const year of [currentYear, currentYear + 1]) {
    const dateStr = `${year}-${pad2(m)}-${pad2(parseInt(dStr, 10))}`
    const isoAttempt = `${dateStr}T${pad2(h)}:${pad2(parseInt(minStr, 10))}:00+08:00`
    const candidate = new Date(isoAttempt)
    // Accept if the slot is at least 1 minute in the future
    if (candidate.getTime() > now.getTime() - 60_000) {
      return { date: dateStr, time: `${pad2(h)}:${minStr}` }
    }
  }

  // Slot is in the past — return current-year interpretation as fallback
  const dateStr = `${currentYear}-${pad2(m)}-${pad2(parseInt(dStr, 10))}`
  return { date: dateStr, time: `${pad2(h)}:${minStr}` }
}

/**
 * Creates a fully-structured PitchSlot with slot_iso always populated.
 */
export function createStructuredSlot(
  index: number,
  dateStr: string,
  timeStr: string,
): PitchSlot {
  return {
    index,
    date: dateStr,
    time: timeStr,
    label: formatSlotLabel(dateStr, timeStr),
    slot_iso: slotToIso(dateStr, timeStr),
  }
}

/**
 * Extracts slot offerings from a pitch draft text.
 * ⚠ FALLBACK ONLY — use structured slots from the backend whenever available.
 * Emits a console warning to flag when this is called.
 */
export function parseSlotsFromDraft(text: string): PitchSlot[] {
  if (!text) return []
  const pattern = /(?:^|\s)([1-3])\)\s*([A-Za-z]{3}\s+\d{1,2}\s+[A-Za-z]{3},\s+\d{1,2}:\d{2}\s+(?:AM|PM))/g
  const slots: PitchSlot[] = []
  let m: RegExpExecArray | null

  while ((m = pattern.exec(text)) !== null) {
    const index = parseInt(m[1], 10)
    const label = m[2].trim()
    const parsed = parseSlotLabel(label)
    if (parsed) {
      console.warn(`[slot-utils] parseSlotsFromDraft fallback used for "${label}" — prefer structured slots`)
      slots.push({
        index,
        label,
        date: parsed.date,
        time: parsed.time,
        slot_iso: slotToIso(parsed.date, parsed.time),
      })
    } else {
      const fallbackDate = getFallbackDate(index)
      const fallbackTime = index === 1 ? "10:00" : index === 2 ? "11:30" : "14:00"
      slots.push({
        index,
        label,
        date: fallbackDate,
        time: fallbackTime,
        slot_iso: slotToIso(fallbackDate, fallbackTime),
      })
    }
  }

  if (slots.length === 0) {
    return [
      createDefaultSlot(1, 1, "10:00"),
      createDefaultSlot(2, 1, "11:30"),
      createDefaultSlot(3, 1, "14:00"),
    ]
  }

  return slots.sort((a, b) => a.index - b.index)
}

function getFallbackDate(offsetDays: number): string {
  const d = new Date()
  d.setDate(d.getDate() + offsetDays)
  // Skip weekend
  if (d.getDay() === 0) d.setDate(d.getDate() + 1)
  if (d.getDay() === 6) d.setDate(d.getDate() + 2)
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`
}

export function createDefaultSlot(index: number, dayOffset: number, timeStr: string): PitchSlot {
  const dateStr = getFallbackDate(dayOffset)
  return createStructuredSlot(index, dateStr, timeStr)
}

/**
 * Splits draft text into core body and call-to-action (CTA).
 */
export function splitPitchDraft(text: string): { body: string; cta: string } {
  const defaultCta = "Reply 1, 2 or 3 to book, or tell me a time that suits you."
  if (!text) return { body: "", cta: defaultCta }

  const marker = /Proposed slots:/i
  const match = text.match(marker)
  if (!match || match.index === undefined) {
    return { body: text.trim(), cta: defaultCta }
  }

  const body = text.slice(0, match.index).trim()
  const rest = text.slice(match.index + match[0].length)

  const ctaMarker = /Reply 1, 2 or 3[^\n]*/i
  const ctaMatch = rest.match(ctaMarker)
  const cta = ctaMatch ? ctaMatch[0].trim() : defaultCta

  return { body, cta }
}

/**
 * Assembles body, slots, and CTA into a complete WhatsApp pitch message.
 */
export function assemblePitchDraft(
  body: string,
  slots: PitchSlot[],
  cta = "Reply 1, 2 or 3 to book, or tell me a time that suits you.",
): string {
  const sorted = [...slots].sort((a, b) => a.index - b.index)
  const slotLine = sorted.map((s) => `${s.index}) ${s.label}`).join("  ")
  return `${body.trim()}\n\nProposed slots:\n${slotLine}\n\n${cta.trim()}`
}
