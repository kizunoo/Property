"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import {
  ArrowRight, BookOpen, ChevronDown, Filter, HelpCircle,
  LayoutGrid, List, RotateCcw, Search, Sparkles, X, XCircle, Zap,
} from "lucide-react"
import type { CatalogUnit, DashboardData } from "@/lib/portal-types"
import { fetchCatalog } from "@/lib/portal-api"
import { useToast } from "@/hooks/use-toast"
import { Skeleton } from "@/components/ui/skeleton"

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatCost(n: number | null): string {
  if (!n) return "—"
  if (n >= 1_000_000) return `RM ${(n / 1_000_000).toFixed(2)}M`
  if (n >= 1_000)     return `RM ${(n / 1_000).toFixed(0)}K`
  return `RM ${n.toLocaleString()}`
}

function formatSavings(n: number | null): string {
  if (!n) return "—"
  if (n >= 1_000_000) return `RM ${(n / 1_000_000).toFixed(1)}M/yr`
  return `RM ${(n / 1_000).toFixed(0)}K/yr`
}

type SortKey = "default" | "cost_asc" | "cost_desc" | "payback_asc"
type ViewMode = "grid" | "list"

const SORT_OPTIONS: { key: SortKey; label: string }[] = [
  { key: "default",     label: "Default order" },
  { key: "cost_asc",    label: "Cost: low → high" },
  { key: "cost_desc",   label: "Cost: high → low" },
  { key: "payback_asc", label: "Fastest payback" },
]

// ─── Spec pill ────────────────────────────────────────────────────────────────

function SpecPill({ label, value }: { label: string; value: string }) {
  return (
    <span className="inline-flex items-center gap-1 border border-border bg-secondary px-2 py-0.5 text-[10px] font-bold">
      <span className="text-muted-foreground">{label}</span>
      <span>{value}</span>
    </span>
  )
}

// ─── Unit card (grid view) ────────────────────────────────────────────────────

