"use client"

import { useMemo, useState } from "react"
import { Calculator, RotateCcw, AlertCircle, Info, Sparkles } from "lucide-react"
import {
  type SimPair,
  type SimClientInput,
  SCENARIOS,
  startingPrice,
  simulate,
  validPrice,
  toSimPairs,
} from "@/lib/market-sim"
import { currency } from "@/lib/pipeline-data"

export interface MarketSimulatorRobot {
  id: string
  address?: string
  name?: string
  value?: number | null
  propertyValue?: number | null
  indicativePriceMyr?: number | null
  indicativePriceNote?: string | null
}

export interface MarketSimulatorPanelProps {
  pairs: SimPair[] | SimClientInput[]
  robots: MarketSimulatorRobot[]
}

export function MarketSimulatorPanel({ pairs, robots }: MarketSimulatorPanelProps) {
  // Normalize input pairs
  const normalizedPairs: SimPair[] = useMemo(() => {
    if (!Array.isArray(pairs) || pairs.length === 0) return []
    const first = pairs[0] as unknown as Record<string, unknown>
    if ("clientDbId" in first) {
      return toSimPairs(pairs as SimClientInput[])
    }
    return pairs as SimPair[]
  }, [pairs])

  // Initial prices computation
  const getInitialPrices = (): Record<string, string> => {
    const init: Record<string, string> = {}
    for (const r of robots) {
      const real = r.value ?? r.propertyValue ?? null
      const indicative = r.indicativePriceMyr ?? null
      const start = startingPrice(real, indicative)
      init[r.id] = start != null ? String(start) : ""
    }
    return init
  }

  const [prices, setPrices] = useState<Record<string, string>>(() => getInitialPrices())
  const [scenarioIndex, setScenarioIndex] = useState<number>(1) // Base (1x)

  const activeScenario = SCENARIOS[scenarioIndex] || SCENARIOS[1]

  const handleReset = () => {
    setPrices(getInitialPrices())
    setScenarioIndex(1)
  }

  const handlePriceChange = (robotId: string, val: string) => {
    setPrices((prev) => ({ ...prev, [robotId]: val }))
  }

  // Parse numeric prices for simulation
  const numericPrices = useMemo(() => {
    const map: Record<string, number | null> = {}
    for (const r of robots) {
      const str = prices[r.id]
      if (str === undefined || str === null || str.trim() === "") {
        map[r.id] = null
      } else {
        const parsed = Number(str.trim())
        map[r.id] = validPrice(parsed)
      }
    }
    return map
  }, [robots, prices])

  // Run simulation
  const simResult = useMemo(() => {
    return simulate(normalizedPairs, numericPrices, activeScenario.multiplier)
  }, [normalizedPairs, numericPrices, activeScenario.multiplier])

  const anyPriced = useMemo(() => {
    return Object.values(numericPrices).some((p) => p != null)
  }, [numericPrices])

  const robotNameMap = useMemo(() => {
    const map = new Map<string, string>()
    for (const r of robots) {
      map.set(r.id, r.address || r.name || r.id)
    }
    return map
  }, [robots])

  return (
    <div className="overflow-hidden rounded-[var(--radius)] border border-border bg-card shadow-[var(--shadow-sm)]">
      {/* Header */}
      <div className="flex flex-col gap-3 border-b border-border bg-transparent px-5 py-3.5 sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <div className="flex items-center gap-2 text-foreground">
          <Calculator className="h-4 w-4 text-primary" strokeWidth={2} />
          <span className="text-xs font-bold uppercase tracking-wider text-foreground sm:text-sm">
            Market Simulator (What-If)
          </span>
        </div>
        <button
          type="button"
          onClick={handleReset}
          className="inline-flex items-center gap-1.5 self-start rounded-[var(--radius-sm)] border border-border bg-muted/60 px-2.5 py-1 text-xs font-medium text-foreground transition-colors hover:bg-muted"
        >
          <RotateCcw className="h-3.5 w-3.5 text-muted-foreground" />
          <span>Reset</span>
        </button>
      </div>

      <div className="p-4 sm:p-6 space-y-6">
        {/* Permanent Banner */}
        <div className="flex items-start gap-3 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-600 dark:text-amber-400">
          <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
          <span className="font-semibold tracking-wide uppercase">
            SIMULATION: assumed prices and adoption. Not saved. Not a quote.
          </span>
        </div>

        {/* Controls: Scenarios */}
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Adoption Scenario
          </div>
          <div className="inline-flex rounded-md border border-border bg-muted/40 p-1">
            {SCENARIOS.map((sc, idx) => (
              <button
                key={sc.name}
                type="button"
                onClick={() => setScenarioIndex(idx)}
                className={`rounded px-3 py-1 text-xs font-semibold transition-colors ${
                  scenarioIndex === idx
                    ? "bg-background text-foreground shadow-xs"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {sc.name} ({sc.multiplier}x)
              </button>
            ))}
          </div>
        </div>

        {/* Robot Assumed Prices Grid */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Assumed Robot Prices (RM)
            </span>
            <span className="text-[11px] text-muted-foreground">
              Prefilled from real or indicative prices
            </span>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {robots.map((robot) => {
              const name = robot.address || robot.name || robot.id
              const real = robot.value ?? robot.propertyValue ?? null
              const indicative = robot.indicativePriceMyr ?? null
              const currentVal = numericPrices[robot.id]

              let badgeText = "Unpriced"
              let badgeClass = "bg-muted text-muted-foreground border-border"
              if (currentVal != null) {
                if (validPrice(real) === currentVal) {
                  badgeText = "Real quote"
                  badgeClass = "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30"
                } else if (validPrice(indicative) === currentVal) {
                  badgeText = "Indicative"
                  badgeClass = "bg-sky-500/10 text-sky-600 dark:text-sky-400 border-sky-500/30"
                } else {
                  badgeText = "Custom"
                  badgeClass = "bg-violet-500/10 text-violet-600 dark:text-violet-400 border-violet-500/30"
                }
              }

              return (
                <div
                  key={robot.id}
                  className="flex flex-col gap-1.5 rounded-md border border-border bg-muted/20 p-2.5"
                >
                  <div className="flex items-center justify-between gap-1">
                    <span className="truncate text-xs font-medium text-foreground" title={name}>
                      {name}
                    </span>
                    <span
                      className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider ${badgeClass}`}
                    >
                      {badgeText}
                    </span>
                  </div>
                  <div className="relative">
                    <span className="absolute left-2 top-1.5 text-xs font-mono text-muted-foreground">
                      RM
                    </span>
                    <input
                      type="number"
                      min="0"
                      step="1000"
                      placeholder="No price"
                      value={prices[robot.id] ?? ""}
                      onChange={(e) => handlePriceChange(robot.id, e.target.value)}
                      className="w-full rounded border border-input bg-background pl-9 pr-2 py-1 font-mono text-xs text-foreground placeholder:text-muted-foreground/60 focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                    />
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* Results Section */}
        {!anyPriced ? (
          <div className="rounded-lg border border-dashed border-border p-8 text-center text-xs font-medium text-muted-foreground">
            Enter a price for at least one robot
          </div>
        ) : (
          <div className="space-y-4">
            {/* KPI Summary Cards */}
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <div className="rounded-lg border border-border bg-card p-3 shadow-xs">
                <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Simulated Pipeline
                </div>
                <div className="mt-1 font-mono text-lg font-bold text-foreground">
                  {currency(simResult.totalValue)}
                </div>
              </div>
              <div className="rounded-lg border border-border bg-card p-3 shadow-xs">
                <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Tier 1 (VIP)
                </div>
                <div className="mt-1 font-mono text-lg font-bold text-emerald-600 dark:text-emerald-400">
                  {simResult.tierCounts[1]}
                </div>
              </div>
              <div className="rounded-lg border border-border bg-card p-3 shadow-xs">
                <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Tier 2 (Warm)
                </div>
                <div className="mt-1 font-mono text-lg font-bold text-amber-600 dark:text-amber-400">
                  {simResult.tierCounts[2]}
                </div>
              </div>
              <div className="rounded-lg border border-border bg-card p-3 shadow-xs">
                <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Tier 3 (Cold)
                </div>
                <div className="mt-1 font-mono text-lg font-bold text-slate-500">
                  {simResult.tierCounts[3]}
                </div>
              </div>
            </div>

            {/* Coverage / Exclusion Notices */}
            <div className="flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
              <span>
                <strong className="text-foreground">{simResult.excludedRobotIds.length}</strong> robots excluded: no price assumed
              </span>
              <span>&middot;</span>
              <span>
                <strong className="text-foreground">{simResult.companiesWithoutPrice}</strong> companies have no priced robot
              </span>
            </div>

            {/* Top 5 Companies Table */}
            <div className="space-y-2">
              <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-foreground">
                <Sparkles className="h-3.5 w-3.5 text-primary" />
                <span>Top 5 Likely Adopters (Simulated)</span>
              </div>
              <div className="overflow-hidden rounded-md border border-border">
                <table className="w-full text-left text-xs">
                  <thead className="border-b border-border bg-muted/40 font-semibold text-muted-foreground">
                    <tr>
                      <th className="px-3 py-2">Company</th>
                      <th className="px-3 py-2">Best Match Robot</th>
                      <th className="px-3 py-2 text-right">Probability</th>
                      <th className="px-3 py-2 text-right">Simulated E(x)</th>
                      <th className="px-3 py-2 text-center">Sim Tier</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {simResult.rows.slice(0, 5).map((row) => (
                      <tr key={row.companyId} className="hover:bg-muted/20">
                        <td className="px-3 py-2 font-medium text-foreground">
                          {row.companyName}
                        </td>
                        <td className="px-3 py-2 text-muted-foreground">
                          {robotNameMap.get(row.robotId) || row.robotId}
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-foreground">
                          {Math.round(row.probability * 100)}%
                        </td>
                        <td className="px-3 py-2 text-right font-mono font-semibold text-foreground">
                          {currency(row.ev)}
                        </td>
                        <td className="px-3 py-2 text-center">
                          <span
                            className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-bold ${
                              row.tier === 1
                                ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                                : row.tier === 2
                                ? "bg-amber-500/10 text-amber-600 dark:text-amber-400"
                                : "bg-slate-500/10 text-slate-500"
                            }`}
                          >
                            T{row.tier}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* Permanent Note */}
        <div className="flex items-center gap-2 border-t border-border pt-4 text-[11px] text-muted-foreground">
          <Info className="h-3.5 w-3.5 shrink-0 text-muted-foreground/80" />
          <span>
            Adoption probability is the model value times the scenario multiplier. It does not change with price.
          </span>
        </div>
      </div>
    </div>
  )
}

