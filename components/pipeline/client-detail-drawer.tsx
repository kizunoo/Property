"use client"

import { useEffect, useRef, useState } from "react"
import {
  Brain,
  Building2,
  Calendar,
  CalendarCheck,
  CheckCircle2,
  Eye,
  History,
  Layers,
  Loader2,
  MapPin,
  Plus,
  Send,
  ShieldCheck,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  Trophy,
  Wallet,
  X,
} from "lucide-react"
import { TIER_SHORT, currency, percent, type DeduplicatedClient, type PastPurchase } from "@/lib/pipeline-data"
import { priceLabel, evLabel } from "@/lib/price"
import { fetchReasoning } from "@/lib/generate-reasoning"
import { logViewing, type ViewingResult } from "@/lib/log-viewing"
import { scheduleViewing } from "@/lib/schedule-viewing"
import { StageBadge } from "@/components/pipeline/stage-badge"
import { PortalAccessPanel } from "@/components/pipeline/portal-access-panel"
import { CompanyInquiryHistory } from "@/components/pipeline/inquiry-detail-modal"

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
  if (budget != null && budget > 0 && propVal != null && propVal > 0) {
    if (budget >= propVal) {
      const ratio = propVal / budget
      finFactor = 0.5 + 0.5 * Math.min(1.0, ratio)
    } else {
      const ratio = budget / propVal
      finFactor = 0.5 * Math.max(0.0, ratio)
    }
  }
  const finPts = Math.round(40 * finFactor)

  // 3. Geo Match (primary): +30% if preferred neighborhood matches, else 0%
  const geoPts = (prefNbhd && prefNbhd === propNbhd) ? 30 : 0

  // 4. Engagement Bonus: +10% per past viewing, capped at +20%
  const engagementPts = Math.min((viewings || 0) * 10, 20)

  // ── Rich profile bonuses (additive, all optional) ─────────────────────────

  // 5. Financing bonus: +5% if cash or pre-approved
  const fin = client.financingStatus
  const financingPts = (fin === "cash" || fin === "pre-approved") ? 5 : 0

  // 6. Timeline urgency: +5% if moving within 6 months
  const tl = client.moveInTimeline
  const timelinePts = (tl === "< 3 months" || tl === "3-6 months") ? 5 : 0

  // 7. Secondary geo: +10% if secondary neighborhood matches (only when primary didn't fire)
  const secNbhd = client.secondaryNeighborhood
  const secGeoPts = (secNbhd && secNbhd === propNbhd && geoPts === 0) ? 10 : 0

  // 8. Past acquisition track record bonuses
  const purchases = client.pastPurchases ?? []
  const trackRecordPts = purchases.length > 0 ? 5 : 0
  const repeatAreaPts = (propNbhd && purchases.some((p) => p.neighborhood === propNbhd)) ? 5 : 0

  const rows: ScoreRow[] = [
    { label: "Base Probability", points: basePts,       max: 10, earned: basePts > 0 },
    { label: "Financial Fit",    points: finPts,        max: 40, earned: finPts > 0 },
    { label: "Geo Match",        points: geoPts,        max: 30, earned: geoPts > 0 },
    { label: "Engagement Bonus", points: engagementPts, max: 20, earned: engagementPts > 0 },
  ]

  // Only show rich-profile rows when the data exists
  if (fin)      rows.push({ label: "Financing Bonus",   points: financingPts, max: 5,  earned: financingPts > 0 })
  if (tl)       rows.push({ label: "Urgency Bonus",     points: timelinePts,  max: 5,  earned: timelinePts > 0 })
  if (secNbhd)  rows.push({ label: "Secondary Geo",     points: secGeoPts,    max: 10, earned: secGeoPts > 0 })
  if (purchases.length > 0) {
    rows.push({ label: "Track Record", points: trackRecordPts, max: 5, earned: trackRecordPts > 0 })
    if (repeatAreaPts > 0) {
      rows.push({ label: "Repeat Area Owner", points: repeatAreaPts, max: 5, earned: repeatAreaPts > 0 })
    }
  }

  return rows
}

// ─── Sub-components ───────────────────────────────────────────────────────────
function TierBadge({ tier }: { tier: DeduplicatedClient["tier"] }) {
  const styles: Record<DeduplicatedClient["tier"], string> = {
    TIER_1: "bg-primary text-black border-primary",
    TIER_2: "bg-black text-white border-black",
    TIER_3: "bg-muted text-foreground border-border",
  }
  return (
    <span className={`inline-block rounded-[6px] border px-2.5 py-1 text-xs font-bold uppercase tracking-wider ${styles[tier]}`}>
      {TIER_SHORT[tier]}
    </span>
  )
}

