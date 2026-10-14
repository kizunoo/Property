"use client"

import { useEffect, useState, useMemo, useCallback } from "react"
import {
  ArrowDownUp,
  Building2,
  CheckSquare,
  Crown,
  Flame,
  GitCompare,
  Loader2,
  MapPin,
  Send,
  ShieldCheck,
  Snowflake,
  Square,
  Users,
  Wallet,
  X,
} from "lucide-react"
import { currency, percent, TIER_SHORT, type Property, type Tier } from "@/lib/pipeline-data"
import { fetchShortlist, type ShortlistEntry } from "@/lib/fetch-shortlist"

// ─── Filter + sort types ──────────────────────────────────────────────────────
type TierFilter       = "ALL" | "TIER_1" | "TIER_1_2"
type ConfidenceFilter = "ALL" | "HIGH" | "HIGH_MED"
type SortMode         = "blended" | "formula" | "budget"

// ─── Sub-components ───────────────────────────────────────────────────────────
function TierIcon({ tier }: { tier: Tier }) {
  if (tier === "TIER_1") return <Crown     className="h-3.5 w-3.5 text-primary"          strokeWidth={2.5} />
  if (tier === "TIER_2") return <Flame     className="h-3.5 w-3.5 text-black"            strokeWidth={2.5} />
  return                        <Snowflake className="h-3.5 w-3.5 text-muted-foreground" strokeWidth={2.5} />
}

function TierBadge({ tier }: { tier: Tier }) {
  const styles: Record<Tier, string> = {
    TIER_1: "bg-primary text-black border-primary",
    TIER_2: "bg-black text-white border-black",
    TIER_3: "bg-muted text-foreground border-border",
  }
  return (
    <span className={`inline-block rounded-[var(--radius-sm)] border px-2 py-0.5 font-mono text-[9px] font-bold uppercase tracking-wider ${styles[tier]}`}>
      {TIER_SHORT[tier]}
    </span>
  )
}

