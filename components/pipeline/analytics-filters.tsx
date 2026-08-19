"use client"

import type { ComponentType } from "react"
import { Crown, Flame, MapPin, Snowflake, Users } from "lucide-react"
import type { Client, Tier } from "@/lib/pipeline-data"

// ─── Tier filter ─────────────────────────────────────────────────────────────
export type AnalyticsTierFilter = "ALL" | Tier

const TIER_OPTIONS: {
  value: AnalyticsTierFilter
  label: string
  icon: ComponentType<{ className?: string; strokeWidth?: number }>
}[] = [
  { value: "ALL",    label: "All Tiers",    icon: Users },
  { value: "TIER_1", label: "Tier 1 · VIP", icon: Crown },
  { value: "TIER_2", label: "Tier 2 · Warm", icon: Flame },
  { value: "TIER_3", label: "Tier 3 · Cold", icon: Snowflake },
]

// ─── Neighbourhood filter ─────────────────────────────────────────────────────
export type NeighborhoodFilter = "ALL" | string

// ─── Shared pill button ───────────────────────────────────────────────────────
function Pill({
  isActive,
  onClick,
  icon: Icon,
  label,
  count,
}: {
  isActive: boolean
  onClick: () => void
  icon?: ComponentType<{ className?: string; strokeWidth?: number }>
  label: string
  count?: number
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={isActive}
      className={`flex items-center gap-2 border border-neutral-200 px-3 py-2 text-xs font-black uppercase tracking-wider transition-transform sm:px-4 sm:py-2.5 sm:text-sm ${
        isActive
          ? "bg-black text-white shadow-[0px_2px_8px_rgba(0,0,0,0.08)] -translate-x-0.5 -translate-y-0.5"
          : "bg-white text-black shadow-[0px_1px_4px_rgba(0,0,0,0.07)] hover:shadow-[0px_2px_8px_rgba(0,0,0,0.08)]"
      }`}
    >
      {Icon && (
        <Icon
          className={`h-3.5 w-3.5 ${isActive ? "text-primary" : "text-black"}`}
          strokeWidth={2.5}
        />
      )}
      {label}
      {count !== undefined && (
        <span
          className={`border border-neutral-200 px-1.5 text-[10px] sm:text-xs ${
            isActive ? "bg-primary text-black" : "bg-black text-white"
          }`}
        >
          {count}
        </span>
      )}
    </button>
  )
}

// ─── Filter bar ───────────────────────────────────────────────────────────────
interface AnalyticsFiltersProps {
  /** Full client list — will be deduplicated by clientDbId to show unique client counts. */
  allClients: Client[]

  tierFilter: AnalyticsTierFilter
  onTierChange: (v: AnalyticsTierFilter) => void

  neighborhoodFilter: NeighborhoodFilter
  onNeighborhoodChange: (v: NeighborhoodFilter) => void

  /** Resulting unique client count after both filters are applied. */
  filteredCount: number
}

export function AnalyticsFilters({
  allClients,
  tierFilter,
  onTierChange,
  neighborhoodFilter,
  onNeighborhoodChange,
  filteredCount,
}: AnalyticsFiltersProps) {
  // Deduplicate allClients by clientDbId (keep best-match row for each client)
  const seen = new Set<string>()
  const uniqueClients = allClients.filter((c) => {
    const id = c.clientDbId ?? c.id
    if (!id || seen.has(id)) return false
    seen.add(id)
    return true
  })

  // Helper for neighborhood preference
  const getNbhd = (c: Client) => c.preferredNeighborhood ?? c.agent

  // Derive sorted unique neighborhoods from deduplicated data
  const neighborhoods = Array.from(new Set(uniqueClients.map(getNbhd))).sort()

  // Counts for tier pills (unique clients per tier)
  const tierCounts: Record<AnalyticsTierFilter, number> = {
    ALL: uniqueClients.length,
    TIER_1: uniqueClients.filter((c) => c.tier === "TIER_1").length,
    TIER_2: uniqueClients.filter((c) => c.tier === "TIER_2").length,
    TIER_3: uniqueClients.filter((c) => c.tier === "TIER_3").length,
  }

  // Counts for neighborhood pills (unique clients per preferred neighborhood)
  const neighborhoodCounts: Record<string, number> = {}
  for (const c of uniqueClients) {
    const n = getNbhd(c)
    neighborhoodCounts[n] = (neighborhoodCounts[n] ?? 0) + 1
  }

  return (
    <div className="border border-neutral-200 bg-white shadow-[0px_4px_16px_rgba(0,0,0,0.10)]">
      {/* Header bar */}
      <div className="flex items-center justify-between gap-4 border-b border-neutral-200 bg-black px-5 py-3 sm:px-6">
        <span className="text-xs font-black uppercase tracking-wider text-white sm:text-sm">
          Analytics Filters
        </span>
        <span className="border border-neutral-200 bg-primary px-2.5 py-1 text-[10px] font-black uppercase tracking-wider text-black sm:text-xs">
          {filteredCount} {filteredCount === 1 ? "result" : "results"}
        </span>
      </div>

      <div className="flex flex-col gap-5 p-4 sm:p-5">
        {/* ── Tier row ── */}
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-1.5 text-[10px] font-black uppercase tracking-wider text-muted-foreground">
            <Crown className="h-3 w-3" strokeWidth={2.5} />
            Segment Tier
          </div>
          <div className="flex flex-wrap gap-2">
            {TIER_OPTIONS.map((opt) => (
              <Pill
                key={opt.value}
                isActive={tierFilter === opt.value}
                onClick={() => onTierChange(opt.value)}
                icon={opt.icon}
                label={opt.label}
                count={tierCounts[opt.value]}
              />
            ))}
          </div>
        </div>

        {/* ── Divider ── */}
        <div className="border-t-2 border-black border-dashed" />

        {/* ── Neighborhood row ── */}
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-1.5 text-[10px] font-black uppercase tracking-wider text-muted-foreground">
            <MapPin className="h-3 w-3" strokeWidth={2.5} />
            Neighborhood
          </div>
          <div className="flex flex-wrap gap-2">
            {/* "ALL" pill */}
            <Pill
              isActive={neighborhoodFilter === "ALL"}
              onClick={() => onNeighborhoodChange("ALL")}
              label="All Areas"
              count={uniqueClients.length}
            />
            {neighborhoods.map((n) => (
              <Pill
                key={n}
                isActive={neighborhoodFilter === n}
                onClick={() => onNeighborhoodChange(n)}
                icon={MapPin}
                label={n}
                count={neighborhoodCounts[n] ?? 0}
              />
            ))}
          </div>
        </div>

        {/* ── Active filter summary ── */}
        {(tierFilter !== "ALL" || neighborhoodFilter !== "ALL") && (
          <div className="flex items-center justify-between gap-3 border border-neutral-200 bg-primary px-3 py-2 shadow-[0px_1px_4px_rgba(0,0,0,0.07)]">
            <span className="text-[10px] font-black uppercase tracking-wider text-black">
              Showing{" "}
              {tierFilter !== "ALL" && (
                <span>{tierFilter.replace("_", " ")} </span>
              )}
              {neighborhoodFilter !== "ALL" && (
                <span>in {neighborhoodFilter} </span>
              )}
              — {filteredCount} {filteredCount === 1 ? "result" : "results"}
            </span>
            <button
              type="button"
              onClick={() => {
                onTierChange("ALL")
                onNeighborhoodChange("ALL")
              }}
              className="border border-neutral-200 bg-black px-2.5 py-1 text-[10px] font-black uppercase tracking-wider text-white hover:bg-white hover:text-black transition-colors"
            >
              Clear
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
