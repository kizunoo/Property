import { getSupabase, isSupabaseConfigured } from "@/lib/supabaseClient"
import { compareByEvThenProbability } from "@/lib/price"
import {
  mapEvaluationToClient,
  mapPropertyRow,
  type Client,
  type DeduplicatedClient,
  type PipelineEvaluationRow,
  type Property,
  type PropertyRow,
} from "@/lib/pipeline-data"

function assertSupabaseConfigured() {
  if (!isSupabaseConfigured()) {
    throw new Error(
      "Missing Supabase env vars. Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY (or NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY) in .env.local, then restart the dev server.",
    )
  }
}

// Rich client columns added by rich_profiles_migration.sql
// agents(id,name,initials) is included so assignedAgent badge works immediately after
// the agents_migration.sql runs — Supabase silently ignores unknown relations.
const CLIENT_RICH_COLS = "id, name, stated_budget, preferred_neighborhood, past_viewings, financing_status, move_in_timeline, property_type_preference, secondary_neighborhood, agent_notes, assigned_agent_id, relationship_stage, agents(id, name, initials)"
const PROPERTY_RICH_COLS = "id, address, neighborhood, property_value, bedrooms, bathrooms, sqft, property_type, furnishing, tenure"

export async function fetchPipelineClients(agentId?: string | null): Promise<Client[]> {
  const supabase = getSupabase()

  // Primary query: includes rich profile columns + ml_probability + agents join
  const primaryQuery = supabase
    .from("pipeline_evaluations")
    .select(
      `
      id,
      ai_probability,
      expected_value,
      segment_tier,
      outcome,
      ml_probability,
      clients ( ${CLIENT_RICH_COLS} ),
      properties ( ${PROPERTY_RICH_COLS} )
    `,
    )
    .order("expected_value", { ascending: false, nullsFirst: false })
    .range(0, 4999)

  const { data, error } = agentId
    ? await primaryQuery.eq("clients.assigned_agent_id", agentId)
    : await primaryQuery

  if (error) {
    // Fallback 1: rich cols but without ml_probability (migration not fully run)
    let fallback1Query = supabase
      .from("pipeline_evaluations")
      .select(
        `
        id,
        ai_probability,
        expected_value,
        segment_tier,
        outcome,
        clients ( id, name, stated_budget, preferred_neighborhood, past_viewings, financing_status, move_in_timeline, property_type_preference, secondary_neighborhood, agent_notes, assigned_agent_id, relationship_stage, agents(id, name, initials) ),
        properties ( id, address, neighborhood, property_value, bedrooms, bathrooms, sqft, property_type, furnishing, tenure )
      `,
      )
      .order("expected_value", { ascending: false, nullsFirst: false })
      .range(0, 4999)

    const fallback1 = await fallback1Query

    if (!fallback1.error && fallback1.data) {
      const rows = (fallback1.data as unknown as PipelineEvaluationRow[]) ?? []
      const mapped = rows.map(mapEvaluationToClient).filter((c): c is Client => c !== null)
      return agentId ? mapped.filter((c) => c.assignedAgent?.id === agentId || !agentId) : mapped
    }

    // Fallback 2: minimal (pre-migration)
    const fallback2 = await supabase
      .from("pipeline_evaluations")
      .select(
        `
        id,
        ai_probability,
        expected_value,
        segment_tier,
        outcome,
        clients ( id, name, stated_budget, preferred_neighborhood, past_viewings ),
        properties ( id, address, neighborhood, property_value )
      `,
      )
      .order("expected_value", { ascending: false, nullsFirst: false })
      .range(0, 4999)

    if (fallback2.error) {
      throw new Error(error.message)
    }
    return ((fallback2.data as unknown as PipelineEvaluationRow[]) ?? [])
      .map(mapEvaluationToClient)
      .filter((client): client is Client => client !== null)
  }

  return ((data as unknown as PipelineEvaluationRow[]) ?? [])
    .map(mapEvaluationToClient)
    .filter((client): client is Client => client !== null)
}

/**
 * Fetches all pipeline evaluations and deduplicates them to one row per client.
 * Each row shows the best-match property (highest E(x)).
 * Rich profile fields from the clients table are passed through if available.
 */
