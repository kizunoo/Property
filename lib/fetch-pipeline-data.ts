import { getSupabase, isSupabaseConfigured } from "@/lib/supabaseClient"
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

export async function fetchPipelineClients(): Promise<Client[]> {
  assertSupabaseConfigured()

  const { data, error } = await getSupabase()
    .from("pipeline_evaluations")
    .select(
      `
      id,
      ai_probability,
      expected_value,
      segment_tier,
      clients ( id, name, stated_budget, preferred_neighborhood, past_viewings ),
      properties ( id, address, neighborhood, property_value )
    `,
    )
    .order("expected_value", { ascending: false })
    .range(0, 4999)

  if (error) {
    throw new Error(error.message)
  }

  return ((data as unknown as PipelineEvaluationRow[]) ?? [])
    .map(mapEvaluationToClient)
    .filter((client): client is Client => client !== null)
}

/**
 * Fetches all pipeline evaluations and deduplicates them to one row per client.
 * Each row shows the best-match property (highest E(x)).
 */
export async function fetchDeduplicatedClients(): Promise<DeduplicatedClient[]> {
  const allRows = await fetchPipelineClients()

  // Group by real client UUID (clientDbId) — correct identity, not a name proxy
  const byClientId = new Map<string, Client[]>()
  for (const row of allRows) {
    const existing = byClientId.get(row.clientDbId) ?? []
    existing.push(row)
    byClientId.set(row.clientDbId, existing)
  }

  const result: DeduplicatedClient[] = []
  for (const [clientDbId, rows] of byClientId) {
    // Sort all rows for this client by E(x) descending
    const sorted = [...rows].sort((a, b) => b.expectedValue - a.expectedValue)
    const best = sorted[0]
    result.push({
      clientId:  clientDbId,     // real UUID from the clients table
      name:      best.name,
      initials:  best.initials,
      tier:      best.tier,
      statedBudget:          best.statedBudget ?? 0,
      preferredNeighborhood: best.preferredNeighborhood ?? "",
      pastViewings:          best.pastViewings ?? 0,
      bestMatch: {
        evalId:        best.id,
        propertyId:    best.propertyDbId,  // real UUID from properties table
        property:      best.property,
        propertyValue: best.propertyValue,
        probability:   best.probability,
        expectedValue: best.expectedValue,
        neighborhood:  best.agent,
      },
      otherMatchCount: sorted.length - 1,
      allMatches: sorted,
    })
  }

  // Sort deduped list by best E(x) descending
  result.sort((a, b) => b.bestMatch.expectedValue - a.bestMatch.expectedValue)
  return result
}

export async function fetchProperties(): Promise<Property[]> {
  assertSupabaseConfigured()

  const { data, error } = await getSupabase()
    .from("properties")
    .select("id, address, neighborhood, property_value, image_url")
    .order("property_value", { ascending: false })

  if (error) {
    // If the image_url column hasn't been added to Supabase yet, fallback gracefully
    if (error.message.includes("image_url") || error.code === "PGRST204") {
      const fallback = await getSupabase()
        .from("properties")
        .select("id, address, neighborhood, property_value")
        .order("property_value", { ascending: false })
      if (!fallback.error && fallback.data) {
        return (fallback.data as PropertyRow[]).map(mapPropertyRow)
      }
    }
    throw new Error(error.message)
  }

  return ((data as PropertyRow[]) ?? []).map(mapPropertyRow)
}
