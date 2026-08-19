"use client"

import { useEffect, useRef, useState } from "react"
import {
  Brain,
  Building2,
  Calendar,
  CalendarCheck,
  CheckCircle2,
  Eye,
  Layers,
  Loader2,
  MapPin,
  Send,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  Trophy,
  Wallet,
  X,
} from "lucide-react"
import { TIER_SHORT, currency, percent, type DeduplicatedClient } from "@/lib/pipeline-data"
import { fetchReasoning } from "@/lib/generate-reasoning"
import { logViewing, type ViewingResult } from "@/lib/log-viewing"
import { scheduleViewing } from "@/lib/schedule-viewing"

// ─── Probability decomposition ────────────────────────────────────────────────
interface ScoreRow { label: string; points: number; max: number; earned: boolean }

function buildScoreRows(client: DeduplicatedClient): ScoreRow[] {
  const budget   = client.statedBudget
  const propVal  = client.bestMatch.propertyValue
  const prefNbhd = client.preferredNeighborhood
  const propNbhd = client.bestMatch.neighborhood
  const viewings = client.pastViewings

  // 1. Base Probability: always +10%
  const basePts = 10

  // 2. Financial Fit: calculated directly using the continuous ratio formula matching scoring_engine.py
  let finFactor = 0
  if (budget > 0 && propVal > 0) {
    if (budget >= propVal) {
      const ratio = propVal / budget
      finFactor = 0.5 + 0.5 * Math.min(1.0, ratio)
    } else {
      const ratio = budget / propVal
      finFactor = 0.5 * Math.max(0.0, ratio)
    }
  }
  const finPts = Math.round(40 * finFactor)

  // 3. Geo Match: +30% if preferred neighborhood matches target listing neighborhood, else 0%
  const geoPts = (prefNbhd && prefNbhd === propNbhd) ? 30 : 0

  // 4. Engagement Bonus: +10% per past viewing, capped at +20%
  const engagementPts = Math.min((viewings || 0) * 10, 20)

  return [
    { label: "Base Probability", points: basePts,       max: 10, earned: basePts > 0 },
    { label: "Financial Fit",    points: finPts,        max: 40, earned: finPts > 0 },
    { label: "Geo Match",        points: geoPts,        max: 30, earned: geoPts > 0 },
    { label: "Engagement Bonus", points: engagementPts, max: 20, earned: engagementPts > 0 },
  ]
}

// ─── Sub-components ───────────────────────────────────────────────────────────
function TierBadge({ tier }: { tier: DeduplicatedClient["tier"] }) {
  const styles: Record<DeduplicatedClient["tier"], string> = {
    TIER_1: "bg-primary text-black",
    TIER_2: "bg-black text-white",
    TIER_3: "bg-white text-black",
  }
  return (
    <span className={`inline-block border border-neutral-200 px-3 py-1 text-xs font-black uppercase tracking-wider ${styles[tier]}`}>
      {TIER_SHORT[tier]}
    </span>
  )
}

