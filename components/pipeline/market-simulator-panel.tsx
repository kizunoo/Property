"use client"

import { useMemo, useState } from "react"
import {
  Calculator,
  RotateCcw,
  AlertCircle,
  Info,
  Sparkles,
  TrendingUp,
  Play,
  Shuffle,
} from "lucide-react"
import {
  type SimPair,
  type SimClientInput,
  type VolLevel,
  type FluctResult,
  SCENARIOS,
  startingPrice,
  simulate,
  validPrice,
  toSimPairs,
  runFluctuation,
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

const VOLATILITY_OPTIONS: { level: VolLevel; label: string; desc: string }[] = [
  { level: "low", label: "Low", desc: "about 2% a month" },
  { level: "medium", label: "Medium", desc: "about 5% a month" },
  { level: "high", label: "High", desc: "about 10% a month" },
]

const MONTH_OPTIONS = [6, 12, 24] as const

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

  // Price Fluctuation States
  const [volatility, setVolatility] = useState<VolLevel>("medium")
  const [months, setMonths] = useState<number>(12)
  const [seed, setSeed] = useState<number>(42)
  const [fluctResult, setFluctResult] = useState<FluctResult | null>(null)

  const activeScenario = SCENARIOS[scenarioIndex] || SCENARIOS[1]

  const handleReset = () => {
    setPrices(getInitialPrices())
    setScenarioIndex(1)
    setFluctResult(null)
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

  // Run base simulation
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

  // Run Price Fluctuation simulation
  const handleRunFluct = () => {
    if (!anyPriced) return
    const valueFn = (snapPrices: Record<string, number>) => {
      return simulate(normalizedPairs, snapPrices, activeScenario.multiplier).totalValue
    }
    const res = runFluctuation({
      startPrices: numericPrices,
      months,
      trials: 200,
      vol: volatility,
      seed,
      valueFn,
    })
    setFluctResult(res)
  }

  const handleNewSeed = () => {
    setSeed((prev) => prev + 1)
  }

  // Table rows: month 0 and every 3rd month
  const tableMonths = useMemo(() => {
    if (!fluctResult) return []
    return fluctResult.months.filter((m) => m.month === 0 || m.month % 3 === 0)
  }, [fluctResult])

  // Chart data calculations
  const chartBounds = useMemo(() => {
    if (!fluctResult || fluctResult.months.length === 0) return null
    let min = Infinity
    let max = -Infinity
    for (const m of fluctResult.months) {
      if (m.p10 < min) min = m.p10
      if (m.p90 > max) max = m.p90
    }
    if (!Number.isFinite(min) || !Number.isFinite(max)) return null
    const pad = (max - min) * 0.1 || 1000
    return { min: Math.max(0, min - pad), max: max + pad }
  }, [fluctResult])

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

        {/* ------------------------------------------------------------- */}
        {/* Section: Price Fluctuation Simulator */}
        {/* ------------------------------------------------------------- */}
        <div className="border-t border-border pt-6 space-y-5">
          <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-primary" strokeWidth={2} />
              <h4 className="text-xs font-bold uppercase tracking-wider text-foreground sm:text-sm">
                Price Fluctuation
              </h4>
            </div>
            <p className="text-[11px] text-muted-foreground">
              Prices follow assumed random paths around your starting prices. Not a forecast. Not saved.
            </p>
          </div>

          {/* Controls Bar */}
          <div className="flex flex-wrap items-center gap-4 rounded-lg border border-border bg-muted/20 p-3.5">
            {/* Volatility Selection */}
            <div className="flex flex-col gap-1">
              <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                Monthly Volatility
              </span>
              <div className="inline-flex rounded-md border border-border bg-muted/40 p-0.5">
                {VOLATILITY_OPTIONS.map((vo) => (
                  <button
                    key={vo.level}
                    type="button"
                    onClick={() => setVolatility(vo.level)}
                    className={`rounded px-2.5 py-1 text-xs font-semibold transition-colors ${
                      volatility === vo.level
                        ? "bg-background text-foreground shadow-xs"
                        : "text-muted-foreground hover:text-foreground"
                    }`}
                    title={vo.desc}
                  >
                    {vo.label} ({vo.desc})
                  </button>
                ))}
              </div>
            </div>

            {/* Months Selection */}
            <div className="flex flex-col gap-1">
              <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                Time Horizon
              </span>
              <div className="inline-flex rounded-md border border-border bg-muted/40 p-0.5">
                {MONTH_OPTIONS.map((m) => (
                  <button
                    key={m}
                    type="button"
                    onClick={() => setMonths(m)}
                    className={`rounded px-2.5 py-1 text-xs font-semibold transition-colors ${
                      months === m
                        ? "bg-background text-foreground shadow-xs"
                        : "text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    {m} mos
                  </button>
                ))}
              </div>
            </div>

            {/* Seed Box and New Seed */}
            <div className="flex flex-col gap-1">
              <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                Seed
              </span>
              <div className="flex items-center gap-1.5">
                <input
                  type="number"
                  value={seed}
                  onChange={(e) => setSeed(Number(e.target.value) || 0)}
                  className="w-20 rounded border border-input bg-background px-2 py-1 font-mono text-xs text-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                />
                <button
                  type="button"
                  onClick={handleNewSeed}
                  className="inline-flex items-center gap-1 rounded border border-border bg-muted/60 px-2 py-1 text-xs font-medium text-foreground transition-colors hover:bg-muted"
                  title="Increment seed by 1"
                >
                  <Shuffle className="h-3 w-3 text-muted-foreground" />
                  <span>New seed</span>
                </button>
              </div>
            </div>

            {/* Run Button */}
            <div className="flex flex-col gap-1 self-end sm:ml-auto">
              <button
                type="button"
                onClick={handleRunFluct}
                disabled={!anyPriced}
                className="inline-flex items-center gap-1.5 rounded-md bg-primary px-4 py-1.5 text-xs font-semibold text-primary-foreground shadow-xs transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Play className="h-3.5 w-3.5 fill-current" />
                <span>Run (200 trials)</span>
              </button>
            </div>
          </div>

          {!anyPriced ? (
            <div className="rounded-lg border border-dashed border-border p-6 text-center text-xs font-medium text-muted-foreground">
              Enter a price for at least one robot
            </div>
          ) : fluctResult ? (
            <div className="space-y-4">
              {/* Coverage notice */}
              <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                <span>
                  <strong className="text-foreground">{fluctResult.robotsSimulated}</strong> robots simulated,{" "}
                  <strong className="text-foreground">{fluctResult.robotsExcluded}</strong> excluded: no price assumed
                </span>
                <span>&middot;</span>
                <span>200 Monte Carlo trials</span>
              </div>

              {/* Simple Line Chart (SVG) */}
              {chartBounds && (
                <div className="rounded-lg border border-border bg-muted/10 p-4 space-y-2">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-semibold text-foreground">Pipeline Path Percentiles (RM)</span>
                    <div className="flex items-center gap-3 text-[11px]">
                      <span className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
                        <span className="inline-block h-2 w-2 rounded-full bg-emerald-500" />
                        P90 (Upside)
                      </span>
                      <span className="flex items-center gap-1 text-primary">
                        <span className="inline-block h-2 w-2 rounded-full bg-primary" />
                        P50 (Median)
                      </span>
                      <span className="flex items-center gap-1 text-amber-600 dark:text-amber-400">
                        <span className="inline-block h-2 w-2 rounded-full bg-amber-500" />
                        P10 (Downside)
                      </span>
                    </div>
                  </div>

                  <div className="h-44 w-full">
                    <svg
                      viewBox="0 0 600 160"
                      preserveAspectRatio="none"
                      className="h-full w-full overflow-visible font-mono text-[9px]"
                    >
                      {/* Gridlines */}
                      {[0.2, 0.4, 0.6, 0.8].map((ratio) => (
                        <line
                          key={ratio}
                          x1="45"
                          y1={140 - ratio * 120}
                          x2="590"
                          y2={140 - ratio * 120}
                          stroke="currentColor"
                          strokeDasharray="2 3"
                          className="text-border"
                        />
                      ))}

                      {/* Line paths */}
                      {(() => {
                        const ptsCount = fluctResult.months.length
                        const getX = (idx: number) => 45 + (idx / (ptsCount - 1)) * 545
                        const getY = (val: number) => {
                          const range = chartBounds.max - chartBounds.min || 1
                          const norm = (val - chartBounds.min) / range
                          return 140 - norm * 120
                        }

                        const p10Path = fluctResult.months
                          .map((m, i) => `${getX(i)},${getY(m.p10)}`)
                          .join(" ")
                        const p50Path = fluctResult.months
                          .map((m, i) => `${getX(i)},${getY(m.p50)}`)
                          .join(" ")
                        const p90Path = fluctResult.months
                          .map((m, i) => `${getX(i)},${getY(m.p90)}`)
                          .join(" ")

                        return (
                          <>
                            <polyline
                              fill="none"
                              stroke="#10b981"
                              strokeWidth="2"
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              points={p90Path}
                            />
                            <polyline
                              fill="none"
                              stroke="#3b82f6"
                              strokeWidth="2.5"
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              points={p50Path}
                            />
                            <polyline
                              fill="none"
                              stroke="#f59e0b"
                              strokeWidth="2"
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              points={p10Path}
                            />

                            {/* X-axis tick marks */}
                            {fluctResult.months
                              .filter((m) => m.month === 0 || m.month % 3 === 0)
                              .map((m) => (
                                <text
                                  key={m.month}
                                  x={getX(m.month)}
                                  y="155"
                                  textAnchor="middle"
                                  fill="currentColor"
                                  className="text-muted-foreground"
                                >
                                  M{m.month}
                                </text>
                              ))}

                            {/* Y-axis labels */}
                            <text
                              x="40"
                              y={getY(chartBounds.max)}
                              textAnchor="end"
                              dominantBaseline="middle"
                              fill="currentColor"
                              className="text-muted-foreground"
                            >
                              {currency(chartBounds.max)}
                            </text>
                            <text
                              x="40"
                              y={getY(chartBounds.min)}
                              textAnchor="end"
                              dominantBaseline="middle"
                              fill="currentColor"
                              className="text-muted-foreground"
                            >
                              {currency(chartBounds.min)}
                            </text>
                          </>
                        )
                      })()}
                    </svg>
                  </div>
                </div>
              )}

              {/* Percentile Table: Month 0 and every 3rd month */}
              <div className="overflow-hidden rounded-md border border-border">
                <table className="w-full text-left text-xs">
                  <thead className="border-b border-border bg-muted/40 font-semibold text-muted-foreground">
                    <tr>
                      <th className="px-3 py-2">Month</th>
                      <th className="px-3 py-2 text-right">P10 (Downside)</th>
                      <th className="px-3 py-2 text-right font-bold text-foreground">P50 (Median)</th>
                      <th className="px-3 py-2 text-right">P90 (Upside)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {tableMonths.map((m) => (
                      <tr key={m.month} className="hover:bg-muted/20 font-mono">
                        <td className="px-3 py-2 font-medium text-foreground">
                          {m.month === 0 ? "Month 0 (Today)" : `Month ${m.month}`}
                        </td>
                        <td className="px-3 py-2 text-right text-amber-600 dark:text-amber-400">
                          {currency(m.p10)}
                        </td>
                        <td className="px-3 py-2 text-right font-bold text-foreground">
                          {currency(m.p50)}
                        </td>
                        <td className="px-3 py-2 text-right text-emerald-600 dark:text-emerald-400">
                          {currency(m.p90)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Permanent Note */}
              <div className="flex items-center gap-2 border-t border-border pt-3 text-[11px] text-muted-foreground">
                <Info className="h-3.5 w-3.5 shrink-0 text-muted-foreground/80" />
                <span>
                  Adoption probability does not change with price. Only the pipeline value does.
                </span>
              </div>
            </div>
          ) : (
            <div className="rounded-lg border border-dashed border-border p-6 text-center text-xs text-muted-foreground">
              Click &quot;Run (200 trials)&quot; to simulate price fluctuation paths across time.
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
