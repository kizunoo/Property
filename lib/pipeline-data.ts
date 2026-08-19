export type Tier = "TIER_1" | "TIER_2" | "TIER_3"

export interface Client {
  id: string          // evaluation row UUID
  clientDbId: string  // real UUID from the clients table
  propertyDbId: string // real UUID from the properties table
  name: string
  initials: string
  property: string
  propertyValue: number
  probability: number
  expectedValue: number
  tier: Tier
  agent: string
  statedBudget?: number
  preferredNeighborhood?: string
  pastViewings?: number
  outcome?: "pending" | "won" | "lost"
}

/**
 * A deduplicated view of a client — one row in the table.
 * `bestMatch` is the evaluation row with the highest Expected Value.
 * `otherMatchCount` is how many additional evaluation rows exist for this client.
 */
export interface DeduplicatedClient {
  /** Stable client ID (from the clients table, NOT the evaluation row id) */
  clientId: string
  name: string
  initials: string
  tier: Tier
  statedBudget: number
  preferredNeighborhood: string
  pastViewings: number
  /** Best-match property details (highest E(x)) */
  bestMatch: {
    evalId: string
    propertyId: string  // real UUID from the properties table (for reasoning cache key)
    property: string
    propertyValue: number
    probability: number
    expectedValue: number
    neighborhood: string
    outcome: "pending" | "won" | "lost"
  }
  /** How many additional property evaluations exist for this client (0 = only one match) */
  otherMatchCount: number
  /** All raw evaluation rows for this client, sorted best-first */
  allMatches: Client[]
}

export interface Property {
  id: string
  name: string
  address: string
  neighborhood: string
  value: number
  status: "LISTED" | "PENDING" | "UNDER OFFER"
  imageUrl?: string
}

export const TIER_LABEL: Record<Tier, string> = {
  TIER_1: "TIER 1 — VIP",
  TIER_2: "TIER 2 — WARM",
  TIER_3: "TIER 3 — COLD",
}

export const TIER_SHORT: Record<Tier, string> = {
  TIER_1: "VIP",
  TIER_2: "WARM",
  TIER_3: "COLD",
}

export function initialsOf(name: string) {
  return name
    .split(" ")
    .map((part) => part[0])
    .join("")
    .toUpperCase()
    .slice(0, 2)
}

export const currency = (value: number) =>
  `RM ${new Intl.NumberFormat("en-US", {
    maximumFractionDigits: 0,
  }).format(value)}`

export const percent = (value: number) => `${Math.round(value * 100)}%`

export interface PipelineEvaluationRow {
  id: string
  ai_probability: number
  expected_value: number
  segment_tier: Tier
  outcome?: string | null
  clients:
    | {
        id: string
        name: string
        stated_budget?: number
        preferred_neighborhood?: string
        past_viewings?: number
      }
    | {
        id: string
        name: string
        stated_budget?: number
        preferred_neighborhood?: string
        past_viewings?: number
      }[]
    | null
  properties:
    | {
        id: string
        address: string
        neighborhood: string
        property_value: number
      }
    | {
        id: string
        address: string
        neighborhood: string
        property_value: number
      }[]
    | null
}

export interface PropertyRow {
  id: string
  address: string
  neighborhood: string
  property_value: number
  image_url?: string
}

function unwrapRelation<T>(value: T | T[] | null): T | null {
  if (value == null) return null
  return Array.isArray(value) ? (value[0] ?? null) : value
}

export function mapEvaluationToClient(row: PipelineEvaluationRow): Client | null {
  const client = unwrapRelation(row.clients)
  const property = unwrapRelation(row.properties)
  if (!client || !property) return null

  return {
    id: row.id,
    clientDbId: client.id,
    propertyDbId: property.id,
    name: client.name,
    initials: initialsOf(client.name),
    property: property.address,
    propertyValue: property.property_value,
    probability: row.ai_probability,
    expectedValue: Math.round(row.expected_value),
    tier: row.segment_tier,
    agent: property.neighborhood,
    statedBudget: client.stated_budget,
    preferredNeighborhood: client.preferred_neighborhood,
    pastViewings: client.past_viewings,
    outcome: (row.outcome === "won" || row.outcome === "lost") ? row.outcome : "pending",
  }
}

export function mapPropertyRow(row: PropertyRow, index: number): Property {
  const statuses: Property["status"][] = ["LISTED", "PENDING", "UNDER OFFER"]
  return {
    id: row.id,
    name: row.neighborhood,
    address: row.address,
    neighborhood: row.neighborhood,
    value: row.property_value,
    status: statuses[index % statuses.length],
    imageUrl: row.image_url ?? undefined,
  }
}

// ─── Shared aggregation ───────────────────────────────────────────────────────
/**
 * Single source of truth for all dashboard / chart aggregations.
 *
 * Deduplicates the raw evaluation rows so:
 *   - Each client is counted once (by clientDbId) using their best-match row
 *     (highest E(x) — the first occurrence, since fetch-pipeline-data.ts sorts
 *      evaluations by expected_value DESC before dedup).
 *   - Each property is counted once (by propertyDbId) for totalPropertyValue.
 *
 * Pass the full rawClients for the Dashboard tab, or a filtered subset for
 * Analytics charts — deduplication is applied in either case.
 */
export interface DashboardSummary {
  /** Sum of each unique client's best-match E(x). */
  totalPipelineValue: number
  /** Sum of each unique listing's property_value. */
  totalPropertyValue: number
  /** Unique client count per tier (based on best-match tier). */
  byTier: Record<Tier, number>
  /** Total best-match E(x) per tier (used by the Treemap). */
  byTierEx: Record<Tier, number>
  /** Avg best-match P(Buy) across all unique clients. */
  avgProbability: number
  uniqueClientCount: number
  uniquePropertyCount: number
}

export function getDashboardSummary(rawClients: Client[]): DashboardSummary {
  // ── Deduplicate clients ──────────────────────────────────────────────────
  // fetch-pipeline-data already sorts by expected_value DESC, so the first
  // occurrence of each clientDbId is always the best-match row.
  const seenClients = new Set<string>()
  const uniqueClients = rawClients.filter((c) => {
    if (seenClients.has(c.clientDbId)) return false
    seenClients.add(c.clientDbId)
    return true
  })

  // ── Deduplicate properties ───────────────────────────────────────────────
  const seenProps = new Set<string>()
  const uniqueProperties = rawClients.filter((c) => {
    if (seenProps.has(c.propertyDbId)) return false
    seenProps.add(c.propertyDbId)
    return true
  })

  const byTier:   Record<Tier, number> = { TIER_1: 0, TIER_2: 0, TIER_3: 0 }
  const byTierEx: Record<Tier, number> = { TIER_1: 0, TIER_2: 0, TIER_3: 0 }
  let totalPipelineValue = 0
  let totalProbability   = 0

  for (const c of uniqueClients) {
    byTier[c.tier]   += 1
    byTierEx[c.tier] += c.expectedValue
    totalPipelineValue += c.expectedValue
    totalProbability   += c.probability
  }

  return {
    totalPipelineValue,
    totalPropertyValue: uniqueProperties.reduce((sum, c) => sum + c.propertyValue, 0),
    byTier,
    byTierEx,
    avgProbability: uniqueClients.length > 0 ? totalProbability / uniqueClients.length : 0,
    uniqueClientCount:    uniqueClients.length,
    uniquePropertyCount:  uniqueProperties.length,
  }
}
