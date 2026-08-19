"use client"

import { useState, Fragment } from "react"
import { MapPin } from "lucide-react"
import { currency, type Client, type Tier } from "@/lib/pipeline-data"
import { ScrollConnect } from "@/components/animation/scroll-connect"
import { useChartInsight, ChartInsightPanel } from "./chart-insight-panel"

const TIERS: Tier[] = ["TIER_1", "TIER_2", "TIER_3"]

const TIER_META: Record<Tier, { label: string; shortLabel: string; baseColor: string; textColor: string }> = {
  TIER_1: { label: "Tier 1 · VIP",  shortLabel: "VIP",  baseColor: "212, 170, 0",  textColor: "#000" },
  TIER_2: { label: "Tier 2 · Warm", shortLabel: "WARM", baseColor: "0, 0, 0",       textColor: "#fff" },
  TIER_3: { label: "Tier 3 · Cold", shortLabel: "COLD", baseColor: "160, 160, 160", textColor: "#000" },
}

interface CellData {
  neighborhood: string
  tier: Tier
  count: number
  totalEx: number
}

interface HoverState {
  neighborhood: string
  tier: Tier
  count: number
  totalEx: number
  x: number
  y: number
}

interface NeighborhoodTierHeatmapProps {
  clients: Client[]
  onCellClick?: (neighborhood: string, tier: Tier) => void
}