function UnitCard({
  unit,
  onRequestDemo,
  onAskQuestion,
  onViewDetails,
}: {
  unit: CatalogUnit
  onRequestDemo: (u: CatalogUnit) => void
  onAskQuestion: (u: CatalogUnit) => void
  onViewDetails: (u: CatalogUnit) => void
}) {
  return (
    <div
      className={`group relative flex flex-col border bg-card shadow-[var(--shadow-xs)] hover:shadow-[var(--shadow-sm)] transition-shadow ${
        unit.matched ? "border-primary/60" : "border-border"
      }`}
    >
      {/* Matched badge */}
      {unit.matched && (
        <div className="absolute top-2 right-2 z-10 flex items-center gap-1 border border-primary/40 bg-secondary px-2 py-0.5 text-[9px] font-black uppercase tracking-wider text-primary">
          <Sparkles className="h-2.5 w-2.5" strokeWidth={3} />
          Matched for you
        </div>
      )}

      {/* Image */}
      <div className="relative h-40 overflow-hidden bg-muted">
        {unit.image_url ? (
          <img
            src={unit.image_url}
            alt={unit.name ?? "Robot unit"}
            className="h-full w-full object-cover transition-transform group-hover:scale-105"
          />
        ) : (
          <div className="flex h-full items-center justify-center text-muted-foreground/30">
            <BookOpen className="h-8 w-8" />
          </div>
        )}
        {/* Category chip */}
        {unit.property_type && (
          <span className="absolute bottom-2 left-2 border border-border/60 bg-black/80 px-2 py-0.5 text-[9px] font-black uppercase tracking-wider text-white">
            {unit.property_type}
          </span>
        )}
      </div>

      {/* Body */}
      <div className="flex flex-1 flex-col gap-3 p-4">
        <div>
          <h3 className="font-bold leading-snug text-sm">{unit.name}</h3>
          {unit.environment && (
            <p className="mt-0.5 text-[11px] text-muted-foreground">{unit.environment}</p>
          )}
        </div>

        {/* Price row */}
        <div className="flex items-baseline gap-2 flex-wrap">
          <span className="text-base font-black">{formatCost(unit.cost)}</span>
          {unit.payback_months && (
            <span className="text-[10px] font-semibold text-muted-foreground">
              ~{unit.payback_months}mo payback
            </span>
          )}
        </div>

        {/* Spec pills */}
        <div className="flex flex-wrap gap-1.5">
          {unit.payload_tier != null && (
            <SpecPill label="Payload tier" value={`${unit.payload_tier}/5`} />
          )}
          {unit.nav_sensors != null && (
            <SpecPill label="Nav sensors" value={`${unit.nav_sensors}`} />
          )}
          {unit.operational_range_sqft != null && (
            <SpecPill label="Coverage" value={`${unit.operational_range_sqft.toLocaleString()} sqft`} />
          )}
          {unit.estimated_annual_savings != null && (
            <SpecPill label="Est. savings" value={formatSavings(unit.estimated_annual_savings)} />
          )}
        </div>

        {/* Actions */}
        <div className="mt-auto pt-2 flex flex-col gap-1.5">
          <button
            onClick={() => onRequestDemo(unit)}
            className="group/btn flex items-center justify-center gap-2 border border-border bg-black py-2.5 text-xs font-black uppercase tracking-wider text-white hover:shadow-[var(--shadow-sm)] transition-shadow"
          >
            Request demo
            <ArrowRight className="h-3.5 w-3.5 text-primary transition-transform group-hover/btn:translate-x-0.5" strokeWidth={3} />
          </button>
          <div className="flex gap-1.5">
            <button
              onClick={() => onAskQuestion(unit)}
              className="flex-1 border border-border bg-secondary py-2 text-[10px] font-black uppercase tracking-wider hover:bg-muted transition-colors flex items-center justify-center gap-1"
            >
              <HelpCircle className="h-3 w-3" strokeWidth={3} />
              Ask a question
            </button>
            <button
              onClick={() => onViewDetails(unit)}
              className="flex-1 border border-border bg-secondary py-2 text-[10px] font-black uppercase tracking-wider hover:bg-muted transition-colors"
            >
              Details
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── Unit row (list view) ─────────────────────────────────────────────────────

function UnitRow({
  unit,
  onRequestDemo,
  onAskQuestion,
  onViewDetails,
}: {
  unit: CatalogUnit
  onRequestDemo: (u: CatalogUnit) => void
  onAskQuestion: (u: CatalogUnit) => void
  onViewDetails: (u: CatalogUnit) => void
}) {
  return (
    <div
      className={`group flex flex-col sm:flex-row gap-4 border bg-card shadow-[var(--shadow-xs)] hover:shadow-[var(--shadow-sm)] transition-shadow p-4 ${
        unit.matched ? "border-primary/60" : "border-border"
      }`}
    >
      {/* Thumbnail */}
      <div className="relative h-24 w-full sm:h-20 sm:w-28 shrink-0 overflow-hidden bg-muted">
        {unit.image_url && (
          <img src={unit.image_url} alt={unit.name ?? ""} className="h-full w-full object-cover" />
        )}
      </div>

      {/* Info */}
      <div className="flex flex-1 flex-col gap-2 min-w-0">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="font-bold text-sm truncate">{unit.name}</h3>
              {unit.matched && (
                <span className="inline-flex items-center gap-1 border border-primary/40 bg-secondary px-2 py-0.5 text-[9px] font-black uppercase tracking-wider text-primary">
                  <Sparkles className="h-2.5 w-2.5" strokeWidth={3} />
                  Matched
                </span>
              )}
            </div>
            <p className="text-[11px] text-muted-foreground mt-0.5">
              {[unit.property_type, unit.environment].filter(Boolean).join(" · ")}
            </p>
          </div>
          <span className="text-sm font-black shrink-0">{formatCost(unit.cost)}</span>
        </div>

        <div className="flex flex-wrap gap-1.5">
          {unit.payload_tier != null && <SpecPill label="Payload" value={`${unit.payload_tier}/5`} />}
          {unit.payback_months && <SpecPill label="Payback" value={`~${unit.payback_months}mo`} />}
          {unit.estimated_annual_savings != null && <SpecPill label="Savings" value={formatSavings(unit.estimated_annual_savings)} />}
          {unit.operational_range_sqft != null && <SpecPill label="Coverage" value={`${unit.operational_range_sqft.toLocaleString()} sqft`} />}
        </div>
      </div>

      {/* Actions */}
      <div className="flex sm:flex-col gap-2 shrink-0 sm:justify-center">
        <button
          onClick={() => onRequestDemo(unit)}
          className="flex items-center gap-1.5 border border-border bg-black px-3 py-2 text-[10px] font-black uppercase tracking-wider text-white hover:shadow-[var(--shadow-sm)] transition-shadow"
        >
          Request demo <ArrowRight className="h-3 w-3 text-primary" strokeWidth={3} />
        </button>
        <button
          onClick={() => onAskQuestion(unit)}
          className="flex items-center gap-1.5 border border-border bg-secondary px-3 py-2 text-[10px] font-black uppercase tracking-wider hover:bg-muted transition-colors"
        >
          <HelpCircle className="h-3 w-3" strokeWidth={3} /> Ask
        </button>
        <button
          onClick={() => onViewDetails(unit)}
          className="border border-border bg-secondary px-3 py-2 text-[10px] font-black uppercase tracking-wider hover:bg-muted transition-colors"
        >
          Details
        </button>
      </div>
    </div>
  )
}

// ─── Detail drawer ────────────────────────────────────────────────────────────

function DetailDrawer({
  unit,
  onClose,
  onRequestDemo,
  onAskQuestion,
}: {
  unit: CatalogUnit
  onClose: () => void
  onRequestDemo: (u: CatalogUnit) => void
  onAskQuestion: (u: CatalogUnit) => void
}) {
  return (
    <div className="fixed inset-0 z-50 flex">
      <button onClick={onClose} className="absolute inset-0 bg-black/40 backdrop-blur-sm" aria-label="Close" />
      <div className="absolute right-0 top-0 h-full w-full max-w-md flex flex-col bg-card border-l border-border shadow-[var(--shadow-xl)] overflow-y-auto">
        {/* Header */}
        <div className="flex items-start justify-between gap-4 border-b border-border px-5 py-4 shrink-0">
          <div>
            {unit.matched && (
              <span className="inline-flex items-center gap-1 border border-primary/40 bg-secondary px-2 py-0.5 text-[9px] font-black uppercase tracking-wider text-primary mb-1">
                <Sparkles className="h-2.5 w-2.5" strokeWidth={3} />
                Matched for you
              </span>
            )}
            <h2 className="text-base font-bold leading-snug">{unit.name}</h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              {[unit.property_type, unit.environment].filter(Boolean).join(" · ")}
            </p>
          </div>
          <button onClick={onClose} className="border border-border p-1.5 hover:bg-muted transition-colors">
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Image */}
        {unit.image_url && (
          <div className="h-52 shrink-0 overflow-hidden bg-muted">
            <img src={unit.image_url} alt={unit.name ?? ""} className="h-full w-full object-cover" />
          </div>
        )}

        {/* Specs */}
        <div className="flex-1 px-5 py-5 flex flex-col gap-5">
          {/* Price */}
          <div className="border border-border bg-secondary p-4">
            <p className="text-[10px] font-black uppercase tracking-wider text-muted-foreground mb-1">Unit cost</p>
            <p className="text-2xl font-black">{formatCost(unit.cost)}</p>
          </div>

          {/* ROI strip */}
          {(unit.estimated_annual_savings || unit.payback_months) && (
            <div className="border border-border bg-secondary/60 p-4 flex flex-col gap-2">
              <p className="text-[10px] font-black uppercase tracking-wider text-muted-foreground">Return on investment</p>
              <div className="grid grid-cols-2 gap-3">
                {unit.estimated_annual_savings != null && (
                  <div>
                    <p className="text-[9px] font-bold uppercase tracking-wider text-muted-foreground">Est. annual savings</p>
                    <p className="text-sm font-black">{formatSavings(unit.estimated_annual_savings)}</p>
                  </div>
                )}
                {unit.payback_months && (
                  <div>
                    <p className="text-[9px] font-bold uppercase tracking-wider text-muted-foreground">Payback period</p>
                    <p className="text-sm font-black">~{unit.payback_months} months</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Specs grid */}
          <div className="border border-border divide-y divide-border">
            {unit.payload_tier != null && (
              <div className="flex justify-between px-4 py-3">
                <span className="text-xs font-bold text-muted-foreground">Payload tier</span>
                <span className="text-xs font-black">{unit.payload_tier}/5</span>
              </div>
            )}
            {unit.nav_sensors != null && (
              <div className="flex justify-between px-4 py-3">
                <span className="text-xs font-bold text-muted-foreground">Nav sensors / lidar</span>
                <span className="text-xs font-black">{unit.nav_sensors}</span>
              </div>
            )}
            {unit.operational_range_sqft != null && (
              <div className="flex justify-between px-4 py-3">
                <span className="text-xs font-bold text-muted-foreground">Coverage per 8h shift</span>
                <span className="text-xs font-black">{unit.operational_range_sqft.toLocaleString()} sqft</span>
              </div>
            )}
            {unit.environment && (
              <div className="flex justify-between px-4 py-3">
                <span className="text-xs font-bold text-muted-foreground">Target environment</span>
                <span className="text-xs font-black">{unit.environment}</span>
              </div>
            )}
          </div>

          {/* Actions */}
          <div className="flex flex-col gap-2 pt-2">
            <button
              onClick={() => onRequestDemo(unit)}
              className="group flex items-center justify-center gap-2 border border-border bg-black py-3 text-sm font-black uppercase tracking-wider text-white hover:shadow-[var(--shadow-sm)] transition-shadow"
            >
              Request demo
              <ArrowRight className="h-4 w-4 text-primary transition-transform group-hover:translate-x-0.5" strokeWidth={3} />
            </button>
            <button
              onClick={() => onAskQuestion(unit)}
              className="flex items-center justify-center gap-2 border border-border bg-secondary py-3 text-sm font-black uppercase tracking-wider hover:bg-muted transition-colors"
            >
              <HelpCircle className="h-4 w-4" strokeWidth={3} />
              Ask a question
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── Catalog Tab ──────────────────────────────────────────────────────────────

export function CatalogTab({
  clientId,
  data: dashboardData,
  onNavigateToMessages,
}: {
  clientId: string
  data: DashboardData | null
  onNavigateToMessages: (unit: CatalogUnit) => void
}) {
  const { toast } = useToast()

  const [units, setUnits]               = useState<CatalogUnit[]>([])
  const [loading, setLoading]           = useState(true)
  const [error, setError]               = useState<string | null>(null)
  const [search, setSearch]             = useState("")
  const [sortKey, setSortKey]           = useState<SortKey>("default")
  const [filterEnv, setFilterEnv]       = useState("all")
  const [filterType, setFilterType]     = useState("all")
  const [showMatched, setShowMatched]   = useState(false)
  const [viewMode, setViewMode]         = useState<ViewMode>("grid")
  const [detailUnit, setDetailUnit]     = useState<CatalogUnit | null>(null)
  const [requestUnit, setRequestUnit]   = useState<CatalogUnit | null>(null)
  const [questionUnit, setQuestionUnit] = useState<CatalogUnit | null>(null)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const d = await fetchCatalog(clientId)
      setUnits(d.units)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load catalog.")
    } finally {
      setLoading(false)
    }
  }, [clientId])

  useEffect(() => { load() }, [load])

  // Derived filter options
  const environments = useMemo(() =>
    [...new Set(units.map(u => u.environment).filter(Boolean) as string[])].sort(),
  [units])

  const types = useMemo(() =>
    [...new Set(units.map(u => u.property_type).filter(Boolean) as string[])].sort(),
  [units])

  // Filter + sort
  const displayed = useMemo(() => {
    let list = [...units]
    if (showMatched)      list = list.filter(u => u.matched)
    if (filterEnv !== "all") list = list.filter(u => u.environment === filterEnv)
    if (filterType !== "all") list = list.filter(u => u.property_type === filterType)
    if (search.trim())    list = list.filter(u =>
      (u.name ?? "").toLowerCase().includes(search.toLowerCase()) ||
      (u.property_type ?? "").toLowerCase().includes(search.toLowerCase()) ||
      (u.environment ?? "").toLowerCase().includes(search.toLowerCase())
    )
    switch (sortKey) {
      case "cost_asc":    list.sort((a, b) => (a.cost ?? Infinity) - (b.cost ?? Infinity)); break
      case "cost_desc":   list.sort((a, b) => (b.cost ?? 0) - (a.cost ?? 0)); break
      case "payback_asc": list.sort((a, b) => (a.payback_months ?? 999) - (b.payback_months ?? 999)); break
    }
    return list
  }, [units, search, sortKey, filterEnv, filterType, showMatched])

  const matchedCount = useMemo(() => units.filter(u => u.matched).length, [units])
  const activeFilters = [
    filterEnv !== "all" && filterEnv,
    filterType !== "all" && filterType,
    showMatched && "Matched only",
    search && `"${search}"`,
  ].filter(Boolean) as string[]

  function handleClearFilters() {
    setSearch(""); setFilterEnv("all"); setFilterType("all"); setShowMatched(false)
  }

  // Request demo: navigate to messages tab with unit pre-selected
  function handleRequestDemo(unit: CatalogUnit) {
    toast({
      title: "Request a demo",
      description: `Use the Messages tab to ask about a demo for ${unit.name}.`,
    })
    onNavigateToMessages(unit)
  }

  function handleAskQuestion(unit: CatalogUnit) {
    onNavigateToMessages(unit)
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-7xl px-4 sm:px-6 py-8 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {[...Array(6)].map((_, i) => (
          <div key={i} className="flex flex-col gap-3 border border-border bg-card p-4">
            <Skeleton className="h-40" />
            <Skeleton className="h-5 w-3/4" />
            <Skeleton className="h-4 w-1/2" />
            <Skeleton className="h-10" />
          </div>
        ))}
      </div>
    )
  }

  if (error) {
    return (
      <div className="mx-auto max-w-3xl px-4 sm:px-6 py-10">
        <div className="border border-border bg-card p-8 text-center">
          <XCircle className="mx-auto h-6 w-6 text-destructive mb-2" />
          <p className="text-sm font-semibold text-destructive mb-4">{error}</p>
          <button onClick={load}
            className="border border-border bg-black px-4 py-2 text-xs font-black uppercase tracking-wider text-white">
            Retry
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-7xl px-4 sm:px-6 py-8 flex flex-col gap-6">
      {/* Header row */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-[10px] font-black uppercase tracking-wider text-muted-foreground flex items-center gap-2">
            <BookOpen className="h-3.5 w-3.5" />
            Unit catalog — {units.length} available
          </h1>
          {matchedCount > 0 && (
            <p className="text-xs text-muted-foreground mt-0.5">
              <Sparkles className="inline h-3 w-3 text-primary mr-1" />
              {matchedCount} unit{matchedCount !== 1 ? "s" : ""} matched to your profile
            </p>
          )}
        </div>
        {/* View toggle */}
        <div className="flex items-center gap-2">
          <button
            id="catalog-grid-btn"
            onClick={() => setViewMode("grid")}
            className={`border border-border p-2 transition-colors ${viewMode === "grid" ? "bg-black text-white" : "bg-card hover:bg-muted"}`}
            aria-label="Grid view"
          >
            <LayoutGrid className="h-4 w-4" />
          </button>
          <button
            id="catalog-list-btn"
            onClick={() => setViewMode("list")}
            className={`border border-border p-2 transition-colors ${viewMode === "list" ? "bg-black text-white" : "bg-card hover:bg-muted"}`}
            aria-label="List view"
          >
            <List className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Filters row */}
      <div className="flex flex-col sm:flex-row gap-3 flex-wrap">
        {/* Search */}
        <div className="relative flex-1 min-w-48">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
          <input
            id="catalog-search"
            type="text"
            placeholder="Search units…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-full border border-border bg-white pl-9 pr-3 py-2 text-sm focus:outline-none focus-visible:border-primary"
          />
        </div>

        {/* Environment filter */}
        <div className="relative">
          <Filter className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3 w-3 text-muted-foreground pointer-events-none" />
          <select
            id="catalog-env-filter"
            value={filterEnv}
            onChange={e => setFilterEnv(e.target.value)}
            className="border border-border bg-white pl-8 pr-8 py-2 text-sm focus:outline-none focus-visible:border-primary appearance-none"
          >
            <option value="all">All environments</option>
            {environments.map(e => <option key={e} value={e}>{e}</option>)}
          </select>
          <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 h-3 w-3 text-muted-foreground pointer-events-none" />
        </div>

        {/* Type filter */}
        <div className="relative">
          <select
            id="catalog-type-filter"
            value={filterType}
            onChange={e => setFilterType(e.target.value)}
            className="border border-border bg-white px-3 pr-8 py-2 text-sm focus:outline-none focus-visible:border-primary appearance-none"
          >
            <option value="all">All categories</option>
            {types.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
          <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 h-3 w-3 text-muted-foreground pointer-events-none" />
        </div>

        {/* Sort */}
        <div className="relative">
          <select
            id="catalog-sort"
            value={sortKey}
            onChange={e => setSortKey(e.target.value as SortKey)}
            className="border border-border bg-white px-3 pr-8 py-2 text-sm focus:outline-none focus-visible:border-primary appearance-none"
          >
            {SORT_OPTIONS.map(o => <option key={o.key} value={o.key}>{o.label}</option>)}
          </select>
          <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 h-3 w-3 text-muted-foreground pointer-events-none" />
        </div>

        {/* Matched toggle */}
        {matchedCount > 0 && (
          <button
            id="catalog-matched-filter"
            onClick={() => setShowMatched(v => !v)}
            className={`flex items-center gap-1.5 border border-border px-3 py-2 text-[10px] font-black uppercase tracking-wider transition-colors ${
              showMatched ? "bg-black text-white" : "bg-secondary hover:bg-muted"
            }`}
          >
            <Sparkles className="h-3 w-3" strokeWidth={3} />
            {showMatched ? "Showing matched" : "Show matched"}
          </button>
        )}

        {/* Clear active filters */}
        {activeFilters.length > 0 && (
          <button
            onClick={handleClearFilters}
            className="flex items-center gap-1.5 border border-border bg-secondary px-3 py-2 text-[10px] font-black uppercase tracking-wider hover:bg-muted transition-colors"
          >
            <RotateCcw className="h-3 w-3" strokeWidth={3} />
            Clear ({activeFilters.length})
          </button>
        )}
      </div>

      {/* Active filter chips */}
      {activeFilters.length > 0 && (
        <div className="flex flex-wrap gap-2 -mt-2">
          {activeFilters.map(f => (
            <span key={f} className="inline-flex items-center gap-1 border border-border bg-secondary px-2.5 py-1 text-[10px] font-bold">
              {f}
            </span>
          ))}
        </div>
      )}

      {/* Results */}
      {displayed.length === 0 ? (
        <div className="border border-border bg-card p-10 text-center">
          <Zap className="mx-auto h-6 w-6 text-muted-foreground opacity-40 mb-2" />
          <p className="text-sm text-muted-foreground">No units match your current filters.</p>
          <button onClick={handleClearFilters} className="mt-3 text-xs font-bold underline underline-offset-2 text-muted-foreground hover:text-foreground">
            Clear all filters
          </button>
        </div>
      ) : viewMode === "grid" ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {displayed.map(u => (
            <UnitCard
              key={u.property_id}
              unit={u}
              onRequestDemo={handleRequestDemo}
              onAskQuestion={handleAskQuestion}
              onViewDetails={setDetailUnit}
            />
          ))}
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {displayed.map(u => (
            <UnitRow
              key={u.property_id}
              unit={u}
              onRequestDemo={handleRequestDemo}
              onAskQuestion={handleAskQuestion}
              onViewDetails={setDetailUnit}
            />
          ))}
        </div>
      )}

      {/* Detail drawer */}
      {detailUnit && (
        <DetailDrawer
          unit={detailUnit}
          onClose={() => setDetailUnit(null)}
          onRequestDemo={handleRequestDemo}
          onAskQuestion={handleAskQuestion}
        />
      )}
    </div>
  )
}
