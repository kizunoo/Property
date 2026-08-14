"use client"

import { useEffect, useState, useMemo } from "react"
import {
  Building2,
  Crown,
  Flame,
  Loader2,
  MapPin,
  Send,
  Snowflake,
  Users,
  X,
} from "lucide-react"
import { currency, percent, TIER_SHORT, type Property, type Tier } from "@/lib/pipeline-data"
import { fetchShortlist, type ShortlistEntry } from "@/lib/fetch-shortlist"

// ─── Filter types ─────────────────────────────────────────────────────────────
type TierFilter       = "ALL" | "TIER_1" | "TIER_1_2"
type ConfidenceFilter = "ALL" | "HIGH" | "HIGH_MED"

// ─── Sub-components ───────────────────────────────────────────────────────────
function TierIcon({ tier }: { tier: Tier }) {
  if (tier === "TIER_1") return <Crown     className="h-3.5 w-3.5 text-primary"          strokeWidth={2.5} />
  if (tier === "TIER_2") return <Flame     className="h-3.5 w-3.5 text-black"            strokeWidth={2.5} />
  return                        <Snowflake className="h-3.5 w-3.5 text-muted-foreground" strokeWidth={2.5} />
}

function TierBadge({ tier }: { tier: Tier }) {
  const styles: Record<Tier, string> = {
    TIER_1: "bg-primary text-black",
    TIER_2: "bg-black text-white",
    TIER_3: "bg-white text-black",
  }
  return (
    <span className={`inline-block border-2 border-black px-2 py-0.5 font-mono text-[9px] font-black uppercase tracking-wider ${styles[tier]}`}>
      {TIER_SHORT[tier]}
    </span>
  )
}

function ConfidenceBadge({ level }: { level: ShortlistEntry["confidence"] }) {
  const styles = {
    HIGH:   "border-black bg-primary text-black",
    MEDIUM: "border-black bg-white text-black",
    LOW:    "border-black/40 bg-white text-muted-foreground",
  }
  return (
    <span className={`inline-block border-2 px-2 py-0.5 font-mono text-[9px] font-black uppercase tracking-wider ${styles[level]}`}>
      {level}
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
      className={`border-2 border-black px-3 py-1.5 text-[10px] font-black uppercase tracking-wider transition-all ${
        active
          ? "bg-black text-white shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] translate-x-px translate-y-px"
          : "bg-white text-black hover:bg-black hover:text-white"
      }`}
    >
      {children}
    </button>
  )
}

// ─── Skeleton row ─────────────────────────────────────────────────────────────
function SkeletonRow({ rank }: { rank: number }) {
  return (
    <div className="flex items-center gap-3 border-b-2 border-black px-4 py-3 last:border-b-0">
      <span className="flex h-7 w-7 shrink-0 items-center justify-center border-2 border-black bg-black font-mono text-xs font-black text-white">
        {rank}
      </span>
      <div className="flex h-8 w-8 shrink-0 items-center justify-center border-2 border-black bg-black/10 animate-pulse" />
      <div className="flex flex-1 flex-col gap-1.5">
        <div className="h-3 w-32 animate-pulse bg-black/10" />
        <div className="h-2 w-20 animate-pulse bg-black/10" />
      </div>
      <div className="h-2 w-16 animate-pulse bg-black/10" />
      <div className="h-5 w-14 animate-pulse bg-black/10" />
      <div className="h-5 w-16 animate-pulse bg-black/10" />
      <div className="h-5 w-12 animate-pulse bg-black/10" />
    </div>
  )
}

// ─── Ranked row ───────────────────────────────────────────────────────────────
function ShortlistRow({
  entry,
  rank,
  onGenerateInvite,
}: {
  entry: ShortlistEntry
  rank: number
  onGenerateInvite?: (entry: ShortlistEntry) => void
}) {
  return (
    <div className="flex items-center gap-3 border-b-2 border-black px-4 py-3 last:border-b-0 hover:bg-black/[0.02] transition-colors">
      <span className="flex h-7 w-7 shrink-0 items-center justify-center border-2 border-black bg-black font-mono text-xs font-black text-white">
        {rank}
      </span>
      <div className="flex h-8 w-8 shrink-0 items-center justify-center border-2 border-black bg-black text-[10px] font-black text-white">
        {entry.initials}
      </div>
      <div className="flex flex-1 flex-col gap-0.5 overflow-hidden min-w-0">
        <span className="truncate text-sm font-black leading-tight">{entry.name}</span>
        <span className="flex items-center gap-1">
          <TierIcon tier={entry.tier} />
          <span className="text-[10px] font-bold text-muted-foreground">{TIER_SHORT[entry.tier]}</span>
        </span>
      </div>
      {/* P(Buy) bar */}
      <div className="flex shrink-0 flex-col items-end gap-1">
        <span className="font-mono text-xs font-black">{percent(entry.probability)}</span>
        <div className="h-2 w-16 border border-black bg-white">
          <div className="h-full bg-black transition-all" style={{ width: `${Math.round(entry.probability * 100)}%` }} />
        </div>
      </div>
      {/* Tier badge */}
      <TierBadge tier={entry.tier} />
      {/* E(x) */}
      <span className="shrink-0 border-2 border-black px-2 py-0.5 font-mono text-[10px] font-black bg-white inline-flex w-[130px] justify-end">
        {currency(entry.expectedValue)}
      </span>
      {/* Confidence */}
      <ConfidenceBadge level={entry.confidence} />
      {/* Action */}
      <div className="w-[125px] shrink-0 text-right">
        {entry.tier === "TIER_1" || entry.tier === "TIER_2" ? (
          <button
            type="button"
            onClick={() => onGenerateInvite?.(entry)}
            className="inline-flex items-center gap-1 border-2 border-black bg-black px-2.5 py-1 text-[10px] font-black uppercase tracking-wider text-white shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] transition-transform hover:translate-x-0.5 hover:translate-y-0.5 hover:shadow-none"
          >
            <Send className="h-3 w-3 text-primary" strokeWidth={2.5} />
            Invite
          </button>
        ) : (
          <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">—</span>
        )}
      </div>
    </div>
  )
}