export async function fetchDeduplicatedClients(agentId?: string | null): Promise<DeduplicatedClient[]> {
  const allRows = await fetchPipelineClients(agentId)

  // Group by real client UUID (clientDbId) — correct identity, not a name proxy
  const byClientId = new Map<string, Client[]>()
  for (const row of allRows) {
    const existing = byClientId.get(row.clientDbId) ?? []
    existing.push(row)
    byClientId.set(row.clientDbId, existing)
  }

  // We need rich client fields (financing_status, etc.) but they're not on Client rows —
  // fetch all client profiles in one pass so we can hydrate DeduplicatedClient.
  let richClientMap: Record<string, Record<string, unknown>> = {}
  try {
    const { data, error } = await getSupabase()
      .from("clients")
      .select("id, financing_status, move_in_timeline, property_type_preference, secondary_neighborhood, agent_notes, relationship_stage")
    if (!error && data) {
      for (const row of data) {
        richClientMap[row.id] = row
      }
    } else {
      const fallback = await getSupabase()
        .from("clients")
        .select("id, financing_status, move_in_timeline, property_type_preference, secondary_neighborhood, agent_notes, relationship_stage")
      if (fallback.data) {
        for (const row of fallback.data) {
          richClientMap[row.id] = row
        }
      }
    }
  } catch {
    // Non-fatal: rich fields just won't appear until migration is run
  }

  // Fetch verified past property purchases for all clients in one pass
  let pastPurchasesMap: Record<string, any[]> = {}
  try {
    // Attempt with properties(image_url) join
    const withPropJoin = await getSupabase()
      .from("client_past_purchases")
      .select("*, properties(image_url)")
      .order("purchase_year", { ascending: false })

    const purchData = !withPropJoin.error && withPropJoin.data
      ? withPropJoin.data
      : (await getSupabase().from("client_past_purchases").select("*").order("purchase_year", { ascending: false })).data

    if (purchData) {
      for (const row of purchData) {
        const cid = row.client_id
        if (cid) {
          const propRel = Array.isArray(row.properties) ? row.properties[0] : row.properties
          pastPurchasesMap[cid] = pastPurchasesMap[cid] || []
          pastPurchasesMap[cid].push({
            id: row.id,
            clientId: row.client_id,
            propertyId: row.property_id ?? null,
            propertyName: row.property_name,
            neighborhood: row.neighborhood,
            propertyType: row.property_type,
            purchasePrice: Number(row.purchase_price),
            purchaseYear: row.purchase_year ? Number(row.purchase_year) : null,
            purpose: row.purpose,
            notes: row.notes,
            imageUrl: propRel?.image_url ?? null,
          })
        }
      }
    }
  } catch {
    // Non-fatal if table not yet migrated
  }

  const result: DeduplicatedClient[] = []
  for (const [clientDbId, rows] of byClientId) {
    // Sort all rows for this client by E(x) descending
    const sorted = [...rows].sort(compareByEvThenProbability)
    const best  = sorted[0]
    const rich  = richClientMap[clientDbId] ?? {}
    result.push({
      clientId:  clientDbId,
      name:      best.name,
      initials:  best.initials,
      tier:      best.tier,
      statedBudget:          best.statedBudget ?? 0,
      preferredNeighborhood: best.preferredNeighborhood ?? "",
      pastViewings:          best.pastViewings ?? 0,
      // Rich buyer profile (null when migration not yet run)
      financingStatus:         (rich.financing_status as string | null) ?? null,
      moveInTimeline:          (rich.move_in_timeline as string | null) ?? null,
      propertyTypePreference:  (rich.property_type_preference as string | null) ?? null,
      secondaryNeighborhood:   (rich.secondary_neighborhood as string | null) ?? null,
      agentNotes:              (rich.agent_notes as string | null) ?? null,
      pastPurchases:           pastPurchasesMap[clientDbId] ?? [],
      assignedAgent:           best.assignedAgent ?? null,
      relationshipStage:       (rich.relationship_stage as string) || best.relationshipStage || "new",
      whatsappNumber:          ((rich.whatsapp_number as string | null) ?? best.whatsappNumber ?? null) || null,
      bestMatch: {
        evalId:        best.id,
        propertyId:    best.propertyDbId,
        property:      best.property,
        propertyValue: best.propertyValue,
        probability:   best.probability,
        expectedValue: best.expectedValue,
        neighborhood:  best.agent,
        outcome:       best.outcome ?? "pending",
        mlProbability: best.mlProbability ?? null,
      },
      otherMatchCount: sorted.length - 1,
      allMatches: sorted,
    })
  }

  // Sort deduped list by best E(x) descending
  result.sort((a, b) => compareByEvThenProbability(a.bestMatch, b.bestMatch))
  return result
}