function ScoreBar({ row }: { row: ScoreRow }) {
  const pct = row.max > 0 ? (row.points / row.max) * 100 : 0
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">{row.label}</span>
        <span className={`font-mono text-xs font-bold ${row.earned ? "text-foreground" : "text-muted-foreground"}`}>
          {row.earned ? `+${row.points}%` : "—"}
          <span className="font-semibold text-muted-foreground"> / {row.max}%</span>
        </span>
      </div>
      <div className="h-2.5 w-full rounded-[4px] border border-border bg-muted overflow-hidden">
        <div
          className={`h-full rounded-[4px] transition-all duration-300 ${row.earned ? "bg-black" : "bg-transparent"}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2 border-b border-border pb-2">
      <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">{children}</span>
    </div>
  )
}

function StatRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between border-b border-border/60 py-2.5 last:border-0">
      <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{label}</span>
      <span className="font-mono text-sm font-bold text-foreground">{value}</span>
    </div>
  )
}

// ─── Match list (other properties) ───────────────────────────────────────────
function OtherMatchRow({ match, rank }: { match: DeduplicatedClient["allMatches"][0]; rank: number }) {
  return (
    <div className="flex items-center gap-3 border-b border-border px-4 py-3 last:border-b-0 hover:bg-muted/30 transition-colors">
      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-[6px] bg-muted font-mono text-[10px] font-bold text-foreground">
        {rank}
      </span>
      <div className="flex-1 overflow-hidden">
        <div className="flex items-center gap-1 text-sm font-bold text-foreground">
          <MapPin className="h-3 w-3 shrink-0 text-muted-foreground" strokeWidth={2} />
          <span className="truncate">{match.property}</span>
        </div>
        <div className="font-mono text-[10px] text-muted-foreground">{match.agent}</div>
      </div>
      <div className="text-right">
        <div className="font-mono text-xs font-bold text-foreground">{percent(match.probability)}</div>
        <div className="font-mono text-xs text-muted-foreground">{evLabel(match.expectedValue, currency)}</div>
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
      <div className="mt-3 rounded-[10px] border border-border bg-muted/20 p-4 shadow-[var(--shadow-xs)]">
        <div className="flex items-center gap-2">
          <Loader2 className="h-4 w-4 shrink-0 animate-spin text-foreground" strokeWidth={2.5} />
          <span className="font-mono text-xs font-semibold uppercase tracking-widest text-muted-foreground">
            Generating analysis…
          </span>
        </div>
        {/* Skeleton lines */}
        <div className="mt-3 flex flex-col gap-2">
          <div className="h-3 w-full animate-pulse bg-muted rounded" />
          <div className="h-3 w-[90%] animate-pulse bg-muted rounded" />
          <div className="h-3 w-[75%] animate-pulse bg-muted rounded" />
          <div className="h-3 w-[85%] animate-pulse bg-muted rounded" />
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="mt-3 rounded-[10px] border border-border bg-card p-4 shadow-[var(--shadow-xs)]">
        <div className="flex gap-2">
          <Brain className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" strokeWidth={2} />
          <div>
            <p className="text-sm font-semibold leading-relaxed text-muted-foreground">
              {error}
            </p>
            <p className="mt-1 text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
              Close and reopen to retry
            </p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="mt-3 rounded-[10px] border border-border border-l-4 border-l-primary bg-primary/10 p-4 shadow-[var(--shadow-xs)]">
      <div className="flex gap-2.5">
        <Brain className="mt-0.5 h-4 w-4 shrink-0 text-foreground" strokeWidth={2} />
        <p className="text-sm font-medium leading-relaxed text-foreground">{text}</p>
      </div>
    </div>
  )
}

// ─── Buyer notes field ────────────────────────────────────────────────────────
function BuyerNotesField({ clientId, initialNotes }: { clientId: string; initialNotes: string }) {
  const [notes, setNotes]   = useState(initialNotes)
  const [saving, setSaving] = useState(false)
  const [saved,  setSaved]  = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const save = async (value: string) => {
    setSaving(true)
    setSaved(false)
    try {
      await fetch(`/api/clients/${clientId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ agent_notes: value }),
      })
      setSaved(true)
      timerRef.current = setTimeout(() => setSaved(false), 2500)
    } catch {
      // silent
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="relative">
      <textarea
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        onBlur={(e) => save(e.target.value)}
        placeholder="Add notes about this client (saved on blur)…"
        rows={3}
        className="w-full resize-none rounded-[6px] border border-border bg-muted/30 px-3 py-2 text-xs font-medium text-foreground placeholder:text-muted-foreground outline-none focus:ring-1 focus:ring-foreground transition-all"
      />
      {(saving || saved) && (
        <span className={`absolute bottom-2 right-2 text-[9px] font-bold uppercase tracking-wide ${saved ? "text-emerald-600" : "text-muted-foreground"}`}>
          {saving ? "Saving…" : "Saved ✓"}
        </span>
      )}
    </div>
  )
}

