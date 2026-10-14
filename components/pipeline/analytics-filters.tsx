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
  { value: "ALL",    label: "All Tiers",            icon: Users },
  { value: "TIER_1", label: "Tier 1 · High-Fit",    icon: Crown },
  { value: "TIER_2", label: "Tier 2 · Possible-Fit", icon: Flame },
  { value: "TIER_3", label: "Tier 3 · Low-Fit",     icon: Snowflake },
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
      className={`flex items-center gap-2 rounded-[var(--radius-sm)] border px-3 py-2 text-xs font-bold uppercase tracking-wider transition-all sm:px-3.5 sm:py-2 ${
        isActive
          ? "border-neutral-900 bg-black text-white shadow-[var(--shadow-xs)]"
          : "border-border bg-card text-foreground hover:bg-muted shadow-[var(--shadow-xs)]"
      }`}
    >
      {Icon && (
        <Icon
          className={`h-3.5 w-3.5 ${isActive ? "text-primary" : "text-muted-foreground"}`}
          strokeWidth={2.5}
        />
      )}
      {label}
      {count !== undefined && (
        <span
          className={`rounded px-1.5 py-0.5 text-[10px] font-mono ${
            isActive ? "bg-primary text-black font-bold" : "bg-muted text-muted-foreground"
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
    <div className="overflow-hidden rounded-[var(--radius)] border border-border bg-card shadow-[var(--shadow-sm)]">
      {/* Header bar — Lighter style */}
      <div className="flex items-center justify-between gap-4 border-b border-border bg-transparent px-5 py-3.5 sm:px-6">
        <span className="text-xs font-bold uppercase tracking-wider text-foreground sm:text-sm">
          Analytics Filters
        </span>
        <span className="rounded-[var(--radius-sm)] border border-border bg-muted px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground sm:text-xs">
          {filteredCount} {filteredCount === 1 ? "result" : "results"}
        </span>
      </div>

      <div className="flex flex-col gap-5 p-5 sm:p-6">
        {/* ── Tier row ── */}
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
            <Crown className="h-3 w-3" strokeWidth={2.5} />
            Fit-Tier
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
        <div className="border-t border-border" />

        {/* ── Neighborhood row ── */}
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
            <MapPin className="h-3 w-3" strokeWidth={2.5} />
            Target Environment
          </div>
          <div className="flex flex-wrap gap-2">
            {/* "ALL" pill */}
            <Pill
              isActive={neighborhoodFilter === "ALL"}
              onClick={() => onNeighborhoodChange("ALL")}
              label="All Environments"
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
          <div className="flex items-center justify-between gap-3 rounded-[var(--radius-sm)] border border-primary/40 bg-primary/10 px-3.5 py-2">
            <span className="text-xs font-semibold text-foreground">
              Showing{" "}
              {tierFilter !== "ALL" && (
                <span className="font-bold">{tierFilter.replace("_", " ")} </span>
              )}
              {neighborhoodFilter !== "ALL" && (
                <span>in <span className="font-bold">{neighborhoodFilter}</span> </span>
              )}
              — {filteredCount} {filteredCount === 1 ? "result" : "results"}
            </span>
            <button
              type="button"
              onClick={() => {
                onTierChange("ALL")
                onNeighborhoodChange("ALL")
              }}
              className="rounded-[var(--radius-sm)] border border-border bg-black px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-white hover:bg-neutral-800 transition-colors"
            >
              Clear
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
