import {
  simulate,
  DEFAULT_CONSTANTS,
  priceAtTick,
  validPrice,
  type SimPair,
} from "./market-sim"
import { applyDemoProbability } from "./demo-probability"

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

export interface DemoProjectionResult {
  active: number
  projected: number
}

/**
 * Computes demo projection active pipeline and projected revenue.
 * Falls back to 0.10 if closeRate is not a finite number in [0, 1].
 * Both values 0 if potentialTotal is not a finite number > 0.
 */
export function demoProjection(
  potentialTotal: unknown,
  closeRate: unknown,
): DemoProjectionResult {
  const tot = typeof potentialTotal === "number" && Number.isFinite(potentialTotal) && potentialTotal > 0
    ? potentialTotal
    : 0

  if (tot === 0) {
    return { active: 0, projected: 0 }
  }

  const rate = typeof closeRate === "number" && Number.isFinite(closeRate) && closeRate >= 0 && closeRate <= 1
    ? closeRate
    : 0.10

  return {
    active: tot,
    projected: Math.round(tot * rate),
  }
}

/**
 * Parses a string like "10%" or "12.5%" into 0.10 or 0.125.
 * Returns null if it cannot parse.
 */
export function closeRateFromPct(text: unknown): number | null {
  if (typeof text !== "string") return null
  const trimmed = text.trim()
  if (!trimmed.endsWith("%")) return null
  const numPart = trimmed.slice(0, -1).trim()
  if (numPart.length === 0) return null
  const val = Number(numPart)
  if (!Number.isFinite(val) || val < 0) return null
  return val / 100
}

export interface DemoStrategyInput {
  untapped: number
  robotsUsed: number
  potentialTotal: number
  projected: number
  closeRatePct: string
}

/**
 * Builds demo strategy narrative using exact numbers passed in.
 */
export function demoStrategyText(input: DemoStrategyInput): string {
  const { untapped, robotsUsed, potentialTotal, projected, closeRatePct } = input
  const potFormatted = formatRM(potentialTotal)
  const projFormatted = formatRM(projected)
  return `No active deals yet. If all ${untapped} untapped prospects adopted their best-fit robot, the demo potential pipeline is ${potFormatted} across ${robotsUsed} robots (demo estimate), about ${projFormatted} at the ${closeRatePct} close rate. Run the Shortlist Builder on the top robots and work the five outreach contacts below to start converting it.`
}

export interface DisplayPriceByNameEntry {
  value: number | null
  kind: PriceKind
}

/**
 * Returns the displayed price text for a robot name, or null if unknown or invalid price.
 */
export function priceTextForRobotName(
  name: unknown,
  byName?: Record<string, DisplayPriceByNameEntry | undefined> | null,
): string | null {
  if (typeof name !== "string" || !byName) return null
  const trimmed = name.trim()
  const entry = byName[trimmed] || byName[name]
  if (!entry || entry.value === null || entry.value === undefined || !Number.isFinite(entry.value) || entry.value <= 0) {
    return null
  }
  const formatted = formatRM(entry.value)
  if (entry.kind === "simulated") {
    return `${formatted} demo estimate, simulated`
  }
  if (entry.kind === "indicative") {
    return `${formatted} demo estimate`
  }
  return formatted
}

export interface DemoStatsResult {
  pipelineTotal: number
  companies: number
  highFit: number
  tier2: number
  tier3: number
  avgProbability: number
  fleetTotal: number
  robotsPriced: number
}

/**
 * Computes demo statistics for dashboard stat cards using Base scenario (multiplier = 1).
 * Pure function: deterministic calculation, no timers, no storage, no side effects.
 */
export function demoStats(
  pairs: SimPair[],
  displayPriceByRobotId: Record<string, number | null | undefined>,
  robots?: Array<{ id: string } | string> | null,
): DemoStatsResult {
  const COMPANY_FIELD = "companyId"
  const ROBOT_FIELD = "robotId"
  const PROB_FIELD = "probability"

  const demoPairs = applyDemoProbability(pairs, COMPANY_FIELD, ROBOT_FIELD, PROB_FIELD)
  const sim = simulate(demoPairs, displayPriceByRobotId, 1, DEFAULT_CONSTANTS)
  const companies = sim.rows.length
  const highFit = sim.tierCounts[1]
  const tier2 = sim.tierCounts[2]
  const tier3 = sim.tierCounts[3]
  const avgProbability =
    companies > 0
      ? sim.rows.reduce((sum, r) => sum + r.probability, 0) / companies
      : 0

  let fleetTotal = 0
  let robotsPriced = 0

  if (robots && Array.isArray(robots) && robots.length > 0) {
    for (const rob of robots) {
      const id = typeof rob === "string" ? rob : rob.id
      const p = validPrice(displayPriceByRobotId[id])
      if (p !== null) {
        fleetTotal += p
        robotsPriced += 1
      }
    }
  } else {
    for (const val of Object.values(displayPriceByRobotId)) {
      const p = validPrice(val)
      if (p !== null) {
        fleetTotal += p
        robotsPriced += 1
      }
    }
  }

  return {
    pipelineTotal: sim.totalValue,
    companies,
    highFit,
    tier2,
    tier3,
    avgProbability,
    fleetTotal,
    robotsPriced,
  }
}

