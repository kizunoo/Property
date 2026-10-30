import {
  simulate,
  DEFAULT_CONSTANTS,
  priceAtTick,
  type SimPair,
} from "./market-sim"

export type PriceKind = "real" | "simulated" | "indicative" | "none"

export interface DisplayPriceResult {
  value: number | null
  kind: PriceKind
}

function isValidPositive(n: unknown): n is number {
  return typeof n === "number" && Number.isFinite(n) && n > 0
}

/**
 * Returns the effective display price and kind.
 * Order: real, then simulated, then indicative, then none.
 * Only positive finite numbers are valid.
 */
export function displayPrice(
  realPrice: unknown,
  indicativePrice: unknown,
  simulatedPrice?: unknown,
): DisplayPriceResult {
  const r =
    typeof realPrice === "number"
      ? realPrice
      : realPrice !== null && realPrice !== undefined
      ? Number(realPrice)
      : NaN

  if (isValidPositive(r)) {
    return { value: r, kind: "real" }
  }

  const sim =
    typeof simulatedPrice === "number"
      ? simulatedPrice
      : simulatedPrice !== null && simulatedPrice !== undefined
      ? Number(simulatedPrice)
      : NaN

  if (isValidPositive(sim)) {
    return { value: sim, kind: "simulated" }
  }

  const ind =
    typeof indicativePrice === "number"
      ? indicativePrice
      : indicativePrice !== null && indicativePrice !== undefined
      ? Number(indicativePrice)
      : NaN

  if (isValidPositive(ind)) {
    return { value: ind, kind: "indicative" }
  }

  return { value: null, kind: "none" }
}

export interface RobotWithIndicative {
  id: string
  indicativePriceMyr?: number | null
  indicative_price_myr?: number | null
}

export function simulatedPriceMap(
  robots: RobotWithIndicative[],
  tick: number,
): Record<string, number | null> {
  const map: Record<string, number | null> = {}
  for (const r of robots) {
    const ind = r.indicativePriceMyr ?? r.indicative_price_myr ?? null
    map[r.id] = priceAtTick(ind, r.id, tick)
  }
  return map
}

/** Formats a numeric value into "RM 133,000" style text. */
export function formatRM(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "RM 0"
  }
  return `RM ${Math.round(value).toLocaleString("en-US")}`
}

export interface PotentialPipelineResult {
  total: number
  robotsUsed: number
  robotsExcluded: number
}

/**
 * Computes potential pipeline if every prospect adopted, using Base scenario (multiplier = 1).
 * Calls simulate from lib/market-sim.
 */
export function potentialPipeline(
  pairs: SimPair[],
  displayPriceByRobotId: Record<string, number | null | undefined>,
): PotentialPipelineResult {
  const sim = simulate(pairs, displayPriceByRobotId, 1, DEFAULT_CONSTANTS)
  const allRobotIds = new Set(pairs.map((p) => p.robotId))
  const robotsExcluded = sim.excludedRobotIds.length
  const robotsUsed = allRobotIds.size - robotsExcluded

  return {
    total: sim.totalValue,
    robotsUsed,
    robotsExcluded,
  }
}

