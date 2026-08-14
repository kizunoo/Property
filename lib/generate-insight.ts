import type { Client, Tier } from "./pipeline-data"

interface TierSummary {
  tier: Tier
  count: number
  total_expected_value: number
  avg_probability: number
}

interface InsightPayload {
  total_clients: number
  total_expected_value: number
  avg_probability: number
  tiers: TierSummary[]
  neighborhoods: { name: string; count: number; total_ex: number }[]
  active_filters: { tier: string; neighborhood: string }
}

export async function generateInsight(
  clients: Client[],
  activeFilters: { tier: string; neighborhood: string },
): Promise<string> {
  if (clients.length === 0) {
    return "No clients match the current filter — try broadening your selection."
  }

  const TIERS: Tier[] = ["TIER_1", "TIER_2", "TIER_3"]

  const tiers: TierSummary[] = TIERS.map((tier) => {
    const subset = clients.filter((c) => c.tier === tier)
    const totalEx = subset.reduce((s, c) => s + c.expectedValue, 0)
    const avgProb = subset.length > 0 ? subset.reduce((s, c) => s + c.probability, 0) / subset.length : 0
    return { tier, count: subset.length, total_expected_value: totalEx, avg_probability: avgProb }
  })

  // Neighbourhood aggregation (property neighbourhood stored as c.agent)
  const nbhdMap = new Map<string, { count: number; total_ex: number }>()
  for (const c of clients) {
    const n = c.agent
    const cur = nbhdMap.get(n) ?? { count: 0, total_ex: 0 }
    nbhdMap.set(n, { count: cur.count + 1, total_ex: cur.total_ex + c.expectedValue })
  }
  const neighborhoods = Array.from(nbhdMap.entries()).map(([name, v]) => ({
    name,
    count: v.count,
    total_ex: v.total_ex,
  }))

  const payload: InsightPayload = {
    total_clients: clients.length,
    total_expected_value: clients.reduce((s, c) => s + c.expectedValue, 0),
    avg_probability: clients.reduce((s, c) => s + c.probability, 0) / clients.length,
    tiers,
    neighborhoods,
    active_filters: activeFilters,
  }

  const res = await fetch("/api/insight", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Unknown error" }))
    throw new Error(err.detail ?? "Insight generation failed")
  }

  const data = await res.json()
  return data.insight as string
}