export function NeighborhoodTierHeatmap({ clients, onCellClick }: NeighborhoodTierHeatmapProps) {
  const [hover, setHover] = useState<HoverState | null>(null)
  const { insight, loading, fetchInsight } = useChartInsight()

  // Deduplicate: each client counted once, placed by their preferred_neighborhood × overall tier.
  const seen = new Set<string>()
  const uniqueClients = clients.filter((c) => {
    if (seen.has(c.clientDbId)) return false
    seen.add(c.clientDbId)
    return true
  })

  const neighborhoods = Array.from(
    new Set(uniqueClients.map((c) => c.preferredNeighborhood ?? "Unknown"))
  ).sort()

  const handleCellClick = (nbhd: string, tier: Tier) => {
    fetchInsight("heatmap_cell", { neighborhood: nbhd, tier })
    if (onCellClick) onCellClick(nbhd, tier)
  }

  if (neighborhoods.length === 0) {
    return (
      <div className="border-4 border-black bg-white shadow-[8px_8px_0px_0px_rgba(0,0,0,1)]">
        <HeatmapHeader />
        <div className="flex items-center justify-center p-10 text-xs font-black uppercase tracking-wider text-muted-foreground">
          No data
        </div>
      </div>
    )
  }

  // Build cell data map — one count per unique client
  const cellMap = new Map<string, CellData>()
  for (const c of uniqueClients) {
    const nbhd = c.preferredNeighborhood ?? "Unknown"
    const key = `${nbhd}__${c.tier}`
    const cur = cellMap.get(key) ?? { neighborhood: nbhd, tier: c.tier, count: 0, totalEx: 0 }
    cellMap.set(key, { ...cur, count: cur.count + 1, totalEx: cur.totalEx + c.expectedValue })
  }

  const maxCount = Math.max(...Array.from(cellMap.values()).map((v) => v.count), 1)

  return (
    <ScrollConnect>
      <div className="border-4 border-black bg-white shadow-[8px_8px_0px_0px_rgba(0,0,0,1)]">
        <HeatmapHeader />

        <div className="overflow-x-auto p-4 sm:p-5">
          {/* Column headers (tiers) */}
          <div
            className="grid gap-1.5"
            style={{ gridTemplateColumns: `minmax(90px, 140px) repeat(${TIERS.length}, minmax(72px, 1fr))` }}
          >
            {/* Empty top-left corner */}
            <div />
            {TIERS.map((tier) => (
              <div
                key={tier}
                className="border-2 border-black px-2 py-1.5 text-center text-[10px] font-black uppercase tracking-wider"
                style={{
                  background: tier === "TIER_1" ? "var(--primary)" : tier === "TIER_2" ? "#000" : "#c4c4c4",
                  color: tier === "TIER_2" ? "#fff" : "#000",
                }}
              >
                {TIER_META[tier].shortLabel}
              </div>
            ))}

            {/* Rows (neighborhoods) */}
            {neighborhoods.map((nbhd, rowIndex) => (
              <Fragment key={nbhd}>
                {/* Row label */}
                <div
                  key={`label-${nbhd}`}
                  className="flex items-center gap-1 border-2 border-black bg-black px-2 py-2 text-[10px] font-black uppercase tracking-wider text-white"
                  style={{ minHeight: "44px" }}
                >
                  <MapPin className="h-2.5 w-2.5 shrink-0 text-primary" strokeWidth={2.5} />
                  <span className="truncate">{nbhd}</span>
                </div>

                {/* Tier cells */}
                {TIERS.map((tier, colIndex) => {
                  const key = `${nbhd}__${tier}`
                  const cell = cellMap.get(key)
                  const count = cell?.count ?? 0
                  const totalEx = cell?.totalEx ?? 0
                  const intensity = count === 0 ? 0 : 0.12 + 0.88 * (count / maxCount)
                  const meta = TIER_META[tier]
                  const cellDelay = (rowIndex * 3 + colIndex) * 25

                  return (
                    <div
                      key={key}
                      className="heatmap-cell-enter relative border-2 border-black transition-transform duration-150"
                      style={{
                        animationDelay: `${cellDelay}ms`,
                        background:
                          count === 0
                            ? "#f5f5f5"
                            : `rgba(${meta.baseColor}, ${intensity})`,
                        cursor: count > 0 ? "pointer" : "default",
                        minHeight: "44px",
                      }}
                      onClick={() => count > 0 && handleCellClick(nbhd, tier)}
                      onMouseEnter={(e) => {
                        if (count > 0) {
                          const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
                          setHover({ neighborhood: nbhd, tier, count, totalEx, x: rect.left, y: rect.top })
                        }
                      }}
                      onMouseLeave={() => setHover(null)}
                    >
                      {count > 0 ? (
                        <div className="flex h-full flex-col items-center justify-center p-1.5">
                          <span
                            className="font-mono text-sm font-black leading-none"
                            style={{ color: intensity > 0.5 && tier === "TIER_2" ? "#fff" : "#000" }}
                          >
                            {count}
                          </span>
                          <span
                            className="mt-0.5 text-[9px] font-bold uppercase tracking-wider opacity-70"
                            style={{ color: intensity > 0.5 && tier === "TIER_2" ? "#fff" : "#000" }}
                          >
                            {count === 1 ? "client" : "clients"}
                          </span>
                        </div>
                      ) : (
                        <div className="flex h-full items-center justify-center text-[11px] font-bold text-muted-foreground">
                          —
                        </div>
                      )}
                    </div>
                  )
                })}
              </Fragment>
            ))}
          </div>

          {/* Legend */}
          <div className="mt-4 flex items-center gap-3 border-t-2 border-dashed border-black pt-3">
            <span className="text-[10px] font-black uppercase tracking-wider text-muted-foreground">
              Intensity = client count
            </span>
            <div className="flex items-center gap-1">
              <div className="h-3 w-6 border border-black bg-[#f5f5f5]" />
              <span className="text-[9px] font-bold text-muted-foreground">0</span>
            </div>
            <div className="flex items-center gap-1">
              <div className="h-3 w-6 border border-black" style={{ background: "rgba(0,0,0,0.4)" }} />
              <span className="text-[9px] font-bold text-muted-foreground">High</span>
            </div>
            <span className="ml-auto text-[10px] font-black uppercase tracking-wider text-muted-foreground">
              Click cell for AI analysis →
            </span>
          </div>

          <ChartInsightPanel insight={insight} loading={loading} />
        </div>

        {/* Floating tooltip */}
        {hover && (
          <div
            className="pointer-events-none fixed z-50 border-4 border-black bg-white px-4 py-3 shadow-[4px_4px_0px_0px_rgba(0,0,0,1)]"
            style={{ top: hover.y - 10, left: hover.x + 10, transform: "translateY(-100%)" }}
          >
            <div className="text-xs font-black uppercase tracking-wider">
              {hover.neighborhood} × {TIER_META[hover.tier].shortLabel}
            </div>
            <div className="mt-1 font-mono text-lg font-black leading-none">
              {hover.count} {hover.count === 1 ? "client" : "clients"}
            </div>
            <div className="mt-1 text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
              {currency(hover.totalEx)} total E(x)
            </div>
          </div>
        )}
      </div>
    </ScrollConnect>
  )
}

function HeatmapHeader() {
  return (
    <div className="flex items-center justify-between gap-3 border-b-4 border-black bg-black px-5 py-3.5 sm:px-6">
      <div className="flex items-center gap-2 text-white">
        <MapPin className="h-4 w-4" strokeWidth={2.5} />
        <span className="text-xs font-black uppercase tracking-wider sm:text-sm">
          Neighborhood × Tier Heatmap
        </span>
      </div>
      <span className="border-2 border-black bg-primary px-2.5 py-1 text-[10px] font-black uppercase tracking-wider text-black sm:text-xs">
        Click cell for AI analysis
      </span>
    </div>
  )
}
