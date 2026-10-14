export type Tier = "TIER_1" | "TIER_2" | "TIER_3"

export interface Agent {
  id: string
  name: string
  initials: string
  role: string
}

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
  mlProbability?: number | null
  /** Agent assigned to this client (null if column not yet populated) */
  assignedAgent?: { id: string; name: string; initials: string } | null
  /** Relationship lifecycle stage */
  relationshipStage?: string
  /** WhatsApp phone number (e.g. 60109722730) */
  whatsappNumber?: string | null
}

export interface PastPurchase {
  id: string
  clientId: string
  propertyId?: string | null
  propertyName: string
  neighborhood: string
  propertyType: string
  purchasePrice: number
  purchaseYear?: number | null
  purpose?: "own_stay" | "investment" | "holiday_home" | string | null
  notes?: string | null
  imageUrl?: string | null
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
  /** Rich buyer profile fields (all optional — null if not yet set) */
  financingStatus?: string | null       // 'cash'|'pre-approved'|'in-progress'|'unspecified'
  moveInTimeline?: string | null        // '< 3 months'|'3-6 months'|'6-12 months'|'flexible'
  propertyTypePreference?: string | null // 'condo'|'terrace'|'semi-d'|'bungalow'|'serviced_apt'|'any'
  secondaryNeighborhood?: string | null
  agentNotes?: string | null
  /** Verified previous property acquisition history (track record) */
  pastPurchases?: PastPurchase[]
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
    mlProbability?: number | null
  }
  /** How many additional property evaluations exist for this client (0 = only one match) */
  otherMatchCount: number
  /** All raw evaluation rows for this client, sorted best-first */
  allMatches: Client[]
  /** Agent assigned to this client */
  assignedAgent?: { id: string; name: string; initials: string } | null
  /** Relationship lifecycle stage */
  relationshipStage: string
  /** WhatsApp phone number */
  whatsappNumber?: string | null
}

export interface Property {
  id: string
  name: string
  address: string
  neighborhood: string
  value: number
  status: "LISTED" | "PENDING" | "UNDER OFFER" | "CLOSED"
  imageUrl?: string
  /** ISO timestamp of the last simulated price change (from last_price_change_at column) */
  lastPriceChangeAt?: string
  /** Fractional change, e.g. 0.045 = +4.5%, -0.03 = -3% (from last_price_change_pct column) */
  lastPriceChangePct?: number
  /** Rich listing specs (null if migration not yet run) */
  bedrooms?: number | null
  bathrooms?: number | null
  sqft?: number | null
  propertyType?: string | null   // 'condo'|'terrace'|'semi-d'|'bungalow'|'serviced_apt'
  furnishing?: string | null     // 'fully'|'partially'|'unfurnished'
  tenure?: string | null         // 'freehold'|'leasehold'
  ownerClientId?: string | null
  ownerName?: string | null
  closedAt?: string | null
  /** Agent assigned to this property */
  assignedAgent?: { id: string; name: string; initials: string } | null
}

export const DOMAIN_LABELS = {
  entityUnit: "Robot",
  entityUnitPlural: "Robots",
  clientEntity: "Company",
  clientEntityPlural: "Companies",
  valueLabel: "Unit Cost",
  budgetLabel: "Procurement Budget",
  neighborhoodLabel: "Target Environment",
  engagementLabel: "Demo Sessions",
  viewingAction: "Demo",
  inviteAction: "Outreach Pitch",
  shortlistAction: "Find Likely Adopters",
}

export const TIER_LABEL: Record<Tier, string> = {
  TIER_1: "TIER 1 — HIGH-FIT PROSPECT",
  TIER_2: "TIER 2 — POSSIBLE-FIT PROSPECT",
  TIER_3: "TIER 3 — LOW-FIT PROSPECT",
}

