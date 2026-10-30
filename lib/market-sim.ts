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

// ------------------------------------------------------------------
// Price Fluctuation Simulation (Ported from market_fluct_reference.ts)
// ------------------------------------------------------------------

export type VolLevel = "low" | "medium" | "high";

export interface VolParams {
  sigma: number; // monthly volatility of log price (0.05 = about 5% a month)
  drift: number; // monthly drift of log price (0 = no trend)
}

export const VOLATILITY: Record<VolLevel, VolParams> = {
  low: { sigma: 0.02, drift: 0 },
  medium: { sigma: 0.05, drift: 0 },
  high: { sigma: 0.1, drift: 0 },
};

// Pulls price back toward its starting level so paths do not wander off forever.
export const REVERSION = 0.1;
// Hard bounds as a multiple of the starting price.
export const MIN_MULT = 0.4;
export const MAX_MULT = 2.5;

export const MAX_MONTHS = 24;
export const MAX_TRIALS = 500;

// Seeded generator so a run is repeatable. Same seed gives the same result.
export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// Standard normal draw (Box-Muller) from a uniform generator.
export function normal(rng: () => number): number {
  let u = 0;
  while (u === 0) u = rng();
  const v = rng();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

export function validStart(p: unknown): p is number {
  return typeof p === "number" && Number.isFinite(p) && p > 0;
}

// One price path of length months + 1 (index 0 is the starting price).
export function pricePath(
  start: number,
  months: number,
  vol: VolParams,
  rng: () => number,
): number[] {
  const path = [start];
  const lnStart = Math.log(start);
  let ln = lnStart;
  for (let m = 1; m <= months; m++) {
    const z = normal(rng);
    ln =
      ln +
      REVERSION * (lnStart - ln) +
      vol.drift -
      0.5 * vol.sigma * vol.sigma +
      vol.sigma * z;
    let p = Math.exp(ln);
    const lo = start * MIN_MULT;
    const hi = start * MAX_MULT;
    if (p < lo) p = lo;
    if (p > hi) p = hi;
    ln = Math.log(p);
    path.push(p);
  }
  return path;
}

export function percentile(sortedAsc: number[], q: number): number {
  if (sortedAsc.length === 0) return 0;
  const idx = (sortedAsc.length - 1) * q;
  const lo = Math.floor(idx);
  const hi = Math.ceil(idx);
  if (lo === hi) return sortedAsc[lo];
  return sortedAsc[lo] + (sortedAsc[hi] - sortedAsc[lo]) * (idx - lo);
}

export interface FluctInput {
  // robotId -> starting price in RM, or null/undefined/invalid = no price assumed (excluded)
  startPrices: Record<string, number | null | undefined>;
  months: number; // clamped to 1..MAX_MONTHS
  trials: number; // clamped to 1..MAX_TRIALS
  vol: VolLevel;
  seed: number;
  // Injected: total simulated pipeline in RM for one set of prices.
  valueFn: (prices: Record<string, number>) => number;
}

export interface FluctMonth {
  month: number;
  p10: number;
  p50: number;
  p90: number;
}

export interface FluctResult {
  months: FluctMonth[]; // length months + 1, index 0 = today
  medianPrices: Record<string, number[]>; // per robot, length months + 1
  robotsSimulated: number;
  robotsExcluded: number;
  trials: number;
}

function clampInt(n: number, lo: number, hi: number): number {
  if (!Number.isFinite(n)) return lo;
  return Math.min(hi, Math.max(lo, Math.floor(n)));
}

export function runFluctuation(input: FluctInput): FluctResult {
  const months = clampInt(input.months, 1, MAX_MONTHS);
  const trials = clampInt(input.trials, 1, MAX_TRIALS);
  const vol = VOLATILITY[input.vol] ?? VOLATILITY.medium;
  const rng = mulberry32(input.seed);

  const ids = Object.keys(input.startPrices);
  const priced = ids.filter((id) => validStart(input.startPrices[id]));
  const excluded = ids.length - priced.length;

  const perMonthValues: number[][] = Array.from({ length: months + 1 }, () => []);
  const perRobotMonth: Record<string, number[][]> = {};
  for (const id of priced) {
    perRobotMonth[id] = Array.from({ length: months + 1 }, () => []);
  }

  for (let t = 0; t < trials; t++) {
    const paths: Record<string, number[]> = {};
    for (const id of priced) {
      const p = pricePath(input.startPrices[id] as number, months, vol, rng);
      paths[id] = p;
      for (let m = 0; m <= months; m++) perRobotMonth[id][m].push(p[m]);
    }
    for (let m = 0; m <= months; m++) {
      const snap: Record<string, number> = {};
      for (const id of priced) snap[id] = paths[id][m];
      perMonthValues[m].push(input.valueFn(snap));
    }
  }

  const out: FluctMonth[] = perMonthValues.map((vals, m) => {
    const s = vals.slice().sort((a, b) => a - b);
    return {
      month: m,
      p10: percentile(s, 0.1),
      p50: percentile(s, 0.5),
      p90: percentile(s, 0.9),
    };
  });

  const medianPrices: Record<string, number[]> = {};
  for (const id of priced) {
    medianPrices[id] = perRobotMonth[id].map((vals) =>
      percentile(vals.slice().sort((a, b) => a - b), 0.5),
    );
  }

  return {
    months: out,
    medianPrices,
    robotsSimulated: priced.length,
    robotsExcluded: excluded,
    trials,
  };
}

