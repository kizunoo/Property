export type SimPair = {
  companyId: string;
  companyName: string;
  robotId: string;
  probability: number; // 0..1
};

export type SimConstants = {
  tier1Ev: number;
  tier1Prob: number;
  tier2Prob: number;
};

export const DEFAULT_CONSTANTS: SimConstants = {
  tier1Ev: 50000,
  tier1Prob: 0.65,
  tier2Prob: 0.35,
};

export const SCENARIOS = [
  { name: "Low", multiplier: 0.7 },
  { name: "Base", multiplier: 1 },
  { name: "High", multiplier: 1.3 },
] as const;

export function clamp01(n: number): number {
  if (!Number.isFinite(n)) return 0;
  return Math.min(1, Math.max(0, n));
}

/** A usable assumed price: finite and > 0. Anything else counts as "no price". */
export function validPrice(n: unknown): number | null {
  return typeof n === "number" && Number.isFinite(n) && n > 0 ? n : null;
}

/** Starting value for a robot's price box: real price, else indicative, else EMPTY. Never a default. */
export function startingPrice(
  real: number | null | undefined,
  indicative: number | null | undefined,
): number | null {
  return validPrice(real) ?? validPrice(indicative);
}

export function simTier(
  ev: number,
  p: number,
  c: SimConstants = DEFAULT_CONSTANTS,
): 1 | 2 | 3 {
  if (ev > c.tier1Ev && p >= c.tier1Prob) return 1;
  if (p >= c.tier2Prob) return 2;
  return 3;
}

export type SimRow = {
  companyId: string;
  companyName: string;
  robotId: string;
  probability: number;
  ev: number;
  tier: 1 | 2 | 3;
};

export type SimResult = {
  rows: SimRow[]; // one per company: the robot with the highest simulated E(x)
  totalValue: number;
  tierCounts: { 1: number; 2: number; 3: number };
  excludedRobotIds: string[]; // robots with no assumed price
  companiesWithoutPrice: number; // companies whose every pair was excluded
};

export function simulate(
  pairs: SimPair[],
  prices: Record<string, number | null | undefined>,
  multiplier: number,
  constants: SimConstants = DEFAULT_CONSTANTS,
): SimResult {
  const best = new Map<string, SimRow>();
  const allCompanies = new Set<string>();
  const robots = new Set<string>();
  for (const pair of pairs) {
    allCompanies.add(pair.companyId);
    robots.add(pair.robotId);
    const price = validPrice(prices[pair.robotId]);
    if (price == null) continue;
    const p = clamp01(pair.probability * multiplier);
    const ev = p * price;
    const row: SimRow = { ...pair, probability: p, ev, tier: simTier(ev, p, constants) };
    const cur = best.get(pair.companyId);
    // highest E(x); ties: higher probability; then the first pair seen (stable)
    if (!cur || ev > cur.ev || (ev === cur.ev && p > cur.probability)) {
      best.set(pair.companyId, row);
    }
  }
  const rows = [...best.values()].sort((a, b) => b.ev - a.ev);
  const tierCounts = { 1: 0, 2: 0, 3: 0 };
  let totalValue = 0;
  for (const r of rows) {
    tierCounts[r.tier] += 1;
    totalValue += r.ev;
  }
  const excludedRobotIds = [...robots].filter(
    (id) => validPrice(prices[id]) == null,
  );
  return {
    rows,
    totalValue,
    tierCounts,
    excludedRobotIds,
    companiesWithoutPrice: allCompanies.size - rows.length,
  };
}

export interface SimClientInput {
  clientDbId: string;
  name: string;
  propertyDbId: string;
  probability: number;
}

export function toSimPairs(clients: SimClientInput[]): SimPair[] {
  return clients.map((c) => {
    const p = c.probability > 1 ? c.probability / 100 : c.probability;
    return {
      companyId: c.clientDbId,
      companyName: c.name,
      robotId: c.propertyDbId,
      probability: clamp01(p),
    };
  });
}