// ─── Acquisition track record component ───────────────────────────────────────
function AcquisitionTrackRecord({
  clientId,
  initialPurchases,
  onPurchasesUpdated,
}: {
  clientId: string
  initialPurchases: PastPurchase[]
  onPurchasesUpdated: (purchases: PastPurchase[]) => void
}) {
  const [purchases, setPurchases] = useState<PastPurchase[]>(initialPurchases)
  const [isAdding, setIsAdding]   = useState(false)
  const [loading, setLoading]     = useState(false)

  // Form state
  const [propertyName, setPropertyName]   = useState("")
  const [neighborhood, setNeighborhood]   = useState("")
  const [propertyType, setPropertyType]   = useState("condo")
  const [purchasePrice, setPurchasePrice] = useState("")
  const [purchaseYear, setPurchaseYear]   = useState(String(new Date().getFullYear() - 2))
  const [purpose, setPurpose]             = useState("own_stay")

  useEffect(() => {
    setPurchases(initialPurchases)
  }, [initialPurchases])

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault()
    const priceNum = Number(purchasePrice.replace(/[^0-9.]/g, ""))
    if (!propertyName || !neighborhood || !priceNum) return

    setLoading(true)
    try {
      const res = await fetch(`/api/clients/${clientId}/purchases`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          property_name: propertyName,
          neighborhood,
          property_type: propertyType,
          purchase_price: priceNum,
          purchase_year: purchaseYear ? Number(purchaseYear) : null,
          purpose,
        }),
      })
      if (res.ok) {
        const json = await res.json()
        const newRecord: PastPurchase = {
          id: json.purchase?.id || String(Date.now()),
          clientId,
          propertyName,
          neighborhood,
          propertyType,
          purchasePrice: priceNum,
          purchaseYear: purchaseYear ? Number(purchaseYear) : null,
          purpose,
        }
        const updated = [newRecord, ...purchases]
        setPurchases(updated)
        onPurchasesUpdated(updated)
        setIsAdding(false)
        setPropertyName("")
        setNeighborhood("")
        setPurchasePrice("")
      }
    } catch {
      // silent
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <SectionHeading>
        <History className="inline h-3 w-3 mr-1 text-muted-foreground" strokeWidth={2.5} />
        Acquisition Track Record ({purchases.length})
      </SectionHeading>
      <div className="mt-3 rounded-[8px] border border-border bg-card shadow-[var(--shadow-xs)] overflow-hidden">
        <div className="flex items-center justify-between border-b border-border bg-muted/20 px-4 py-2.5">
          <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
            Previous Properties Owned
          </div>
          {!isAdding && (
            <button
              type="button"
              onClick={() => setIsAdding(true)}
              className="flex items-center gap-1 text-[10px] font-bold text-foreground hover:text-primary transition-colors uppercase tracking-wider"
            >
              <Plus className="h-3 w-3" />
              Add Property
            </button>
          )}
        </div>

        {isAdding && (
          <form onSubmit={handleAdd} className="border-b border-border bg-muted/40 p-4 flex flex-col gap-2.5">
            <div className="text-[10px] font-bold uppercase tracking-wide text-foreground">Log Previous Acquisition</div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <input
                type="text"
                placeholder="Property Name (e.g. The Troika)"
                value={propertyName}
                onChange={(e) => setPropertyName(e.target.value)}
                required
                className="rounded-[4px] border border-border bg-card px-2.5 py-1.5 text-xs text-foreground placeholder:text-muted-foreground outline-none focus:ring-1 focus:ring-foreground"
              />
              <input
                type="text"
                placeholder="Neighborhood (e.g. KLCC)"
                value={neighborhood}
                onChange={(e) => setNeighborhood(e.target.value)}
                required
                className="rounded-[4px] border border-border bg-card px-2.5 py-1.5 text-xs text-foreground placeholder:text-muted-foreground outline-none focus:ring-1 focus:ring-foreground"
              />
              <input
                type="text"
                placeholder="Price (RM, e.g. 2,800,000)"
                value={purchasePrice}
                onChange={(e) => setPurchasePrice(e.target.value)}
                required
                className="rounded-[4px] border border-border bg-card px-2.5 py-1.5 text-xs text-foreground placeholder:text-muted-foreground outline-none focus:ring-1 focus:ring-foreground"
              />
              <div className="flex gap-2">
                <select
                  value={propertyType}
                  onChange={(e) => setPropertyType(e.target.value)}
                  className="flex-1 rounded-[4px] border border-border bg-card px-2 py-1.5 text-xs text-foreground outline-none focus:ring-1 focus:ring-foreground"
                >
                  <option value="condo">Condo</option>
                  <option value="semi-d">Semi-D</option>
                  <option value="bungalow">Bungalow</option>
                  <option value="terrace">Terrace</option>
                  <option value="serviced_apt">Serviced Apt</option>
                </select>
                <input
                  type="number"
                  placeholder="Year"
                  value={purchaseYear}
                  onChange={(e) => setPurchaseYear(e.target.value)}
                  className="w-20 rounded-[4px] border border-border bg-card px-2 py-1.5 text-xs text-foreground outline-none focus:ring-1 focus:ring-foreground"
                />
              </div>
            </div>
            <div className="flex items-center justify-between mt-1">
              <div className="flex items-center gap-2">
                <label className="text-[10px] font-bold uppercase text-muted-foreground">Purpose:</label>
                <select
                  value={purpose}
                  onChange={(e) => setPurpose(e.target.value)}
                  className="rounded-[4px] border border-border bg-card px-2 py-1 text-xs text-foreground outline-none"
                >
                  <option value="own_stay">Own Stay</option>
                  <option value="investment">Investment</option>
                  <option value="holiday_home">Holiday Home</option>
                </select>
              </div>
              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => setIsAdding(false)}
                  className="rounded-[4px] border border-border px-2.5 py-1 text-[10px] font-bold uppercase text-muted-foreground hover:bg-muted"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={loading}
                  className="rounded-[4px] bg-black text-white px-3 py-1 text-[10px] font-bold uppercase disabled:opacity-50"
                >
                  {loading ? "Saving…" : "Save"}
                </button>
              </div>
            </div>
          </form>
        )}

        <div className="divide-y divide-border">
          {purchases.length === 0 ? (
            <div className="p-4 text-center text-xs text-muted-foreground italic">
              No previous property purchases recorded for this client.
            </div>
          ) : (
            purchases.map((p) => (
              <div key={p.id} className="p-3 hover:bg-muted/10 transition-colors flex items-start justify-between gap-3">
                <div className="flex items-start gap-2.5">
                  {p.imageUrl ? (
                    <div className="h-10 w-12 rounded-[4px] border border-border bg-muted overflow-hidden shrink-0 mt-0.5">
                      <img src={p.imageUrl} alt={p.propertyName} className="h-full w-full object-cover" />
                    </div>
                  ) : (
                    <div className="flex h-10 w-10 items-center justify-center rounded-[4px] border border-border bg-muted shrink-0 mt-0.5">
                      <Building2 className="h-4 w-4 text-muted-foreground" />
                    </div>
                  )}
                  <div>
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className="text-xs font-bold text-foreground">{p.propertyName}</span>
                      {p.purchaseYear && <span className="text-[10px] font-mono text-muted-foreground">({p.purchaseYear})</span>}
                      {p.propertyId && (
                        <span className="rounded bg-amber-100 border border-amber-300/80 px-1.5 py-0.2 text-[8px] font-black uppercase tracking-wider text-amber-900">
                          Closed Listing
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-1.5 mt-0.5 text-[10px] font-semibold text-muted-foreground">
                      <MapPin className="h-3 w-3" />
                      {p.neighborhood}
                      <span>·</span>
                      <span className="capitalize">{p.propertyType}</span>
                      {p.purpose && (
                        <>
                          <span>·</span>
                          <span className="rounded bg-muted px-1.5 py-0.2 text-[9px] font-bold uppercase tracking-wider text-muted-foreground">
                            {p.purpose.replace("_", " ")}
                          </span>
                        </>
                      )}
                    </div>
                  </div>
                </div>
                <div className="text-right shrink-0">
                  <div className="font-mono text-xs font-bold text-foreground">
                    {currency(p.purchasePrice)}
                  </div>
                  <span className="inline-block text-[8px] font-bold text-emerald-600 uppercase tracking-wider">
                    Verified
                  </span>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}

interface ClientDetailModalProps {
  client: DeduplicatedClient | null
  open: boolean
  onClose: () => void
  onGenerateInvite?: (client: DeduplicatedClient) => void
  onOutcomeRecorded?: () => void
  onStageChanged?: (newStage: string) => void
  initialScheduleViewing?: boolean
}

export function ClientDetailModal({ client, open, onClose, onGenerateInvite, onOutcomeRecorded, onStageChanged, initialScheduleViewing }: ClientDetailModalProps) {
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
  const [localPurchases, setLocalPurchases]         = useState<PastPurchase[] | null>(null)
  const [localStage, setLocalStage]                 = useState<string | null>(null)
  const [advancingStage, setAdvancingStage]         = useState(false)

  // ── Schedule Viewing (future) state ──────────────────────────────────────
  const [schedFormOpen, setSchedFormOpen]     = useState(Boolean(initialScheduleViewing))
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
      setLocalPurchases(null)
      setLocalStage(null)
      setAdvancingStage(false)
      setViewingResult(null)
      setViewingError(null)
      setOutcomeResult(null)
      setOutcomeError(null)
      setSchedFormOpen(Boolean(initialScheduleViewing))
      setSchedDate("")
      setSchedTime("")
      setSchedError(null)
      setSchedSuccess(null)
      if (confirmTimerRef.current) clearTimeout(confirmTimerRef.current)
      if (schedSuccessTimer.current) clearTimeout(schedSuccessTimer.current)
    }
  }, [client?.clientId, initialScheduleViewing])

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
      setViewingError(err instanceof Error ? err.message : "Failed to log demo")
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
      setSchedSuccess(`Demo scheduled for ${displayDate}`)
      setLocalStage("viewing")
      onStageChanged?.("viewing")
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
      const nextStage = outcome === "won" ? "closed_won" : "closed_lost"
      setLocalStage(nextStage)
      onStageChanged?.(nextStage)
      if (outcomeTimer.current) clearTimeout(outcomeTimer.current)
      // Call parent so the Prediction Accuracy card refreshes immediately
      onOutcomeRecorded?.()
    } catch (err) {
      setOutcomeError(err instanceof Error ? err.message : "Failed to record outcome")
    } finally {
      setOutcomeLoading(false)
    }
  }

  const handleMoveToNegotiation = async () => {
    if (!client || advancingStage) return
    setAdvancingStage(true)
    try {
      const res = await fetch(`/api/clients/${client.clientId}/advance_stage`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ stage: "negotiation" }),
      })
      if (res.ok) {
        setLocalStage("negotiation")
        onStageChanged?.("negotiation")
      }
    } catch {
      // silent
    } finally {
      setAdvancingStage(false)
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
  const effectivePurchases     = localPurchases     ?? (client.pastPurchases ?? [])

  // Rebuild score rows with live pastViewings & pastPurchases so bars animate in place
  const effectiveStage = localStage ?? client.relationshipStage ?? "new"
  const effectiveClient: DeduplicatedClient = {
    ...client,
    pastViewings: effectivePastViewings,
    tier: effectiveTier,
    pastPurchases: effectivePurchases,
    relationshipStage: effectiveStage,
    bestMatch: {
      ...client.bestMatch,
      probability: effectiveProbability,
      expectedValue: effectiveExpectedValue,
    },
  }

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
      style={{ backgroundColor: "rgba(0,0,0,0.65)" }}
      onClick={onClose}
    >
      {/* Modal panel — stop click from closing when inside */}
      <div
        className="relative flex max-h-[90vh] w-full max-w-5xl flex-col overflow-hidden rounded-[12px] border border-border bg-card shadow-[var(--shadow-xl)]"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={`Client Detail — ${client.name}`}
      >
        {/* ── Header ── */}
        <div className="flex shrink-0 items-start justify-between gap-4 border-b border-border bg-transparent p-5 sm:p-6">
          <div className="flex items-center gap-4">
            <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-[8px] bg-primary text-xl font-bold text-black shadow-[var(--shadow-xs)]">
              {client.initials}
            </div>
            <div>
              <div className="text-xl font-bold leading-tight text-foreground sm:text-2xl">{client.name}</div>
              <div className="mt-1 font-mono text-xs text-muted-foreground">{client.bestMatch.neighborhood}</div>
              <div className="mt-2 flex items-center gap-2 flex-wrap">
                <TierBadge tier={effectiveTier} />
                <StageBadge stage={effectiveStage} />
                {effectiveStage === "viewing" && (
                  <button
                    type="button"
                    onClick={handleMoveToNegotiation}
                    disabled={advancingStage}
                    className="inline-flex items-center gap-1 rounded-[6px] border border-black bg-white px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-black shadow-xs hover:bg-neutral-100 transition-all disabled:opacity-50"
                  >
                    {advancingStage ? "Updating…" : "Move to Negotiation →"}
                  </button>
                )}
                {effectivePurchases.length > 0 && (
                  <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-400/60 bg-gradient-to-r from-amber-500/10 via-amber-400/20 to-amber-500/10 px-2.5 py-0.5 text-[10px] font-black uppercase tracking-wider text-amber-900 shadow-sm">
                    <ShieldCheck className="h-3.5 w-3.5 text-amber-700 shrink-0" strokeWidth={2.5} />
                    <span>Proven Adopter</span>
                    <span className="text-amber-400">·</span>
                    <span>{effectivePurchases.length} {effectivePurchases.length === 1 ? "Unit" : "Units"} Deployed</span>
                  </span>
                )}
              </div>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-[var(--radius-sm)] border border-border p-2 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            aria-label="Close"
          >
            <X className="h-5 w-5" strokeWidth={2.5} />
          </button>
        </div>

        {/* ── Scrollable body — two-column on lg ── */}
        <div className="overflow-y-auto">
          <div className="grid grid-cols-1 gap-0 lg:grid-cols-2">
            {/* ── Left column ── */}
            <div className="flex flex-col gap-6 border-b border-border p-5 lg:border-b-0 lg:border-r sm:p-6">
              {/* Financial overview */}
              <div>
                <SectionHeading>
                  <Wallet className="inline h-3 w-3 mr-1 text-muted-foreground" strokeWidth={2.5} />
                  Financial &amp; Preference Overview
                </SectionHeading>
                <div className="mt-3 rounded-[8px] border border-border bg-card shadow-[var(--shadow-xs)] overflow-hidden">
                  <div className="px-4">
                    <StatRow label="Best-Fit Match"       value={client.bestMatch.property} />
                    <StatRow label="Unit Cost"            value={priceLabel(client.bestMatch.propertyValue, currency)} />
                    <StatRow label="Stated Budget"        value={client.statedBudget != null && client.statedBudget > 0 ? currency(client.statedBudget) : "Budget not set"} />
                    <StatRow label="Target Environment"   value={client.bestMatch.neighborhood} />
                    <StatRow label="E(x) on Best-Fit Match" value={evLabel(effectiveExpectedValue, currency)} />
                    <StatRow label="Demo Sessions"        value={String(effectivePastViewings)} />
                    <StatRow label="Total Robot Matches"  value={String(client.allMatches.length)} />
                  </div>
                  {highestLikelihoodMatch && (
                    <div className="border-t border-border bg-muted/30 px-4 py-2.5 text-xs font-semibold">
                      <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                        Highest Likelihood:
                      </span>{" "}
                      <span className="font-mono font-bold text-foreground">{highestLikelihoodMatch.property}</span>
                      {" — "}
                      <span className="font-mono font-bold text-foreground">{percent(highestLikelihoodMatch.probability)}</span>
                    </div>
                  )}
                </div>
              </div>

              {/* AI score decomposition */}
              <div>
                <SectionHeading>
                  <Brain className="inline h-3 w-3 mr-1 text-muted-foreground" strokeWidth={2.5} />
                  AI Score Decomposition
                </SectionHeading>
                <div className="mt-3 rounded-[8px] border border-border bg-card p-4 shadow-[var(--shadow-xs)]">
                  <div className="flex flex-col gap-4">
                    {scoreRows.map((row) => <ScoreBar key={row.label} row={row} />)}
                  </div>
                  <div className="mt-5 border-t border-border pt-4">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold uppercase tracking-wider text-foreground">Total P(Adopt)</span>
                      <span className="font-mono text-2xl font-bold transition-all duration-300 text-foreground">{percent(effectiveProbability)}</span>
                    </div>
                    <div className="mt-2 h-4 w-full rounded-[4px] border border-border bg-muted overflow-hidden">
                      <div className="h-full rounded-[4px] bg-black transition-all duration-500" style={{ width: `${totalProb}%` }} />
                    </div>
                    <div className="mt-1.5 flex justify-between text-[10px] font-semibold text-muted-foreground">
                      <span>0%</span>
                      <span className="font-bold text-primary">High-Fit Prospect ≥ 65%</span>
                      <span>100%</span>
                    </div>
                    {client.bestMatch.mlProbability != null && (
                      <div style={{ marginTop: "10px", fontSize: "12px", color: "#666" }}>
                        Model-calibrated estimate:{" "}
                        <strong style={{ color: "#000" }}>{(client.bestMatch.mlProbability * 100).toFixed(0)}%</strong>{" "}
                        <span style={{ color: "#999" }}>(formula: {(effectiveProbability * 100).toFixed(0)}%)</span>
                      </div>
                    )}
                    {localPastViewings !== null && (
                      <div className="mt-2 font-mono text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                        {effectivePastViewings} demo session{effectivePastViewings !== 1 ? "s" : ""} recorded
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
                  <Sparkles className="inline h-3 w-3 mr-1 text-muted-foreground" strokeWidth={2.5} />
                  AI Reasoning Breakdown
                </SectionHeading>
                <ReasoningBox
                  loading={reasoningLoading}
                  error={reasoningError}
                  text={reasoning}
                />
              </div>

              {/* Company Profile (rich profile fields) */}
              {(client.financingStatus || client.moveInTimeline || client.propertyTypePreference || client.secondaryNeighborhood || client.agentNotes !== undefined) && (
                <div>
                  <SectionHeading>
                    <Wallet className="inline h-3 w-3 mr-1 text-muted-foreground" strokeWidth={2.5} />
                    Company Profile
                  </SectionHeading>
                  <div className="mt-3 rounded-[8px] border border-border bg-card shadow-[var(--shadow-xs)] overflow-hidden">
                    <div className="px-4">
                      {client.financingStatus && (
                        <StatRow label="Procurement / Financing" value={client.financingStatus.replace("-", " ").replace(/\b\w/g, (c) => c.toUpperCase())} />
                      )}
                      {client.moveInTimeline && (
                        <StatRow label="Deployment Timeline" value={client.moveInTimeline} />
                      )}
                      {client.propertyTypePreference && (
                        <StatRow label="Robot Type Preference" value={client.propertyTypePreference} />
                      )}
                      {client.secondaryNeighborhood && (
                        <StatRow label="Secondary Environment" value={client.secondaryNeighborhood} />
                      )}
                    </div>
                    <div className="border-t border-border px-4 py-3">
                      <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mb-1.5">Sales Rep Notes</div>
                      <BuyerNotesField clientId={client.clientId} initialNotes={client.agentNotes ?? ""} />
                    </div>
                  </div>
                </div>
              )}

              {/* Acquisition Track Record */}
              <AcquisitionTrackRecord
                clientId={client.clientId}
                initialPurchases={effectivePurchases}
                onPurchasesUpdated={(updated) => setLocalPurchases(updated)}
              />

              {/* Other property matches */}
              {otherProps.length > 0 && (
                <div>
                  <SectionHeading>
                    <Layers className="inline h-3 w-3 mr-1 text-muted-foreground" strokeWidth={2.5} />
                    Other Listing Matches ({otherProps.length})
                  </SectionHeading>
                  <div className="mt-3 rounded-[8px] border border-border bg-card shadow-[var(--shadow-xs)] overflow-hidden">
                    <div className="flex items-center gap-3 border-b border-border bg-muted/40 px-4 py-2.5">
                      <span className="flex-1 text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Property</span>
                      <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">P / E(x)</span>
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
                    <Building2 className="inline h-3 w-3 mr-1 text-muted-foreground" strokeWidth={2.5} />
                    Target Listing Snapshot
                  </SectionHeading>
                  <div className="mt-3 rounded-[8px] border border-border bg-card p-4 shadow-[var(--shadow-xs)]">
                    <div className="flex items-center gap-3">
                      <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-[8px] bg-black">
                        <Building2 className="h-5 w-5 text-primary" strokeWidth={2.5} />
                      </div>
                      <div>
                        <div className="text-sm font-bold leading-tight text-foreground">{client.bestMatch.property}</div>
                        <div className="flex items-center gap-1 mt-1 text-xs font-semibold text-muted-foreground">
                          <MapPin className="h-3 w-3 text-muted-foreground" strokeWidth={2.5} />
                          {client.bestMatch.neighborhood}
                        </div>
                      </div>
                      <div className="ml-auto text-right">
                        <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Value</div>
                        <div className="font-mono text-base font-bold text-foreground">{priceLabel(client.bestMatch.propertyValue, currency)}</div>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* ── Footer ── */}
        <div className="shrink-0 border-t border-border bg-card">

          {/* Log Viewing confirmation banner */}
          {viewingResult && (
            <div className="flex items-center gap-3 border-b border-primary/40 bg-primary/15 px-5 py-3">
              <CheckCircle2 className="h-5 w-5 shrink-0 text-black" strokeWidth={2.5} />
              <p className="flex-1 text-sm font-bold text-foreground">
                Demo session logged.{" "}
                <span className="font-mono">{viewingResult.clientName}&apos;s</span> P(Adopt) updated to{" "}
                <span className="font-mono font-bold">{Math.round(viewingResult.probability * 100)}%</span>
                {" — "}{viewingResult.tier.replace("_", " ")}
              </p>
              <button
                type="button"
                onClick={() => setViewingResult(null)}
                className="shrink-0 rounded-[var(--radius-sm)] border border-border p-1 text-foreground hover:bg-muted"
                aria-label="Dismiss log confirmation"
              >
                <X className="h-3.5 w-3.5" strokeWidth={2.5} />
              </button>
            </div>
          )}
          {viewingError && (
            <div className="border-b border-border bg-muted/30 px-5 py-3">
              <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Error: {viewingError}</span>
            </div>
          )}

          {/* Outcome confirmation banner */}
          {outcomeResult && (
            <div className={`flex items-center gap-3 border-b border-border px-5 py-3 ${
              outcomeResult === "won" ? "border-l-4 border-l-primary bg-primary/10 text-foreground" : "bg-muted/40 text-muted-foreground"
            }`}>
              {outcomeResult === "won" ? (
                <CheckCircle2 className="h-5 w-5 shrink-0 text-emerald-700" strokeWidth={2.5} />
              ) : (
                <X className="h-5 w-5 shrink-0 text-muted-foreground" strokeWidth={2.5} />
              )}
              <p className="flex-1 text-sm font-bold text-foreground">
                {outcomeResult === "won" ? `Deployment contract recorded for ${client?.name}.` : `Deal marked inactive/passed for ${client?.name}.`}
                {" "}Outcome recorded for prediction model retraining.
              </p>
              <button
                type="button"
                onClick={() => setOutcomeResult(null)}
                className="shrink-0 rounded-[var(--radius-sm)] border border-border p-1 text-foreground hover:bg-muted"
                aria-label="Dismiss outcome confirmation"
              >
                <X className="h-3.5 w-3.5" strokeWidth={2.5} />
              </button>
            </div>
          )}
          {outcomeError && (
            <div className="border-b border-border bg-muted/30 px-5 py-3">
              <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Error: {outcomeError}</span>
            </div>
          )}

          {/* Schedule Viewing confirmation banner */}
          {schedSuccess && (
            <div className="flex items-center gap-3 border-b border-border bg-card px-5 py-3 shadow-[var(--shadow-xs)]">
              <Calendar className="h-5 w-5 shrink-0 text-primary" strokeWidth={2.5} />
              <p className="flex-1 text-sm font-bold text-foreground">{schedSuccess}</p>
              <button
                type="button"
                onClick={() => setSchedSuccess(null)}
                className="shrink-0 rounded-[var(--radius-sm)] border border-border p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
                aria-label="Dismiss schedule confirmation"
              >
                <X className="h-3.5 w-3.5" strokeWidth={2.5} />
              </button>
            </div>
          )}
          {schedError && (
            <div className="border-b border-border bg-muted/30 px-5 py-3">
              <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Error: {schedError}</span>
            </div>
          )}

          {/* Schedule Viewing inline date+time form */}
          {schedFormOpen && (
            <form
              onSubmit={handleScheduleViewingSubmit}
              className="border-b border-border bg-card px-5 py-4"
            >
              <div className="mb-3 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
                Set demo date &amp; time
              </div>
              <div className="flex flex-col gap-3 sm:flex-row">
                <div className="flex flex-1 flex-col gap-1">
                  <label htmlFor="sched-date" className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Date</label>
                  <input
                    id="sched-date"
                    type="date"
                    required
                    value={schedDate}
                    onChange={(e) => setSchedDate(e.target.value)}
                    min={new Date().toISOString().split("T")[0]}
                    className="rounded-[6px] border border-border bg-card px-3 py-2 font-mono text-sm font-bold text-foreground outline-none focus:border-foreground"
                  />
                </div>
                <div className="flex flex-1 flex-col gap-1">
                  <label htmlFor="sched-time" className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Time</label>
                  <input
                    id="sched-time"
                    type="time"
                    required
                    value={schedTime}
                    onChange={(e) => setSchedTime(e.target.value)}
                    className="rounded-[6px] border border-border bg-card px-3 py-2 font-mono text-sm font-bold text-foreground outline-none focus:border-foreground"
                  />
                </div>
                <div className="flex items-end gap-2">
                  <button
                    type="submit"
                    disabled={schedLoading || !schedDate || !schedTime}
                    className="flex items-center gap-2 rounded-[6px] border border-border bg-black px-4 py-2 text-xs font-bold uppercase tracking-wider text-white shadow-[var(--shadow-xs)] transition-all hover:bg-neutral-800 hover:shadow-[var(--shadow-sm)] disabled:opacity-50"
                  >
                    {schedLoading ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" strokeWidth={2.5} />
                    ) : (
                      <CalendarCheck className="h-3.5 w-3.5 text-primary" strokeWidth={2.5} />
                    )}
                    Confirm
                  </button>
                  <button
                    type="button"
                    onClick={() => { setSchedFormOpen(false); setSchedError(null) }}
                    className="rounded-[6px] border border-border bg-card px-4 py-2 text-xs font-bold uppercase tracking-wider text-foreground shadow-[var(--shadow-xs)] transition-all hover:bg-muted"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            </form>
          )}

          {/* Portal Access Panel (Rep Console) */}
          <div className="px-5 pb-2 sm:px-6">
            <PortalAccessPanel clientId={client.clientId} clientName={client.name} />
          </div>

          {/* Inquiry history (Rep Console) */}
          <div className="px-5 pb-2 sm:px-6">
            <CompanyInquiryHistory clientId={client.clientId} />
          </div>

          {/* Action buttons row */}
          <div className="flex flex-col gap-3 p-5 sm:flex-row sm:p-6">
            {effectiveTier === "TIER_1" || effectiveTier === "TIER_2" ? (
              <button
                type="button"
                onClick={() => {
                  if (onGenerateInvite) onGenerateInvite(client)
                }}
                className="flex flex-1 items-center justify-center gap-2 rounded-[8px] border border-border bg-black py-3.5 text-xs sm:text-sm font-bold uppercase tracking-wider text-white shadow-[var(--shadow-xs)] transition-all hover:bg-neutral-800 hover:shadow-[var(--shadow-sm)]"
              >
                <Send className="h-4 w-4 text-primary" strokeWidth={2.5} />
                Send Pitch
              </button>
            ) : (
              <button
                type="button"
                disabled
                className="flex flex-1 cursor-not-allowed items-center justify-center gap-2 rounded-[8px] border border-border bg-muted py-3.5 text-xs sm:text-sm font-bold uppercase tracking-wider text-muted-foreground"
              >
                <Send className="h-4 w-4 text-muted-foreground" strokeWidth={2.5} />
                Send Pitch (High/Possible-Fit Only)
              </button>
            )}

            {/* Schedule Viewing — opens the inline form */}
            <button
              type="button"
              onClick={() => { setSchedFormOpen((o) => !o); setSchedError(null) }}
              className={`flex flex-1 items-center justify-center gap-2 rounded-[8px] border border-border py-3.5 text-xs sm:text-sm font-bold uppercase tracking-wider shadow-[var(--shadow-xs)] transition-all hover:shadow-[var(--shadow-sm)] ${
                schedFormOpen ? "bg-black text-white" : "bg-card text-foreground hover:bg-muted"
              }`}
            >
              <Calendar className="h-4 w-4" strokeWidth={2.5} />
              Schedule Demo
            </button>

            {/* Log Viewing — records a past/completed viewing */}
            <button
              type="button"
              onClick={handleLogViewing}
              disabled={viewingLoading}
              className="flex flex-1 items-center justify-center gap-2 rounded-[8px] border border-border bg-card py-3.5 text-xs sm:text-sm font-bold uppercase tracking-wider text-foreground shadow-[var(--shadow-xs)] transition-all hover:bg-muted hover:shadow-[var(--shadow-sm)] disabled:cursor-not-allowed disabled:opacity-60"
            >
              {viewingLoading ? (
                <Loader2 className="h-4 w-4 animate-spin" strokeWidth={2.5} />
              ) : (
                <CalendarCheck className="h-4 w-4" strokeWidth={2.5} />
              )}
              {viewingLoading ? "Logging…" : "Log Demo"}
            </button>
          </div>

          {/* Won / Lost outcome row */}
          <div className="flex gap-3 border-t border-border px-5 pb-5 pt-3 sm:px-6">
            {effectiveOutcome === "pending" ? (
              <>
                <button
                  type="button"
                  disabled={outcomeLoading}
                  onClick={() => handleRecordOutcome("won")}
                  className="flex flex-1 items-center justify-center gap-2 rounded-[8px] border border-emerald-600 bg-emerald-600 py-3 text-xs sm:text-sm font-bold uppercase tracking-wider text-white shadow-[var(--shadow-xs)] transition-all hover:bg-emerald-700 hover:shadow-[var(--shadow-sm)] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {outcomeLoading ? (
                    <Loader2 className="h-4 w-4 animate-spin text-white" strokeWidth={2.5} />
                  ) : (
                    <CheckCircle2 className="h-4 w-4" strokeWidth={2.5} />
                  )}
                  Record Deployment (Closed Won)
                </button>
                <button
                  type="button"
                  disabled={outcomeLoading}
                  onClick={() => handleRecordOutcome("lost")}
                  className="flex flex-1 items-center justify-center gap-2 rounded-[8px] border border-border bg-card py-3 text-xs sm:text-sm font-bold uppercase tracking-wider text-muted-foreground shadow-[var(--shadow-xs)] transition-all hover:bg-muted hover:text-foreground hover:shadow-[var(--shadow-sm)] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {outcomeLoading ? (
                    <Loader2 className="h-4 w-4 animate-spin" strokeWidth={2.5} />
                  ) : (
                    <X className="h-4 w-4" strokeWidth={2.5} />
                  )}
                  Mark Inactive / Passed
                </button>
              </>
            ) : (
              <>
                {/* Already recorded — show clean status summary */}
                <div className={`flex flex-1 items-center gap-3 rounded-[8px] border border-border px-4 py-3 ${
                  effectiveOutcome === "won" ? "border-l-4 border-l-emerald-600 bg-emerald-50/50 text-foreground" : "bg-muted/40 text-muted-foreground"
                }`}>
                  {effectiveOutcome === "won" ? (
                    <CheckCircle2 className="h-5 w-5 shrink-0 text-emerald-700" strokeWidth={2.5} />
                  ) : (
                    <X className="h-5 w-5 shrink-0 text-muted-foreground" strokeWidth={2.5} />
                  )}
                  <div className="flex-1">
                    <div className="text-xs font-bold uppercase tracking-wider text-foreground">
                      {effectiveOutcome === "won" ? "Deal Status: Sale Completed (Closed)" : "Deal Status: Passed / Inactive"}
                    </div>
                    <div className="text-[10px] font-semibold text-muted-foreground">Tracked in Pipeline Model Calibration</div>
                  </div>
                </div>
                <button
                  type="button"
                  disabled={outcomeLoading}
                  onClick={() => handleRecordOutcome(effectiveOutcome === "won" ? "lost" : "won")}
                  className="flex shrink-0 items-center justify-center gap-2 rounded-[8px] border border-border bg-card px-4 py-3 text-xs font-bold uppercase tracking-wider text-foreground shadow-[var(--shadow-xs)] transition-all hover:bg-muted hover:shadow-[var(--shadow-sm)] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Change Status
                </button>
              </>
            )}
          </div>
        </div>

      </div>
    </div>
  )
}