// ─── Main modal ───────────────────────────────────────────────────────────────
interface ShortlistModalProps {
  property: Property | null
  open: boolean
  onClose: () => void
  onGenerateInvite?: (entry: ShortlistEntry) => void
}

export function ShortlistModal({ property, open, onClose, onGenerateInvite }: ShortlistModalProps) {
  const [entries,  setEntries]  = useState<ShortlistEntry[]>([])
  const [loading,  setLoading]  = useState(false)
  const [error,    setError]    = useState<string | null>(null)

  const [tierFilter,       setTierFilter]       = useState<TierFilter>("ALL")
  const [confidenceFilter, setConfidenceFilter] = useState<ConfidenceFilter>("ALL")

  // Fetch on open
  useEffect(() => {
    if (!open || !property) return

    setEntries([])
    setLoading(true)
    setError(null)
    setTierFilter("ALL")
    setConfidenceFilter("ALL")

    fetchShortlist(property.id)
      .then(setEntries)
      .catch((err: Error) => setError(err.message ?? "Failed to load shortlist"))
      .finally(() => setLoading(false))
  }, [open, property?.id])

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

  const filtered = useMemo(() => {
    return entries.filter((e) => {
      const tierOk = tierFilter === "ALL"
        || (tierFilter === "TIER_1"   && e.tier === "TIER_1")
        || (tierFilter === "TIER_1_2" && (e.tier === "TIER_1" || e.tier === "TIER_2"))
      const confOk = confidenceFilter === "ALL"
        || (confidenceFilter === "HIGH"     && e.confidence === "HIGH")
        || (confidenceFilter === "HIGH_MED" && (e.confidence === "HIGH" || e.confidence === "MEDIUM"))
      return tierOk && confOk
    })
  }, [entries, tierFilter, confidenceFilter])

  if (!open || !property) return null

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center p-4 sm:p-6 lg:p-10"
      style={{ backgroundColor: "rgba(0,0,0,0.80)" }}
      onClick={onClose}
    >
      <div
        className="relative flex max-h-[90vh] w-full max-w-4xl flex-col overflow-hidden border-4 border-black bg-white shadow-[14px_14px_0px_0px_rgba(0,0,0,1)]"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={`Shortlist for ${property.address}`}
      >
        {/* ── Header ── */}
        <div className="shrink-0 border-b-4 border-black bg-black p-5 sm:p-6">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-center gap-4">
              <div className="flex h-12 w-12 shrink-0 items-center justify-center border-4 border-primary bg-primary">
                <Users className="h-5 w-5 text-black" strokeWidth={2.5} />
              </div>
              <div>
                <div className="text-[10px] font-black uppercase tracking-widest text-white/50">
                  Shortlist Builder
                </div>
                <div className="mt-0.5 text-lg font-black leading-tight text-white sm:text-xl">
                  {property.name}
                </div>
                <div className="mt-1 flex items-center gap-1.5 font-mono text-[11px] text-white/60">
                  <MapPin className="h-3 w-3 shrink-0" strokeWidth={2.5} />
                  {property.address}
                </div>
              </div>
            </div>
            <div className="flex shrink-0 flex-col items-end gap-2">
              <button
                type="button"
                onClick={onClose}
                className="border-2 border-white/40 p-2 text-white transition-colors hover:border-white hover:bg-white hover:text-black"
                aria-label="Close"
              >
                <X className="h-5 w-5" strokeWidth={2.5} />
              </button>
              <div className="border-2 border-primary px-3 py-1 font-mono text-xs font-black text-primary">
                {currency(property.value)}
              </div>
            </div>
          </div>
        </div>

        {/* ── Filter bar ── */}
        <div className="shrink-0 border-b-4 border-black bg-white p-4 sm:px-6">
          <div className="flex flex-wrap items-center gap-4">
            {/* Tier pills */}
            <div className="flex flex-col gap-1.5">
              <span className="text-[9px] font-black uppercase tracking-widest text-muted-foreground">
                Min Tier
              </span>
              <div className="flex gap-1.5">
                <FilterPill active={tierFilter === "ALL"}      onClick={() => setTierFilter("ALL")}>All</FilterPill>
                <FilterPill active={tierFilter === "TIER_1"}   onClick={() => setTierFilter("TIER_1")}>Tier 1 only</FilterPill>
                <FilterPill active={tierFilter === "TIER_1_2"} onClick={() => setTierFilter("TIER_1_2")}>Tier 1 + 2</FilterPill>
              </div>
            </div>

            <div className="h-10 w-px bg-black/20" />

            {/* Confidence pills */}
            <div className="flex flex-col gap-1.5">
              <span className="text-[9px] font-black uppercase tracking-widest text-muted-foreground">
                Min Confidence
              </span>
              <div className="flex gap-1.5">
                <FilterPill active={confidenceFilter === "ALL"}      onClick={() => setConfidenceFilter("ALL")}>All</FilterPill>
                <FilterPill active={confidenceFilter === "HIGH"}     onClick={() => setConfidenceFilter("HIGH")}>High only</FilterPill>
                <FilterPill active={confidenceFilter === "HIGH_MED"} onClick={() => setConfidenceFilter("HIGH_MED")}>Med+</FilterPill>
              </div>
            </div>

            {/* Result count */}
            {!loading && !error && (
              <div className="ml-auto border-4 border-black bg-primary px-4 py-2 font-mono text-xs font-black shadow-[3px_3px_0px_0px_rgba(0,0,0,1)]">
                {filtered.length} result{filtered.length !== 1 ? "s" : ""}
              </div>
            )}
          </div>
        </div>

        {/* ── Table ── */}
        <div className="flex-1 overflow-y-auto">
          {/* Table header */}
          <div className="sticky top-0 z-10 flex items-center gap-3 border-b-4 border-black bg-black px-4 py-2">
            <span className="w-7 shrink-0" />
            <span className="w-8 shrink-0" />
            <span className="flex-1 text-[10px] font-black uppercase tracking-wider text-white">Client</span>
            <span className="w-[88px] shrink-0 text-right text-[10px] font-black uppercase tracking-wider text-white">P(Buy)</span>
            <span className="w-[50px] shrink-0 text-center text-[10px] font-black uppercase tracking-wider text-white">Tier</span>
            <span className="w-[130px] shrink-0 text-right text-[10px] font-black uppercase tracking-wider text-white">E(x)</span>
            <span className="w-[58px] shrink-0 text-center text-[10px] font-black uppercase tracking-wider text-white">Conf.</span>
            <span className="w-[125px] shrink-0 text-right text-[10px] font-black uppercase tracking-wider text-white">Action</span>
          </div>

          {/* Loading */}
          {loading && (
            <div>
              <div className="flex items-center gap-3 border-b-4 border-black bg-white px-4 py-3">
                <Loader2 className="h-4 w-4 animate-spin text-black" strokeWidth={2.5} />
                <span className="text-xs font-black uppercase tracking-wider text-muted-foreground">
                  Scoring all clients against this property…
                </span>
              </div>
              {[1, 2, 3, 4, 5].map((n) => <SkeletonRow key={n} rank={n} />)}
            </div>
          )}

          {/* Error */}
          {!loading && error && (
            <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
              <Building2 className="h-8 w-8 text-muted-foreground" strokeWidth={2} />
              <p className="text-sm font-bold text-muted-foreground">{error}</p>
              <p className="text-[10px] font-black uppercase tracking-wider text-muted-foreground">
                Make sure the backend is running on port 8000
              </p>
            </div>
          )}

          {/* Empty after filter */}
          {!loading && !error && filtered.length === 0 && entries.length > 0 && (
            <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
              <Users className="h-8 w-8 text-muted-foreground" strokeWidth={2} />
              <p className="text-xs font-black uppercase tracking-wider text-muted-foreground">
                No clients match the selected filters
              </p>
              <button
                type="button"
                onClick={() => { setTierFilter("ALL"); setConfidenceFilter("ALL") }}
                className="border-2 border-black px-4 py-2 text-[10px] font-black uppercase tracking-wider hover:bg-black hover:text-white"
              >
                Clear filters
              </button>
            </div>
          )}

          {/* No results at all */}
          {!loading && !error && entries.length === 0 && (
            <div className="flex flex-col items-center justify-center gap-3 py-16">
              <Users className="h-8 w-8 text-muted-foreground" strokeWidth={2} />
              <p className="text-xs font-black uppercase tracking-wider text-muted-foreground">
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
                />
              ))}
            </div>
          )}
        </div>

        {/* ── Footer ── */}
        <div className="shrink-0 border-t-4 border-black px-5 py-4 sm:px-6">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-black uppercase tracking-wider text-muted-foreground">
              Scored by PIPELINE.EV · Top 20 by E(x) · Filters are client-side
            </span>
            <button
              type="button"
              onClick={onClose}
              className="border-2 border-black px-4 py-2 text-xs font-black uppercase tracking-wider hover:bg-black hover:text-white"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