export async function fetchProperties(agentId?: string | null): Promise<Property[]> {
  assertSupabaseConfigured()

  const supabase = getSupabase()

  // Shared agent filter helper
  const applyAgentFilter = <T extends object>(q: T) =>
    agentId ? (q as any).eq("assigned_agent_id", agentId) : q

  // Attempt 1: Full set including price-change columns (may fail if migration not yet run)
  const attempt1 = await applyAgentFilter(
    supabase
      .from("properties")
      .select("id, address, neighborhood, property_value, image_url, status, owner_client_id, closed_at, last_price_change_at, last_price_change_pct, bedrooms, bathrooms, sqft, property_type, furnishing, tenure, clients(name), assigned_agent_id, agents(id, name, initials), indicative_price_myr, indicative_price_note")
      .order("property_value", { ascending: false, nullsFirst: false })
  )
  if (!attempt1.error && attempt1.data) {
    return (attempt1.data as unknown as PropertyRow[]).map(mapPropertyRow)
  }

  // Attempt 2: Without price-change columns (column may not exist yet), but keep agents join
  const attempt2 = await applyAgentFilter(
    supabase
      .from("properties")
      .select("id, address, neighborhood, property_value, image_url, status, owner_client_id, closed_at, bedrooms, bathrooms, sqft, property_type, furnishing, tenure, clients(name), assigned_agent_id, agents(id, name, initials), indicative_price_myr, indicative_price_note")
      .order("property_value", { ascending: false, nullsFirst: false })
  )
  if (!attempt2.error && attempt2.data) {
    return (attempt2.data as unknown as PropertyRow[]).map(mapPropertyRow)
  }

  // Attempt 3: Without clients join (owner name won't show), but keep agents join
  const attempt3 = await applyAgentFilter(
    supabase
      .from("properties")
      .select("id, address, neighborhood, property_value, image_url, status, owner_client_id, closed_at, bedrooms, bathrooms, sqft, property_type, furnishing, tenure, assigned_agent_id, agents(id, name, initials), indicative_price_myr, indicative_price_note")
      .order("property_value", { ascending: false, nullsFirst: false })
  )
  if (!attempt3.error && attempt3.data) {
    return (attempt3.data as unknown as PropertyRow[]).map(mapPropertyRow)
  }

  // Attempt 4: Rich specs + image_url + agents join
  const attempt4 = await applyAgentFilter(
    supabase
      .from("properties")
      .select("id, address, neighborhood, property_value, image_url, bedrooms, bathrooms, sqft, property_type, furnishing, tenure, assigned_agent_id, agents(id, name, initials), indicative_price_myr, indicative_price_note")
      .order("property_value", { ascending: false, nullsFirst: false })
  )
  if (!attempt4.error && attempt4.data) {
    return (attempt4.data as unknown as PropertyRow[]).map(mapPropertyRow)
  }

  // Attempt 5: Base columns + agents join
  const attempt5 = await applyAgentFilter(
    supabase
      .from("properties")
      .select("id, address, neighborhood, property_value, image_url, assigned_agent_id, agents(id, name, initials), indicative_price_myr, indicative_price_note")
      .order("property_value", { ascending: false, nullsFirst: false })
  )
  if (!attempt5.error && attempt5.data) {
    return (attempt5.data as unknown as PropertyRow[]).map(mapPropertyRow)
  }

  // Attempt 6: Minimal fallback (no agents — badge hidden, but page still loads)
  const attempt6 = await supabase
    .from("properties")
    .select("id, address, neighborhood, property_value")
    .order("property_value", { ascending: false, nullsFirst: false })

  if (!attempt6.error && attempt6.data) {
    return (attempt6.data as unknown as PropertyRow[]).map(mapPropertyRow)
  }

  throw new Error(attempt1.error?.message || "Failed to fetch properties")
}
