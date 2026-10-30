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

// ------------------------------------------------------------------
// Time-Based Seeded Simulation (Phase 12L)
// ------------------------------------------------------------------

export const SIM_SEED = 20261030;
export const SIM_EPOCH_MS = Date.UTC(2026, 9, 23, 0, 0, 0);
export const TICK_MIN_GAP_MIN = 30;
export const TICK_MAX_GAP_MIN = 120;
export const TICK_SIGMA = 0.012;
export const TICK_REVERSION = 0.03;
export const MAX_TICKS = 20000;

export function hash32(...parts: (string | number)[]): number {
  const text = parts.join(":");
  let h = 0x811c9dc5 >>> 0;
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h >>> 0;
}

export function tickGapMs(k: number): number {
  if (k < 1) return 0;
  const rng = mulberry32(hash32(SIM_SEED, k));
  const r = rng();
  const min = TICK_MIN_GAP_MIN + Math.floor(r * (TICK_MAX_GAP_MIN - TICK_MIN_GAP_MIN + 1));
  return min * 60 * 1000;
}

// Precompute cumulative tick times for O(1) lookup and O(log N) binary search
const TICK_TIME_TABLE = new Float64Array(MAX_TICKS + 1);
TICK_TIME_TABLE[0] = SIM_EPOCH_MS;
for (let i = 1; i <= MAX_TICKS; i++) {
  TICK_TIME_TABLE[i] = TICK_TIME_TABLE[i - 1] + tickGapMs(i);
}

export function tickTimeMs(k: number): number {
  if (k <= 0) return SIM_EPOCH_MS;
  if (k >= MAX_TICKS) return TICK_TIME_TABLE[MAX_TICKS];
  return TICK_TIME_TABLE[k];
}

export function currentTick(nowMs: number): number {
  if (!Number.isFinite(nowMs) || nowMs <= SIM_EPOCH_MS) {
    return 0;
  }
  if (nowMs >= TICK_TIME_TABLE[MAX_TICKS]) {
    return MAX_TICKS;
  }
  let lo = 0;
  let hi = MAX_TICKS;
  let ans = 0;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (TICK_TIME_TABLE[mid] <= nowMs) {
      ans = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return ans;
}

export function nextTickMs(nowMs: number): number {
  const curr = currentTick(nowMs);
  return tickTimeMs(curr + 1);
}

export function priceAtTick(
  startPrice: unknown,
  robotId: string,
  tick: number,
): number | null {
  if (!validStart(startPrice) || tick < 0) return null;
  const round100 = (v: number) => Math.round(v / 100) * 100;
  if (tick === 0) return round100(startPrice);

  const lnStart = Math.log(startPrice);
  let ln = lnStart;
  let p = startPrice;
  const lo = startPrice * MIN_MULT;
  const hi = startPrice * MAX_MULT;

  for (let step = 1; step <= tick; step++) {
    const rng = mulberry32(hash32(SIM_SEED, robotId, step));
    const z = normal(rng);
    ln =
      ln +
      TICK_REVERSION * (lnStart - ln) -
      0.5 * TICK_SIGMA * TICK_SIGMA +
      TICK_SIGMA * z;
    p = Math.exp(ln);
    if (p < lo) p = lo;
    if (p > hi) p = hi;
    ln = Math.log(p);
  }
  return round100(p);
}

export interface PriceHistoryPoint {
  tick: number;
  timeMs: number;
  price: number;
}

export function priceHistory(
  startPrice: unknown,
  robotId: string,
  tick: number,
  maxPoints: number,
): PriceHistoryPoint[] {
  if (!validStart(startPrice) || tick < 0 || maxPoints <= 0) return [];
  const round100 = (v: number) => Math.round(v / 100) * 100;
  const count = Math.min(maxPoints, tick + 1);
  const startTick = tick - count + 1;

  const result: PriceHistoryPoint[] = [];
  const lnStart = Math.log(startPrice);
  let ln = lnStart;
  let p = startPrice;
  const lo = startPrice * MIN_MULT;
  const hi = startPrice * MAX_MULT;

  if (0 >= startTick) {
    result.push({ tick: 0, timeMs: tickTimeMs(0), price: round100(startPrice) });
  }

  for (let step = 1; step <= tick; step++) {
    const rng = mulberry32(hash32(SIM_SEED, robotId, step));
    const z = normal(rng);
    ln =
      ln +
      TICK_REVERSION * (lnStart - ln) -
      0.5 * TICK_SIGMA * TICK_SIGMA +
      TICK_SIGMA * z;
    p = Math.exp(ln);
    if (p < lo) p = lo;
    if (p > hi) p = hi;
    ln = Math.log(p);

    if (step >= startTick) {
      result.push({ tick: step, timeMs: tickTimeMs(step), price: round100(p) });
    }
  }

  return result;
}