function ScoreBar({ row }: { row: ScoreRow }) {
  const pct = row.max > 0 ? (row.points / row.max) * 100 : 0
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-black uppercase tracking-wider">{row.label}</span>
        <span className={`font-mono text-xs font-black ${row.earned ? "text-black" : "text-muted-foreground"}`}>
          {row.earned ? `+${row.points}%` : "—"}
          <span className="font-bold text-muted-foreground"> / {row.max}%</span>
        </span>
      </div>
      <div className="h-3 w-full border border-neutral-200 bg-white">
        <div
          className={`h-full transition-all duration-300 ${row.earned ? "bg-black" : "bg-transparent"}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2 border-b border-neutral-200 pb-2">
      <span className="text-[10px] font-black uppercase tracking-widest text-muted-foreground">{children}</span>
    </div>
  )
}

function StatRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between border-b border-dashed border-black/30 py-2.5 last:border-0">
      <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">{label}</span>
      <span className="font-mono text-sm font-black">{value}</span>
    </div>
  )
}

// ─── Match list (other properties) ───────────────────────────────────────────
function OtherMatchRow({ match, rank }: { match: DeduplicatedClient["allMatches"][0]; rank: number }) {
  return (
    <div className="flex items-center gap-3 border-b border-neutral-200 px-4 py-3 last:border-b-0">
      <span className="flex h-6 w-6 shrink-0 items-center justify-center border border-neutral-200 bg-black font-mono text-[10px] font-black text-white">
        {rank}
      </span>
      <div className="flex-1 overflow-hidden">
        <div className="flex items-center gap-1 text-sm font-bold">
          <MapPin className="h-3 w-3 shrink-0 text-muted-foreground" strokeWidth={2.5} />
          <span className="truncate">{match.property}</span>
        </div>
        <div className="font-mono text-[10px] text-muted-foreground">{match.agent}</div>
      </div>
      <div className="text-right">
        <div className="font-mono text-xs font-black">{percent(match.probability)}</div>
        <div className="font-mono text-xs text-muted-foreground">{currency(match.expectedValue)}</div>
      </div>
    </div>
  )
}

// ─── Reasoning box sub-component ─────────────────────────────────────────────
function ReasoningBox({
  loading,
  error,
  text,
}: {
  loading: boolean
  error: string | null
  text: string | null
}) {
  if (loading) {
    return (
      <div className="mt-3 border border-neutral-200 bg-black p-4 shadow-[0px_2px_8px_rgba(0,0,0,0.08)]">
        <div className="flex items-center gap-2">
          <Loader2 className="h-4 w-4 shrink-0 animate-spin text-primary" strokeWidth={2.5} />
          <span className="font-mono text-xs font-black uppercase tracking-widest text-white/60">
            Generating analysis…
          </span>
        </div>
        {/* Skeleton lines */}
        <div className="mt-3 flex flex-col gap-2">
          <div className="h-3 w-full animate-pulse bg-white/10" />
          <div className="h-3 w-[90%] animate-pulse bg-white/10" />
          <div className="h-3 w-[75%] animate-pulse bg-white/10" />
          <div className="h-3 w-[85%] animate-pulse bg-white/10" />
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="mt-3 border border-neutral-200 bg-white p-4 shadow-[0px_2px_8px_rgba(0,0,0,0.08)]">
        <div className="flex gap-2">
          <Brain className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" strokeWidth={2.5} />
          <div>
            <p className="text-sm font-bold leading-relaxed text-muted-foreground">
              {error}
            </p>
            <p className="mt-1 text-[10px] font-black uppercase tracking-wider text-muted-foreground">
              Close and reopen to retry
            </p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="mt-3 border border-neutral-200 bg-primary p-4 shadow-[0px_2px_8px_rgba(0,0,0,0.08)]">
      <div className="flex gap-2">
        <Brain className="mt-0.5 h-4 w-4 shrink-0 text-black" strokeWidth={2.5} />
        <p className="text-sm font-bold leading-relaxed text-black">{text}</p>
      </div>
    </div>
  )
}

// ─── Main modal ───────────────────────────────────────────────────────────────
interface ClientDetailModalProps {
  client: DeduplicatedClient | null
  open: boolean
  onClose: () => void
  onGenerateInvite?: (client: DeduplicatedClient) => void
  onOutcomeRecorded?: () => void
}

export function ClientDetailModal({ client, open, onClose, onGenerateInvite, onOutcomeRecorded }: ClientDetailModalProps) {
  // ── Reasoning state ──────────────────────────────────────────────────────
  const [reasoning, setReasoning]               = useState<string | null>(null)
  const [reasoningLoading, setReasoningLoading] = useState(false)
  const [reasoningError, setReasoningError]     = useState<string | null>(null)

  // ── Log Viewing state ─────────────────────────────────────────────────────
  const [viewingLoading, setViewingLoading] = useState(false)
  const [viewingResult, setViewingResult]   = useState<ViewingResult | null>(null)
  const [viewingError, setViewingError]     = useState<string | null>(null)
  const confirmTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Local overrides so the modal reflects new scores immediately without a reload
  const [localPastViewings, setLocalPastViewings]   = useState<number | null>(null)
  const [localProbability, setLocalProbability]     = useState<number | null>(null)
  const [localExpectedValue, setLocalExpectedValue] = useState<number | null>(null)
  const [localTier, setLocalTier]                   = useState<DeduplicatedClient["tier"] | null>(null)

  // ── Schedule Viewing (future) state ──────────────────────────────────────
  const [schedFormOpen, setSchedFormOpen]     = useState(false)
  const [schedDate, setSchedDate]             = useState("")
  const [schedTime, setSchedTime]             = useState("")
  const [schedLoading, setSchedLoading]       = useState(false)
  const [schedError, setSchedError]           = useState<string | null>(null)
  const [schedSuccess, setSchedSuccess]       = useState<string | null>(null)
  const schedSuccessTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  // ── Outcome (won/lost) state ───────────────────────────────────────────────
  const [outcomeLoading, setOutcomeLoading]   = useState(false)
  const [outcomeResult, setOutcomeResult]     = useState<"won" | "lost" | null>(null)
  const [outcomeError, setOutcomeError]       = useState<string | null>(null)
  const outcomeTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Reset local overrides when a different client is opened
  const prevClientId = useRef<string | null>(null)
  useEffect(() => {
    if (client?.clientId !== prevClientId.current) {
      prevClientId.current = client?.clientId ?? null
      setLocalPastViewings(null)
      setLocalProbability(null)
      setLocalExpectedValue(null)
      setLocalTier(null)
      setViewingResult(null)
      setViewingError(null)
      setOutcomeResult(null)
      setOutcomeError(null)
      setSchedFormOpen(false)
      setSchedDate("")
      setSchedTime("")
      setSchedError(null)
      setSchedSuccess(null)
      if (confirmTimerRef.current) clearTimeout(confirmTimerRef.current)
      if (schedSuccessTimer.current) clearTimeout(schedSuccessTimer.current)
    }
  }, [client?.clientId])

  const handleLogViewing = async () => {
    if (!client || viewingLoading) return
    setViewingLoading(true)
    setViewingError(null)
    setViewingResult(null)
    try {
      const result = await logViewing(client.clientId, client.bestMatch.propertyId)
      setViewingResult(result)
      setLocalPastViewings(result.pastViewings)
      setLocalProbability(result.probability)
      setLocalExpectedValue(result.expectedValue)
      setLocalTier(result.tier as DeduplicatedClient["tier"])
      // Auto-dismiss confirmation banner after 7 seconds
      confirmTimerRef.current = setTimeout(() => setViewingResult(null), 7000)
    } catch (err) {
      setViewingError(err instanceof Error ? err.message : "Failed to log viewing")
    } finally {
      setViewingLoading(false)
    }
  }

  const handleScheduleViewingSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!client || schedLoading || !schedDate || !schedTime) return
    setSchedLoading(true)
    setSchedError(null)
    setSchedSuccess(null)
    try {
      const localDateObj = new Date(`${schedDate}T${schedTime}:00`)
      const isoDateTime = localDateObj.toISOString()
      await scheduleViewing(client.clientId, client.bestMatch.propertyId, isoDateTime)
      const displayDate = localDateObj.toLocaleString("en-MY", {
        dateStyle: "medium", timeStyle: "short",
      })
      setSchedSuccess(`Viewing scheduled for ${displayDate}`)
      setSchedFormOpen(false)
      setSchedDate("")
      setSchedTime("")
      schedSuccessTimer.current = setTimeout(() => setSchedSuccess(null), 7000)
    } catch (err) {
      setSchedError(err instanceof Error ? err.message : "Failed to schedule viewing")
    } finally {
      setSchedLoading(false)
    }
  }

  const handleRecordOutcome = async (outcome: "won" | "lost") => {
    if (!client || outcomeLoading) return
    setOutcomeLoading(true)
    setOutcomeError(null)
    try {
      const res = await fetch("/api/record_outcome", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          client_id: client.clientId,
          property_id: client.bestMatch.propertyId,
          outcome,
        }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail ?? "Failed to record outcome")
      }
      setOutcomeResult(outcome)
      if (outcomeTimer.current) clearTimeout(outcomeTimer.current)
      // Call parent so the Prediction Accuracy card refreshes immediately
      onOutcomeRecorded?.()
    } catch (err) {
      setOutcomeError(err instanceof Error ? err.message : "Failed to record outcome")
    } finally {
      setOutcomeLoading(false)
    }
  }

  // Fetch reasoning whenever the modal opens for a new client-property pair
  useEffect(() => {
    if (!open || !client) return

    // If we already have the text cached in state for this exact pair, skip fetch
    const currentKey = `${client.clientId}:${client.bestMatch.propertyId}`
    if (reasoning && (window as unknown as Record<string, string>)[`_reasonKey`] === currentKey) return

    setReasoning(null)
    setReasoningLoading(true)
    setReasoningError(null)
    ;(window as unknown as Record<string, string>)[`_reasonKey`] = currentKey

    fetchReasoning(client.clientId, client.bestMatch.propertyId)
      .then((text) => {
        setReasoning(text)
        setReasoningLoading(false)
      })
      .catch((err: Error) => {
        setReasoningError(err.message ?? "Analysis generation failed")
        setReasoningLoading(false)
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, client?.clientId, client?.bestMatch.propertyId])

  // Close on Escape
  useEffect(() => {
    if (!open) return
    function onKey(e: KeyboardEvent) { if (e.key === "Escape") onClose() }
    document.addEventListener("keydown", onKey)
    return () => document.removeEventListener("keydown", onKey)
  }, [open, onClose])

  // Lock body scroll
  useEffect(() => {
    if (open) {
      document.body.style.overflow = "hidden"
    } else {
      document.body.style.overflow = ""
    }
    return () => { document.body.style.overflow = "" }
  }, [open])

  if (!open || !client) return null

  // Use local overrides if available (post-viewing log), otherwise use client data
  const effectivePastViewings  = localPastViewings  ?? client.pastViewings
  const effectiveProbability   = localProbability   ?? client.bestMatch.probability
  const effectiveExpectedValue = localExpectedValue ?? client.bestMatch.expectedValue
  const effectiveTier          = localTier          ?? client.tier

  // Rebuild score rows with live pastViewings so bars animate in place
  const effectiveClient: DeduplicatedClient = localPastViewings !== null
    ? { ...client, pastViewings: localPastViewings, tier: effectiveTier,
        bestMatch: { ...client.bestMatch, probability: effectiveProbability, expectedValue: effectiveExpectedValue } }
    : client

  const scoreRows  = buildScoreRows(effectiveClient)
  const totalProb  = Math.round(effectiveProbability * 100)
  const otherProps = client.allMatches.slice(1) // everything after the best match
  const highestLikelihoodMatch = client.allMatches && client.allMatches.length > 0
    ? [...client.allMatches].sort((a, b) => b.probability - a.probability)[0]
    : null

  // Effective outcome: local state wins, then the server-supplied value
  const effectiveOutcome = outcomeResult ?? client.bestMatch.outcome

  return (
    /* Backdrop */
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 lg:p-10"
      style={{ backgroundColor: "rgba(0,0,0,0.75)" }}
      onClick={onClose}
    >
      {/* Modal panel — stop click from closing when inside */}
      <div
        className="relative flex max-h-[90vh] w-full max-w-5xl flex-col overflow-hidden border border-neutral-200 bg-white shadow-[0px_8px_32px_rgba(0,0,0,0.14)]"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={`Client Detail — ${client.name}`}
      >
        {/* ── Header ── */}
        <div className="flex shrink-0 items-start justify-between gap-4 border-b border-neutral-200 bg-black p-5 sm:p-6">
          <div className="flex items-center gap-4">
            <div className="flex h-16 w-16 shrink-0 items-center justify-center border-4 border-primary bg-primary text-2xl font-black text-black">
              {client.initials}
            </div>
            <div>
              <div className="text-xl font-black leading-tight text-white sm:text-2xl">{client.name}</div>
              <div className="mt-1 font-mono text-[11px] text-white/60">{client.bestMatch.neighborhood}</div>
              <div className="mt-2 flex items-center gap-2">
                <TierBadge tier={effectiveTier} />
                {effectiveOutcome === "won" && (
                  <span className="inline-flex items-center gap-1 border-2 border-primary bg-primary px-2.5 py-1 text-[10px] font-black uppercase tracking-wider text-black">
                    <Trophy className="h-3 w-3" strokeWidth={2.5} />
                    Won
                  </span>
                )}
                {effectiveOutcome === "lost" && (
                  <span className="inline-flex items-center gap-1 border-2 border-white/40 bg-white/10 px-2.5 py-1 text-[10px] font-black uppercase tracking-wider text-white">
                    <ThumbsDown className="h-3 w-3" strokeWidth={2.5} />
                    Lost
                  </span>
                )}
              </div>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="shrink-0 border-2 border-white/40 p-2 text-white transition-colors hover:border-white hover:bg-white hover:text-black"
            aria-label="Close"
          >
            <X className="h-5 w-5" strokeWidth={2.5} />
          </button>
        </div>

        {/* ── Scrollable body — two-column on lg ── */}
        <div className="overflow-y-auto">
          <div className="grid grid-cols-1 gap-0 lg:grid-cols-2">
            {/* ── Left column ── */}
            <div className="flex flex-col gap-6 border-b border-neutral-200 p-5 lg:border-b-0 lg:border-r-4 sm:p-6">
              {/* Financial overview */}
              <div>
                <SectionHeading>
                  <Wallet className="inline h-3 w-3 mr-1" strokeWidth={2.5} />
                  Financial &amp; Preference Overview
                </SectionHeading>
                <div className="mt-3 border border-neutral-200 shadow-[0px_2px_8px_rgba(0,0,0,0.08)]">
                  <div className="px-4">
                    <StatRow label="Highest Value Match"  value={client.bestMatch.property} />
                    <StatRow label="Property Value"       value={currency(client.bestMatch.propertyValue)} />
                    <StatRow label="Pref. Neighbourhood"  value={client.bestMatch.neighborhood} />
                    <StatRow label="E(x) on Highest Value Match" value={currency(effectiveExpectedValue)} />
                    <StatRow label="Past Viewings"        value={String(effectivePastViewings)} />
                    <StatRow label="Total Listings"       value={String(client.allMatches.length)} />
                  </div>
                  {highestLikelihoodMatch && (
                    <div className="border-t-2 border-black bg-secondary px-4 py-2.5 text-xs font-bold">
                      <span className="text-[10px] font-black uppercase tracking-wider text-muted-foreground">
                        Highest Likelihood:
                      </span>{" "}
                      <span className="font-mono font-black text-black">{highestLikelihoodMatch.property}</span>
                      {" — "}
                      <span className="font-mono font-black text-black">{percent(highestLikelihoodMatch.probability)}</span>
                    </div>
                  )}
                </div>
              </div>

              {/* AI score decomposition — UNCHANGED */}
              <div>
                <SectionHeading>
                  <Brain className="inline h-3 w-3 mr-1" strokeWidth={2.5} />
                  AI Score Decomposition
                </SectionHeading>
                <div className="mt-3 border border-neutral-200 p-4 shadow-[0px_2px_8px_rgba(0,0,0,0.08)]">
                  <div className="flex flex-col gap-4">
                    {scoreRows.map((row) => <ScoreBar key={row.label} row={row} />)}
                  </div>
                  <div className="mt-5 border-t border-neutral-200 pt-4">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-black uppercase tracking-wider">Total P(Buy)</span>
                      <span className="font-mono text-2xl font-black transition-all duration-300">{percent(effectiveProbability)}</span>
                    </div>
                    <div className="mt-2 h-5 w-full border border-neutral-200 bg-white">
                      <div className="h-full bg-black transition-all duration-500" style={{ width: `${totalProb}%` }} />
                    </div>
                    <div className="mt-1 flex justify-between text-[10px] font-bold text-muted-foreground">
                      <span>0%</span>
                      <span className="font-black text-primary">VIP ≥ 65%</span>
                      <span>100%</span>
                    </div>
                    {localPastViewings !== null && (
                      <div className="mt-2 font-mono text-[10px] font-black uppercase tracking-wider text-muted-foreground">
                        {effectivePastViewings} past viewing{effectivePastViewings !== 1 ? "s" : ""} recorded
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>

            {/* ── Right column ── */}
            <div className="flex flex-col gap-6 p-5 sm:p-6">
              {/* AI reasoning — LIVE GENERATED */}
              <div>
                <SectionHeading>
                  <Sparkles className="inline h-3 w-3 mr-1" strokeWidth={2.5} />
                  AI Reasoning Breakdown
                </SectionHeading>
                <ReasoningBox
                  loading={reasoningLoading}
                  error={reasoningError}
                  text={reasoning}
                />
              </div>

              {/* Other property matches */}
              {otherProps.length > 0 && (
                <div>
                  <SectionHeading>
                    <Layers className="inline h-3 w-3 mr-1" strokeWidth={2.5} />
                    Other Listing Matches ({otherProps.length})
                  </SectionHeading>
                  <div className="mt-3 border border-neutral-200 shadow-[0px_2px_8px_rgba(0,0,0,0.08)]">
                    <div className="flex items-center gap-3 border-b border-neutral-200 bg-black px-4 py-2">
                      <span className="flex-1 text-[10px] font-black uppercase tracking-wider text-white">Property</span>
                      <span className="text-[10px] font-black uppercase tracking-wider text-white">P / E(x)</span>
                    </div>
                    {otherProps.map((m, i) => (
                      <OtherMatchRow key={m.id} match={m} rank={i + 2} />
                    ))}
                  </div>
                </div>
              )}

              {/* Best listing snapshot (when no other matches take up space) */}
              {otherProps.length === 0 && (
                <div>
                  <SectionHeading>
                    <Building2 className="inline h-3 w-3 mr-1" strokeWidth={2.5} />
                    Target Listing Snapshot
                  </SectionHeading>
                  <div className="mt-3 border border-neutral-200 p-4 shadow-[0px_2px_8px_rgba(0,0,0,0.08)]">
                    <div className="flex items-center gap-3">
                      <div className="flex h-12 w-12 shrink-0 items-center justify-center border border-neutral-200 bg-black">
                        <Building2 className="h-5 w-5 text-primary" strokeWidth={2.5} />
                      </div>
                      <div>
                        <div className="text-sm font-black leading-tight">{client.bestMatch.property}</div>
                        <div className="flex items-center gap-1 mt-1 text-xs font-bold text-muted-foreground">
                          <MapPin className="h-3 w-3" strokeWidth={2.5} />
                          {client.bestMatch.neighborhood}
                        </div>
                      </div>
                      <div className="ml-auto text-right">
                        <div className="text-[10px] font-black uppercase tracking-wider text-muted-foreground">Value</div>
                        <div className="font-mono text-base font-black">{currency(client.bestMatch.propertyValue)}</div>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* ── Footer ── */}
        <div className="shrink-0 border-t border-neutral-200 bg-card">

          {/* Log Viewing confirmation banner */}
          {viewingResult && (
            <div className="flex items-center gap-3 border-b border-neutral-200 bg-primary px-5 py-3">
              <CheckCircle2 className="h-5 w-5 shrink-0 text-black" strokeWidth={2.5} />
              <p className="flex-1 text-sm font-black text-black">
                Viewing logged.{" "}
                <span className="font-mono">{viewingResult.clientName}&apos;s</span> P(Buy) updated to{" "}
                <span className="font-mono">{Math.round(viewingResult.probability * 100)}%</span>
                {" — "}{viewingResult.tier.replace("_", " ")}
              </p>
              <button
                type="button"
                onClick={() => setViewingResult(null)}
                className="shrink-0 border border-neutral-200 p-1 text-black hover:bg-black hover:text-primary"
                aria-label="Dismiss log confirmation"
              >
                <X className="h-3.5 w-3.5" strokeWidth={2.5} />
              </button>
            </div>
          )}
          {viewingError && (
            <div className="border-b border-neutral-200 bg-white px-5 py-3">
              <span className="text-xs font-black uppercase tracking-wider text-red-600">Error: {viewingError}</span>
            </div>
          )}

          {/* Outcome confirmation banner */}
          {outcomeResult && (
            <div className={`flex items-center gap-3 border-b border-neutral-200 px-5 py-3 ${
              outcomeResult === "won" ? "bg-primary" : "bg-white"
            }`}>
              {outcomeResult === "won" ? (
                <Trophy className="h-5 w-5 shrink-0 text-black" strokeWidth={2.5} />
              ) : (
                <ThumbsDown className="h-5 w-5 shrink-0 text-black" strokeWidth={2.5} />
              )}
              <p className="flex-1 text-sm font-black text-black">
                {client?.name} marked as <span className="uppercase">{outcomeResult}</span>.
                {" "}Outcome recorded for prediction accuracy tracking.
              </p>
              <button
                type="button"
                onClick={() => setOutcomeResult(null)}
                className="shrink-0 border border-neutral-200 p-1 text-black hover:bg-black hover:text-primary"
                aria-label="Dismiss outcome confirmation"
              >
                <X className="h-3.5 w-3.5" strokeWidth={2.5} />
              </button>
            </div>
          )}
          {outcomeError && (
            <div className="border-b border-neutral-200 bg-white px-5 py-3">
              <span className="text-xs font-black uppercase tracking-wider text-red-600">Error: {outcomeError}</span>
            </div>
          )}

          {/* Schedule Viewing confirmation banner */}
          {schedSuccess && (
            <div className="flex items-center gap-3 border-b border-neutral-200 bg-black px-5 py-3">
              <Calendar className="h-5 w-5 shrink-0 text-primary" strokeWidth={2.5} />
              <p className="flex-1 text-sm font-black text-white">{schedSuccess}</p>
              <button
                type="button"
                onClick={() => setSchedSuccess(null)}
                className="shrink-0 border-2 border-white/40 p-1 text-white hover:border-white hover:bg-white hover:text-black"
                aria-label="Dismiss schedule confirmation"
              >
                <X className="h-3.5 w-3.5" strokeWidth={2.5} />
              </button>
            </div>
          )}
          {schedError && (
            <div className="border-b border-neutral-200 bg-white px-5 py-3">
              <span className="text-xs font-black uppercase tracking-wider text-red-600">Error: {schedError}</span>
            </div>
          )}

          {/* Schedule Viewing inline date+time form */}
          {schedFormOpen && (
            <form
              onSubmit={handleScheduleViewingSubmit}
              className="border-b border-neutral-200 bg-white px-5 py-4"
            >
              <div className="mb-3 text-[10px] font-black uppercase tracking-widest text-muted-foreground">
                Set viewing date &amp; time
              </div>
              <div className="flex flex-col gap-3 sm:flex-row">
                <div className="flex flex-1 flex-col gap-1">
                  <label htmlFor="sched-date" className="text-[10px] font-black uppercase tracking-wider">Date</label>
                  <input
                    id="sched-date"
                    type="date"
                    required
                    value={schedDate}
                    onChange={(e) => setSchedDate(e.target.value)}
                    min={new Date().toISOString().split("T")[0]}
                    className="border border-neutral-200 bg-white px-3 py-2 font-mono text-sm font-bold outline-none focus:border-black focus:ring-2 focus:ring-primary"
                  />
                </div>
                <div className="flex flex-1 flex-col gap-1">
                  <label htmlFor="sched-time" className="text-[10px] font-black uppercase tracking-wider">Time</label>
                  <input
                    id="sched-time"
                    type="time"
                    required
                    value={schedTime}
                    onChange={(e) => setSchedTime(e.target.value)}
                    className="border border-neutral-200 bg-white px-3 py-2 font-mono text-sm font-bold outline-none focus:border-black focus:ring-2 focus:ring-primary"
                  />
                </div>
                <div className="flex items-end gap-2">
                  <button
                    type="submit"
                    disabled={schedLoading || !schedDate || !schedTime}
                    className="flex items-center gap-2 border border-neutral-200 bg-black px-4 py-2 text-xs font-black uppercase tracking-wider text-white shadow-[0px_1px_4px_rgba(0,0,0,0.07)] transition-all hover:shadow-[0px_2px_8px_rgba(0,0,0,0.08)] disabled:opacity-50"
                  >
                    {schedLoading ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={2.5} />
                    ) : (
                      <CalendarCheck className="h-3.5 w-3.5 text-primary" strokeWidth={2.5} />
                    )}
                    Confirm
                  </button>
                  <button
                    type="button"
                    onClick={() => { setSchedFormOpen(false); setSchedError(null) }}
                    className="border border-neutral-200 bg-white px-4 py-2 text-xs font-black uppercase tracking-wider text-black shadow-[0px_1px_4px_rgba(0,0,0,0.07)] transition-all"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            </form>
          )}

          {/* Action buttons row */}
          <div className="flex flex-col gap-3 p-5 sm:flex-row sm:p-6">
            {effectiveTier === "TIER_1" || effectiveTier === "TIER_2" ? (
              <button
                type="button"
                onClick={() => {
                  if (onGenerateInvite) onGenerateInvite(client)
                }}
                className="flex flex-1 items-center justify-center gap-2 border border-neutral-200 bg-black py-3.5 text-sm font-black uppercase tracking-wider text-white shadow-[0px_2px_8px_rgba(0,0,0,0.08)] transition-all hover:shadow-[0px_1px_3px_rgba(0,0,0,0.06)]"
              >
                <Send className="h-4 w-4 text-primary" strokeWidth={2.5} />
                Generate Invite
              </button>
            ) : (
              <button
                type="button"
                disabled
                className="flex flex-1 cursor-not-allowed items-center justify-center gap-2 border border-neutral-200/40 bg-muted py-3.5 text-sm font-black uppercase tracking-wider text-muted-foreground"
              >
                <Send className="h-4 w-4 text-muted-foreground" strokeWidth={2.5} />
                Generate Invite (VIP/Warm Only)
              </button>
            )}

            {/* Schedule Viewing — opens the inline form */}
            <button
              type="button"
              onClick={() => { setSchedFormOpen((o) => !o); setSchedError(null) }}
              className={`flex flex-1 items-center justify-center gap-2 border border-neutral-200 py-3.5 text-sm font-black uppercase tracking-wider shadow-[0px_2px_8px_rgba(0,0,0,0.08)] transition-all hover:shadow-[0px_1px_3px_rgba(0,0,0,0.06)] ${
                schedFormOpen ? "bg-black text-white" : "bg-white text-black"
              }`}
            >
              <Calendar className="h-4 w-4" strokeWidth={2.5} />
              Schedule Viewing
            </button>

            {/* Log Viewing — records a past/completed viewing */}
            <button
              type="button"
              onClick={handleLogViewing}
              disabled={viewingLoading}
              className="flex flex-1 items-center justify-center gap-2 border border-neutral-200 bg-white py-3.5 text-sm font-black uppercase tracking-wider text-black shadow-[0px_2px_8px_rgba(0,0,0,0.08)] transition-all hover:shadow-[0px_1px_3px_rgba(0,0,0,0.06)] disabled:cursor-not-allowed disabled:opacity-60"
            >
              {viewingLoading ? (
                <Loader2 className="h-4 w-4 animate-spin" strokeWidth={2.5} />
              ) : (
                <CalendarCheck className="h-4 w-4" strokeWidth={2.5} />
              )}
              {viewingLoading ? "Logging…" : "Log Viewing"}
            </button>
          </div>

          {/* Won / Lost outcome row */}
          <div className="flex gap-3 border-t-2 border-black/20 px-5 pb-5 pt-3 sm:px-6">
            {effectiveOutcome === "pending" ? (
              <>
                <button
                  type="button"
                  disabled={outcomeLoading}
                  onClick={() => handleRecordOutcome("won")}
                  className="flex flex-1 items-center justify-center gap-2 border border-neutral-200 bg-primary py-3 text-sm font-black uppercase tracking-wider text-black shadow-[0px_2px_8px_rgba(0,0,0,0.08)] transition-all hover:shadow-[0px_1px_3px_rgba(0,0,0,0.06)] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {outcomeLoading ? (
                    <Loader2 className="h-4 w-4 animate-spin" strokeWidth={2.5} />
                  ) : (
                    <ThumbsUp className="h-4 w-4" strokeWidth={2.5} />
                  )}
                  Mark as Won
                </button>
                <button
                  type="button"
                  disabled={outcomeLoading}
                  onClick={() => handleRecordOutcome("lost")}
                  className="flex flex-1 items-center justify-center gap-2 border border-neutral-200 bg-white py-3 text-sm font-black uppercase tracking-wider text-black shadow-[0px_2px_8px_rgba(0,0,0,0.08)] transition-all hover:shadow-[0px_1px_3px_rgba(0,0,0,0.06)] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {outcomeLoading ? (
                    <Loader2 className="h-4 w-4 animate-spin" strokeWidth={2.5} />
                  ) : (
                    <ThumbsDown className="h-4 w-4" strokeWidth={2.5} />
                  )}
                  Mark as Lost
                </button>
              </>
            ) : (
              <>
                {/* Already decided — show a compact change option */}
                <div className={`flex flex-1 items-center gap-3 border border-neutral-200 px-4 py-3 ${
                  effectiveOutcome === "won" ? "bg-primary" : "bg-white"
                }`}>
                  {effectiveOutcome === "won" ? (
                    <Trophy className="h-5 w-5 shrink-0 text-black" strokeWidth={2.5} />
                  ) : (
                    <ThumbsDown className="h-5 w-5 shrink-0 text-black" strokeWidth={2.5} />
                  )}
                  <div className="flex-1">
                    <div className="text-xs font-black uppercase tracking-wider text-black">
                      Outcome recorded: {effectiveOutcome?.toUpperCase()}
                    </div>
                    <div className="text-[10px] font-bold text-black/70">Tracked in Prediction Accuracy</div>
                  </div>
                </div>
                <button
                  type="button"
                  disabled={outcomeLoading}
                  onClick={() => handleRecordOutcome(effectiveOutcome === "won" ? "lost" : "won")}
                  className="flex shrink-0 items-center justify-center gap-2 border border-neutral-200 bg-white px-4 py-3 text-xs font-black uppercase tracking-wider text-black shadow-[0px_1px_4px_rgba(0,0,0,0.07)] transition-all hover:shadow-[0px_1px_3px_rgba(0,0,0,0.06)] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Change to {effectiveOutcome === "won" ? "Lost" : "Won"}
                </button>
              </>
            )}
          </div>
        </div>

      </div>
    </div>
  )
}