export const TIER_SHORT: Record<Tier, string> = {
  TIER_1: "HIGH-FIT",
  TIER_2: "POSSIBLE-FIT",
  TIER_3: "LOW-FIT",
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
  ml_probability?: number | null
  clients:
    | {
        id: string
        name: string
        stated_budget?: number
        preferred_neighborhood?: string
        past_viewings?: number
        financing_status?: string | null
        move_in_timeline?: string | null
        property_type_preference?: string | null
        secondary_neighborhood?: string | null
        agent_notes?: string | null
        assigned_agent_id?: string | null
        relationship_stage?: string | null
        whatsapp_number?: string | null
        agents?: { id: string; name: string; initials: string } | { id: string; name: string; initials: string }[] | null
      }
    | {
        id: string
        name: string
        stated_budget?: number
        preferred_neighborhood?: string
        past_viewings?: number
        financing_status?: string | null
        move_in_timeline?: string | null
        property_type_preference?: string | null
        secondary_neighborhood?: string | null
        agent_notes?: string | null
        assigned_agent_id?: string | null
        relationship_stage?: string | null
        whatsapp_number?: string | null
        agents?: { id: string; name: string; initials: string } | { id: string; name: string; initials: string }[] | null
      }[]
    | null
  properties:
    | {
        id: string
        address: string
        neighborhood: string
        property_value: number
        bedrooms?: number | null
        bathrooms?: number | null
        sqft?: number | null
        property_type?: string | null
        furnishing?: string | null
        tenure?: string | null
      }
    | {
        id: string
        address: string
        neighborhood: string
        property_value: number
        bedrooms?: number | null
        bathrooms?: number | null
        sqft?: number | null
        property_type?: string | null
        furnishing?: string | null
        tenure?: string | null
      }[]
    | null
}

export interface PropertyRow {
  id: string
  address: string
  neighborhood: string
  property_value: number
  image_url?: string
  last_price_change_at?: string | null
  last_price_change_pct?: number | null
  bedrooms?: number | null
  bathrooms?: number | null
  sqft?: number | null
  property_type?: string | null
  furnishing?: string | null
  tenure?: string | null
  status?: string | null
  owner_client_id?: string | null
  closed_at?: string | null
  clients?: { name: string } | { name: string }[] | null
  assigned_agent_id?: string | null
  agents?: { id: string; name: string; initials: string } | { id: string; name: string; initials: string }[] | null
}

function unwrapRelation<T>(value: T | T[] | null): T | null {
  if (value == null) return null
  return Array.isArray(value) ? (value[0] ?? null) : value
}

export function mapEvaluationToClient(row: PipelineEvaluationRow): Client | null {
  const client = unwrapRelation(row.clients)
  const property = unwrapRelation(row.properties)
  if (!client || !property) return null

  const agentRaw = unwrapRelation(client.agents ?? null)

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
    mlProbability: row.ml_probability != null ? Number(row.ml_probability) : null,
    assignedAgent: agentRaw ? { id: agentRaw.id, name: agentRaw.name, initials: agentRaw.initials } : null,
    relationshipStage: client.relationship_stage || "new",
    whatsappNumber: client.whatsapp_number ?? null,
  }
}

export function mapPropertyRow(row: PropertyRow, index: number): Property {
  const statuses: Property["status"][] = ["LISTED", "PENDING", "UNDER OFFER"]
  const owner = unwrapRelation(row.clients)
  const agentRaw = unwrapRelation(row.agents ?? null)
  const validStatus = row.status === "CLOSED" || row.status === "LISTED" || row.status === "PENDING" || row.status === "UNDER OFFER"
    ? row.status
    : statuses[index % statuses.length]

  return {
    id: row.id,
    name: row.address,
    address: row.address,
    neighborhood: row.neighborhood,
    value: row.property_value,
    status: validStatus,
    imageUrl: row.image_url ?? undefined,
    lastPriceChangeAt:  row.last_price_change_at  ?? undefined,
    lastPriceChangePct: row.last_price_change_pct  ?? undefined,
    // Rich listing specs (null if migration not yet run)
    bedrooms:     row.bedrooms     ?? null,
    bathrooms:    row.bathrooms    ?? null,
    sqft:         row.sqft         ?? null,
    propertyType: row.property_type ?? null,
    furnishing:   row.furnishing   ?? null,
    tenure:       row.tenure       ?? null,
    ownerClientId: row.owner_client_id ?? null,
    ownerName:     owner?.name ?? null,
    closedAt:      row.closed_at ?? null,
    assignedAgent: agentRaw ? { id: agentRaw.id, name: agentRaw.name, initials: agentRaw.initials } : null,
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