function FilterPill({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-[8px] border px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider transition-all ${
        active
          ? "border-neutral-900 bg-black text-white shadow-[var(--shadow-xs)]"
          : "border-border bg-card text-foreground hover:bg-muted shadow-[var(--shadow-xs)]"
      }`}
    >
      {children}
    </button>
  )
}

// ─── Blended score bar ────────────────────────────────────────────────────────
function BlendedBar({ entry }: { entry: ShortlistEntry }) {
  const blended     = Math.round(entry.blendedScore * 100)
  const formulaPct  = Math.round(entry.formulaScore * 100)
  const hasMl       = entry.mlProbability !== null
  // ML portion within the blended bar
  const mlShare     = hasMl ? Math.round((entry.blendedScore - entry.formulaScore * 0.7) * 100 / Math.max(entry.blendedScore, 0.01)) : 0
  const formulaShare = 100 - Math.max(mlShare, 0)

  return (
    <div className="flex shrink-0 flex-col items-end gap-1 min-w-[80px]">
      <div className="flex items-baseline gap-1">
        <span className="font-mono text-xs font-bold text-foreground">{blended}%</span>
        {hasMl && (
          <span className="font-mono text-[9px] text-muted-foreground">blend</span>
        )}
      </div>
      <div className="h-2 w-20 rounded-full overflow-hidden bg-muted flex">
        {/* Formula portion (black) */}
        <div
          className="h-full bg-black transition-all"
          style={{ width: `${Math.min(formulaShare * blended / 100, blended)}%` }}
        />
        {/* ML portion (yellow/primary) */}
        {hasMl && (
          <div
            className="h-full bg-primary transition-all"
            style={{ width: `${Math.max(mlShare * blended / 100, 0)}%` }}
          />
        )}
      </div>
      {hasMl && (
        <span className="text-[8px] font-semibold text-muted-foreground uppercase tracking-wide">
          ML+Formula
        </span>
      )}
    </div>
  )
}

// ─── Pick/Skip reason chip ────────────────────────────────────────────────────
function ReasonChip({ text, isSkip }: { text: string; isSkip: boolean }) {
  if (!text) return null
  return (
    <span
      className={`inline-block max-w-full truncate rounded-[4px] px-1.5 py-0.5 text-[9px] font-semibold leading-tight ${
        isSkip
          ? "bg-neutral-100 text-neutral-500 border border-neutral-200"
          : "bg-emerald-50 text-emerald-700 border border-emerald-200"
      }`}
      title={text}
    >
      {text}
    </span>
  )
}

// ─── Skeleton row ─────────────────────────────────────────────────────────────
function SkeletonRow({ rank }: { rank: number }) {
  return (
    <div className="flex items-center gap-3 border-b border-border px-4 py-3 last:border-b-0">
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-[6px] bg-muted font-mono text-xs font-bold text-muted-foreground">
        {rank}
      </span>
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[6px] bg-muted animate-pulse" />
      <div className="flex flex-1 flex-col gap-1.5">
        <div className="h-3 w-32 animate-pulse bg-muted rounded" />
        <div className="h-2 w-44 animate-pulse bg-muted rounded" />
      </div>
      <div className="h-2 w-20 animate-pulse bg-muted rounded" />
      <div className="h-5 w-14 animate-pulse bg-muted rounded" />
      <div className="h-5 w-16 animate-pulse bg-muted rounded" />
      <div className="h-5 w-12 animate-pulse bg-muted rounded" />
    </div>
  )
}

// ─── Ranked row ───────────────────────────────────────────────────────────────
function ShortlistRow({
  entry,
  rank,
  onGenerateInvite,
  compareMode,
  compareSelected,
  onToggleCompare,
}: {
  entry: ShortlistEntry
  rank: number
  onGenerateInvite?: (entry: ShortlistEntry) => void
  compareMode: boolean
  compareSelected: boolean
  onToggleCompare: (id: string) => void
}) {
  const showSkip = entry.tier === "TIER_3"

  return (
    <div className={`group flex items-start gap-3 border-b border-border px-4 py-3 last:border-b-0 hover:bg-muted/30 transition-colors ${compareSelected ? "bg-primary/5 border-l-2 border-l-primary" : ""}`}>
      {/* Compare checkbox */}
      {compareMode && (
        <button
          type="button"
          onClick={() => onToggleCompare(entry.clientId)}
          className="mt-0.5 shrink-0 text-muted-foreground hover:text-foreground transition-colors"
          aria-label={compareSelected ? "Remove from compare" : "Add to compare"}
        >
          {compareSelected
            ? <CheckSquare className="h-4 w-4 text-primary" strokeWidth={2.5} />
            : <Square      className="h-4 w-4"              strokeWidth={2} />
          }
        </button>
      )}

      {/* Rank */}
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-[6px] bg-muted font-mono text-xs font-bold text-foreground">
        {rank}
      </span>

      {/* Avatar */}
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[6px] bg-black text-[10px] font-bold text-white mt-0.5">
        {entry.initials}
      </div>

      {/* Name + tier + reason */}
      <div className="flex flex-1 flex-col gap-0.5 overflow-hidden min-w-0">
        <span className="truncate text-sm font-bold leading-tight text-foreground">{entry.name}</span>
        <span className="flex items-center gap-1">
          <TierIcon tier={entry.tier} />
          <span className="text-[10px] font-semibold text-muted-foreground">{TIER_SHORT[entry.tier]}</span>
        </span>
        <div className="mt-0.5">
          <ReasonChip
            text={showSkip ? entry.skipReason : entry.pickReason}
            isSkip={showSkip}
          />
        </div>
      </div>

      {/* Blended score bar */}
      <BlendedBar entry={entry} />

      {/* Tier badge */}
      <div className="shrink-0 mt-1">
        <TierBadge tier={entry.tier} />
      </div>

      {/* Blended E(x) & Formula E(x) */}
      <div className="shrink-0 flex flex-col items-end w-[130px] mt-0.5">
        <span className="rounded-[var(--radius-sm)] border border-border px-2 py-0.5 font-mono text-[10px] font-bold bg-card text-foreground inline-flex justify-end shadow-[var(--shadow-xs)]">
          {currency(entry.blendedExpectedValue)}
        </span>
        {entry.mlProbability !== null ? (
          <span
            className="font-mono text-[9px] text-muted-foreground mt-0.5 pr-0.5"
            title="Rule-based formula expected value"
          >
            formula: {currency(entry.expectedValue)}
          </span>
        ) : (
          <span className="font-mono text-[8px] text-muted-foreground/60 mt-0.5 pr-0.5">
            formula-only
          </span>
        )}
      </div>

      {/* Action */}
      <div className="w-[110px] shrink-0 text-right mt-1">
        {entry.tier === "TIER_1" || entry.tier === "TIER_2" ? (
          <button
            type="button"
            onClick={() => onGenerateInvite?.(entry)}
            className="inline-flex items-center gap-1.5 rounded-[6px] border border-border bg-black px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-white shadow-[var(--shadow-xs)] transition-colors hover:bg-neutral-800"
          >
            <Send className="h-3 w-3 text-primary" strokeWidth={2.5} />
            Pitch
          </button>
        ) : (
          <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">—</span>
        )}
      </div>
    </div>
  )
}

// ─── Compare panel ────────────────────────────────────────────────────────────
function ComparePanel({
  entries,
  propertyValue,
  onInvite,
  onRemove,
}: {
  entries: ShortlistEntry[]
  propertyValue: number
  onInvite?: (e: ShortlistEntry) => void
  onRemove: (id: string) => void
}) {
  if (entries.length === 0) return null

  const fmt = (v: number | null) =>
    v != null ? `RM ${v.toLocaleString()}` : "—"
  const pct = (v: number | null) =>
    v != null ? `${Math.round(v * 100)}%` : "—"

  return (
    <div className="shrink-0 border-t-2 border-primary bg-card">
      <div className="px-5 py-3 flex items-center justify-between">
        <span className="text-[10px] font-bold uppercase tracking-widest text-primary">
          Compare Mode — {entries.length} of 3 selected
        </span>
        <span className="text-[10px] text-muted-foreground">Select up to 3 companies to compare</span>
      </div>
      <div className={`grid gap-0 divide-x divide-border border-t border-border`} style={{ gridTemplateColumns: `repeat(${entries.length}, 1fr)` }}>
        {entries.map((e) => {
          const budgetVsPrice = e.statedBudget != null
            ? e.statedBudget >= propertyValue
              ? "✓ Covers unit cost"
              : `${Math.round((e.statedBudget / propertyValue) * 100)}% of unit cost`
            : "—"
          return (
            <div key={e.clientId} className="p-4 flex flex-col gap-2.5 relative">
              <button
                onClick={() => onRemove(e.clientId)}
                className="absolute top-3 right-3 text-muted-foreground hover:text-foreground"
              >
                <X className="h-3.5 w-3.5" strokeWidth={2.5} />
              </button>
              {/* Header */}
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <div className="flex h-7 w-7 items-center justify-center rounded-[6px] bg-black text-[10px] font-bold text-white">
                    {e.initials}
                  </div>
                  <span className="font-bold text-sm text-foreground truncate pr-4">{e.name}</span>
                </div>
                <TierBadge tier={e.tier} />
              </div>

              {/* Stats */}
              <div className="flex flex-col gap-1.5 text-xs">
                <div className="flex justify-between gap-2">
                  <span className="text-muted-foreground font-medium">Blended Score</span>
                  <span className="font-mono font-bold">{Math.round(e.blendedScore * 100)}%</span>
                </div>
                <div className="flex justify-between gap-2">
                  <span className="text-muted-foreground font-medium">Budget vs Unit Cost</span>
                  <span className={`font-mono font-bold ${e.statedBudget != null && e.statedBudget >= propertyValue ? "text-emerald-700" : "text-neutral-500"}`}>
                    {budgetVsPrice}
                  </span>
                </div>
                <div className="flex justify-between gap-2">
                  <span className="text-muted-foreground font-medium">Environment Match</span>
                  <span className="font-mono font-bold">
                    {e.pickReason?.includes("✓ Area") || e.pickReason?.includes("✓ Secondary")
                      ? <span className="text-emerald-700">✓</span>
                      : <span className="text-neutral-400">✗</span>
                    }
                  </span>
                </div>
                <div className="flex justify-between gap-2">
                  <span className="text-muted-foreground font-medium">Demos</span>
                  <span className="font-mono font-bold">{e.pastViewings}</span>
                </div>
                <div className="flex justify-between gap-2">
                  <span className="text-muted-foreground font-medium">Financing</span>
                  <span className="font-mono font-bold capitalize">{e.financingStatus ?? "—"}</span>
                </div>
                <div className="flex justify-between gap-2">
                  <span className="text-muted-foreground font-medium">Deploy Timeline</span>
                  <span className="font-mono font-bold">{e.moveInTimeline ?? "—"}</span>
                </div>
                <div className="flex justify-between gap-2">
                  <span className="text-muted-foreground font-medium">Track Record</span>
                  <span className="font-mono font-bold">
                    {(e.pastPurchasesCount ?? 0) > 0 ? (
                      <span className="inline-flex items-center gap-1 text-amber-800 font-bold text-[11px]">
                        <ShieldCheck className="h-3 w-3 text-amber-700" strokeWidth={2.5} />
                        {e.pastPurchasesCount} Deployed (Proven)
                      </span>
                    ) : (
                      <span className="text-neutral-400 font-medium">First-time</span>
                    )}
                  </span>
                </div>
                <div className="flex justify-between gap-2">
                  <span className="text-muted-foreground font-medium">Blended E(x)</span>
                  <span className="font-mono font-bold">{currency(e.blendedExpectedValue)}</span>
                </div>
                {e.mlProbability !== null && (
                  <div className="flex justify-between gap-2 -mt-1">
                    <span className="text-muted-foreground text-[10px]">Formula E(x)</span>
                    <span className="font-mono text-[10px] text-muted-foreground">{currency(e.expectedValue)}</span>
                  </div>
                )}
              </div>

              {/* Verdict chip */}
              <div className="mt-1">
                <ReasonChip
                  text={e.tier === "TIER_3" ? e.skipReason : e.pickReason}
                  isSkip={e.tier === "TIER_3"}
                />
              </div>

              {/* Invite CTA */}
              {(e.tier === "TIER_1" || e.tier === "TIER_2") && (
                <button
                  onClick={() => onInvite?.(e)}
                  className="mt-auto flex w-full items-center justify-center gap-1.5 rounded-[6px] border border-border bg-black py-1.5 text-[10px] font-bold uppercase tracking-wider text-white hover:bg-neutral-800 transition-colors"
                >
                  <Send className="h-3 w-3 text-primary" strokeWidth={2.5} />
                  Send Pitch
                </button>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ─── Main modal ───────────────────────────────────────────────────────────────
interface ShortlistModalProps {
  property: Property | null
  open: boolean
  onClose: () => void
  agentId?: string | null
  onGenerateInvite?: (entry: ShortlistEntry) => void
}

export function ShortlistModal({ property, open, onClose, agentId, onGenerateInvite }: ShortlistModalProps) {
  const [entries,  setEntries]  = useState<ShortlistEntry[]>([])
  const [loading,  setLoading]  = useState(false)
  const [error,    setError]    = useState<string | null>(null)

  const [tierFilter,       setTierFilter]       = useState<TierFilter>("ALL")
  const [confidenceFilter, setConfidenceFilter] = useState<ConfidenceFilter>("ALL")
  const [sortMode,         setSortMode]         = useState<SortMode>("blended")
  const [compareMode,      setCompareMode]      = useState(false)
  const [compareIds,       setCompareIds]       = useState<Set<string>>(new Set())

  // Fetch on open
  useEffect(() => {
    if (!open || !property) return

    setEntries([])
    setLoading(true)
    setError(null)
    setTierFilter("ALL")
    setConfidenceFilter("ALL")
    setSortMode("blended")
    setCompareMode(false)
    setCompareIds(new Set())

    fetchShortlist(property.id, agentId)
      .then(setEntries)
      .catch((err: Error) => setError(err.message ?? "Failed to load shortlist"))
      .finally(() => setLoading(false))
  }, [open, property?.id, agentId])

  // Escape key
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose() }
    document.addEventListener("keydown", onKey)
    return () => document.removeEventListener("keydown", onKey)
  }, [open, onClose])

  // Scroll lock
  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : ""
    return () => { document.body.style.overflow = "" }
  }, [open])

  const handleToggleCompare = useCallback((id: string) => {
    setCompareIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else if (next.size < 3) {
        next.add(id)
      }
      return next
    })
  }, [])

  const compareEntries = useMemo(
    () => entries.filter((e) => compareIds.has(e.clientId)),
    [entries, compareIds],
  )

  const filtered = useMemo(() => {
    const f = entries.filter((e) => {
      const tierOk = tierFilter === "ALL"
        || (tierFilter === "TIER_1"   && e.tier === "TIER_1")
        || (tierFilter === "TIER_1_2" && (e.tier === "TIER_1" || e.tier === "TIER_2"))
      const confOk = confidenceFilter === "ALL"
        || (confidenceFilter === "HIGH"     && e.confidence === "HIGH")
        || (confidenceFilter === "HIGH_MED" && (e.confidence === "HIGH" || e.confidence === "MEDIUM"))
      return tierOk && confOk
    })

    // Sort
    return [...f].sort((a, b) => {
      if (sortMode === "formula")  return b.formulaScore - a.formulaScore
      if (sortMode === "budget")   return b.budgetRatio - a.budgetRatio
      return b.blendedExpectedValue - a.blendedExpectedValue  // default: blended E(x)
    })
  }, [entries, tierFilter, confidenceFilter, sortMode])

  if (!open || !property) return null

  const hasMl = entries.some((e) => e.mlProbability !== null)

  return (
    <div
      className="fixed inset-0 z-[60] flex items-end sm:items-center justify-center sm:p-4 lg:p-10"
      style={{ backgroundColor: "rgba(0,0,0,0.65)" }}
      onClick={onClose}
    >
      <div
        className="relative flex max-h-[95vh] sm:max-h-[90vh] w-full max-w-4xl flex-col overflow-hidden rounded-t-[16px] sm:rounded-[12px] border border-border bg-card shadow-[var(--shadow-xl)]"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={`Shortlist for ${property.address}`}
      >
        {/* ── Header ── */}
        <div className="shrink-0 border-b border-border bg-transparent p-5 sm:p-6">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-center gap-3.5">
              <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-[8px] bg-black">
                <Users className="h-5 w-5 text-primary" strokeWidth={2.5} />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
                    Shortlist v2
                  </span>
                  {hasMl && (
                    <span className="rounded-[4px] bg-primary/20 border border-primary/30 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-foreground">
                      ML+Formula
                    </span>
                  )}
                </div>
                <div className="mt-0.5 text-lg font-bold leading-tight text-foreground sm:text-xl">
                  {property.address || property.name}
                </div>
                <div className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
                  <MapPin className="h-3 w-3 shrink-0 text-muted-foreground" strokeWidth={2.5} />
                  {property.neighborhood}
                </div>
              </div>
            </div>
            <div className="flex shrink-0 flex-col items-end gap-2">
              <button
                type="button"
                onClick={onClose}
                className="rounded-[var(--radius-sm)] border border-border p-2 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                aria-label="Close"
              >
                <X className="h-5 w-5" strokeWidth={2.5} />
              </button>
              <div className="flex items-center gap-1.5 rounded-[var(--radius-sm)] border border-border bg-muted px-3 py-1 font-display text-xs font-bold text-foreground">
                <Wallet className="h-3 w-3 text-muted-foreground" strokeWidth={2.5} />
                {currency(property.value)}
              </div>
            </div>
          </div>
        </div>

        {/* ── Filter + sort bar ── */}
        <div className="shrink-0 border-b border-border bg-card p-4 sm:px-6">
          <div className="flex flex-wrap items-center gap-4">
            {/* Tier pills */}
            <div className="flex flex-col gap-1.5">
              <span className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground">Min Tier</span>
              <div className="flex gap-1.5">
                <FilterPill active={tierFilter === "ALL"}      onClick={() => setTierFilter("ALL")}>All</FilterPill>
                <FilterPill active={tierFilter === "TIER_1"}   onClick={() => setTierFilter("TIER_1")}>Tier 1</FilterPill>
                <FilterPill active={tierFilter === "TIER_1_2"} onClick={() => setTierFilter("TIER_1_2")}>Tier 1+2</FilterPill>
              </div>
            </div>

            <div className="h-8 w-px bg-border" />

            {/* Confidence pills */}
            <div className="flex flex-col gap-1.5">
              <span className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground">Confidence</span>
              <div className="flex gap-1.5">
                <FilterPill active={confidenceFilter === "ALL"}      onClick={() => setConfidenceFilter("ALL")}>All</FilterPill>
                <FilterPill active={confidenceFilter === "HIGH"}     onClick={() => setConfidenceFilter("HIGH")}>High</FilterPill>
                <FilterPill active={confidenceFilter === "HIGH_MED"} onClick={() => setConfidenceFilter("HIGH_MED")}>Med+</FilterPill>
              </div>
            </div>

            <div className="h-8 w-px bg-border" />

            {/* Sort mode */}
            <div className="flex flex-col gap-1.5">
              <span className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground">
                <ArrowDownUp className="inline h-2.5 w-2.5 mr-1" strokeWidth={2.5} />Sort
              </span>
              <div className="flex gap-1.5">
                <FilterPill active={sortMode === "blended"} onClick={() => setSortMode("blended")}>Blended</FilterPill>
                <FilterPill active={sortMode === "formula"} onClick={() => setSortMode("formula")}>P(Buy)</FilterPill>
                <FilterPill active={sortMode === "budget"}  onClick={() => setSortMode("budget")}>Budget Fit</FilterPill>
              </div>
            </div>

            <div className="h-8 w-px bg-border hidden sm:block" />

            {/* Compare toggle */}
            <div className="flex flex-col gap-1.5">
              <span className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground">
                <GitCompare className="inline h-2.5 w-2.5 mr-1" strokeWidth={2.5} />Compare
              </span>
              <button
                type="button"
                onClick={() => {
                  setCompareMode((v) => !v)
                  if (compareMode) setCompareIds(new Set())
                }}
                className={`rounded-[8px] border px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider transition-all ${
                  compareMode
                    ? "border-primary bg-primary text-black shadow-[var(--shadow-xs)]"
                    : "border-border bg-card text-foreground hover:bg-muted shadow-[var(--shadow-xs)]"
                }`}
              >
                {compareMode ? `${compareIds.size}/3 Selected` : "Compare"}
              </button>
            </div>

            {/* Result count */}
            {!loading && !error && (
              <div className="ml-auto rounded-[var(--radius-sm)] border border-border bg-muted px-3 py-1.5 font-mono text-xs font-semibold text-muted-foreground">
                {filtered.length} {filtered.length === 1 ? "result" : "results"}
              </div>
            )}
          </div>
        </div>

        {/* ── Table ── */}
        <div className="flex-1 overflow-y-auto">
          {/* Table header */}
          <div className="sticky top-0 z-10 flex items-center gap-3 border-b border-border bg-muted/40 backdrop-blur-sm px-4 py-2.5">
            {compareMode && <span className="w-4 shrink-0" />}
            <span className="w-7 shrink-0" />
            <span className="w-8 shrink-0" />
            <span className="flex-1 text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Client</span>
            <span className="w-[88px] shrink-0 text-right text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
              {sortMode === "blended" ? "Blended" : sortMode === "formula" ? "P(Buy)" : "Budget Fit"}
            </span>
            <span className="w-[50px] shrink-0 text-center text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Tier</span>
            <span className="w-[130px] shrink-0 text-right text-[10px] font-bold uppercase tracking-wider text-muted-foreground inline-flex items-center justify-end gap-1">
              E(x)
              {hasMl && (
                <span
                  className="rounded-[3px] bg-primary/20 border border-primary/40 px-1 py-0.2 text-[8px] font-bold tracking-tight text-foreground uppercase"
                  title="Blended ranking: 60% formula + 40% ML model"
                >
                  ML-adj
                </span>
              )}
            </span>
            <span className="w-[110px] shrink-0 text-right text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Action</span>
          </div>

          {/* Loading */}
          {loading && (
            <div>
              <div className="flex items-center gap-3 border-b border-border bg-card px-4 py-3">
                <Loader2 className="h-4 w-4 animate-spin text-foreground" strokeWidth={2.5} />
                <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Ranking clients with ML+Formula blend…
                </span>
              </div>
              {[1, 2, 3, 4, 5].map((n) => <SkeletonRow key={n} rank={n} />)}
            </div>
          )}

          {/* Error */}
          {!loading && error && (
            <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
              <Building2 className="h-8 w-8 text-muted-foreground" strokeWidth={2} />
              <p className="text-sm font-semibold text-muted-foreground">{error}</p>
              <p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                Make sure the backend is running on port 8000
              </p>
            </div>
          )}

          {/* Empty after filter */}
          {!loading && !error && filtered.length === 0 && entries.length > 0 && (
            <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
              <Users className="h-8 w-8 text-muted-foreground" strokeWidth={2} />
              <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                No clients match the selected filters
              </p>
              <button
                type="button"
                onClick={() => { setTierFilter("ALL"); setConfidenceFilter("ALL") }}
                className="rounded-[var(--radius-sm)] border border-border px-3 py-1.5 text-xs font-bold uppercase tracking-wider hover:bg-muted"
              >
                Clear filters
              </button>
            </div>
          )}

          {/* No results at all */}
          {!loading && !error && entries.length === 0 && (
            <div className="flex flex-col items-center justify-center gap-3 py-16">
              <Users className="h-8 w-8 text-muted-foreground" strokeWidth={2} />
              <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                No clients in pipeline
              </p>
            </div>
          )}

          {/* Ranked rows */}
          {!loading && !error && filtered.length > 0 && (
            <div>
              {filtered.map((entry, i) => (
                <ShortlistRow
                  key={entry.clientId}
                  entry={entry}
                  rank={i + 1}
                  onGenerateInvite={onGenerateInvite}
                  compareMode={compareMode}
                  compareSelected={compareIds.has(entry.clientId)}
                  onToggleCompare={handleToggleCompare}
                />
              ))}
            </div>
          )}
        </div>

        {/* ── Compare panel (inline, above footer) ── */}
        {compareMode && compareEntries.length > 0 && (
          <ComparePanel
            entries={compareEntries}
            propertyValue={property.value}
            onInvite={onGenerateInvite}
            onRemove={(id) => handleToggleCompare(id)}
          />
        )}

        {/* ── Footer ── */}
        <div className="shrink-0 border-t border-border px-5 py-4 sm:px-6 bg-card">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              {hasMl
                ? "Ranked by ML + formula blend · Top 25 shown · Filters client-side"
                : "Ranked by formula P(Adopt) · Top 25 shown · Train model to enable ML blend"
              }
            </span>
            <button
              type="button"
              onClick={onClose}
              className="rounded-[var(--radius-sm)] border border-border px-4 py-2 text-xs font-bold uppercase tracking-wider hover:bg-muted transition-colors"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
