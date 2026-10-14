import { initialsOf, type Tier } from "@/lib/pipeline-data"

export interface ShortlistEntry {
  clientId:               string
  name:                   string
  initials:               string
  // Core scoring
  probability:            number   // rule-based formula P(Buy)
  formulaScore:           number   // same as probability (aliased for clarity)
  formulaProbability:     number   // explicit formula probability
  mlProbability:          number | null
  blendedScore:           number   // 0.6×formula + 0.4×ml (or 100% formula if no model)
  blendedProbability:     number   // blended P(Buy)
  tier:                   Tier
  expectedValue:          number   // formula-only expected value
  blendedExpectedValue:   number   // ML-adjusted blended expected value (primary sort)
  confidence:             "HIGH" | "MEDIUM" | "LOW"
  // Pick / Skip reasoning
  pickReason:             string   // e.g. "✓ Budget covers asking · ✓ Area match · 2 viewings"
  skipReason:             string   // e.g. "✗ Budget 38% below asking · ✗ Area mismatch"
  // Rich client fields for Compare mode
  statedBudget:           number | null
  preferredNeighborhood:  string | null
  secondaryNeighborhood:  string | null
  pastViewings:           number
  financingStatus:        string | null
  moveInTimeline:         string | null
  propertyTypePreference: string | null
  budgetRatio:            number   // stated_budget / property_value
  pastPurchasesCount?:    number
  pastPurchases?:         any[]
}

const TIMEOUT_MS = 30_000

export async function fetchShortlist(propertyId: string, agentId?: string | null): Promise<ShortlistEntry[]> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS)

  try {
    const url = new URL(`/api/shortlist/${propertyId}`, window.location.origin)
    if (agentId) url.searchParams.set("agent_id", agentId)

    const res = await fetch(url.toString(), {
      signal: controller.signal,
    })

    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err?.error ?? `Request failed (${res.status})`)
    }

    const raw: Array<{
      client_id:                  string
      name:                       string
      probability:                number
      formula_score?:             number
      formula_probability?:       number
      ml_probability:             number | null
      blended_score?:             number
      blended_probability?:       number
      tier:                       Tier
      expected_value:             number
      blended_expected_value?:    number
      confidence:                 "HIGH" | "MEDIUM" | "LOW"
      pick_reason:                string
      skip_reason:                string
      stated_budget:              number | null
      preferred_neighborhood:     string | null
      secondary_neighborhood:     string | null
      past_viewings:              number
      financing_status:           string | null
      move_in_timeline:           string | null
      property_type_preference:   string | null
      budget_ratio:               number
    }> = await res.json()

    return raw.map((r) => {
      const formulaProb = r.formula_probability ?? r.formula_score ?? r.probability
      const blendedProb = r.blended_probability ?? r.blended_score ?? formulaProb
      const blendedEV = r.blended_expected_value ?? r.expected_value

      return {
        clientId:               r.client_id,
        name:                   r.name,
        initials:               initialsOf(r.name),
        probability:            formulaProb,
        formulaScore:           formulaProb,
        formulaProbability:     formulaProb,
        mlProbability:          r.ml_probability ?? null,
        blendedScore:           blendedProb,
        blendedProbability:     blendedProb,
        tier:                   r.tier,
        expectedValue:          r.expected_value,
        blendedExpectedValue:   blendedEV,
        confidence:             r.confidence,
        pickReason:             r.pick_reason ?? "",
        skipReason:             r.skip_reason ?? "",
        statedBudget:           r.stated_budget ?? null,
        preferredNeighborhood:  r.preferred_neighborhood ?? null,
        secondaryNeighborhood:  r.secondary_neighborhood ?? null,
        pastViewings:           r.past_viewings ?? 0,
        financingStatus:        r.financing_status ?? null,
        moveInTimeline:         r.move_in_timeline ?? null,
        propertyTypePreference: r.property_type_preference ?? null,
        budgetRatio:            r.budget_ratio ?? 0,
        pastPurchasesCount:     (r as any).past_purchases_count ?? 0,
        pastPurchases:          (r as any).past_purchases ?? [],
      }
    })
  } catch (err) {
    if ((err as Error).name === "AbortError") {
      throw new Error("Shortlist timed out. Please try again.")
    }
    throw err
  } finally {
    clearTimeout(timer)
  }
}
