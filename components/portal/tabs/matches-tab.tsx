"use client"

import { useState, useMemo, useEffect } from "react"
import {
  ArrowRight, Bookmark, BookmarkCheck, Bot, ChevronRight, Clock, GitCompare, HelpCircle,
  MapPin, MessageSquare, RotateCcw, Sparkles, ThumbsDown, ThumbsUp, TrendingUp, X, XCircle, Zap,
} from "lucide-react"
import type { DashboardData, MatchUnit, PortalTab, UnitFeedback } from "@/lib/portal-types"
import { requestDemo, submitInquiry, saveUnitFeedback } from "@/lib/portal-api"
import { useToast } from "@/hooks/use-toast"
import { Skeleton } from "@/components/ui/skeleton"

// ─── Utilities ────────────────────────────────────────────────────────────────

function formatCost(c: number | null): string {
  if (c == null || c <= 0) return "Price on request"
  return `RM ${c.toLocaleString("en-MY", { maximumFractionDigits: 0 })}`
}

// ─── Request Demo Modal ───────────────────────────────────────────────────────

function DemoModal({
  unit, clientId, onClose, onSuccess,
}: {
  unit: MatchUnit; clientId: string
  onClose: () => void; onSuccess: (id: string) => void
}) {
  const { toast } = useToast()
  const [preferredDate, setPreferredDate] = useState("")
  const [notes, setNotes]   = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true); setError(null)
    try {
      const res = await requestDemo(clientId, {
        property_id: unit.property_id,
        preferred_date: preferredDate || null,
        notes: notes || null,
      })
      if (!res.success && res.existing_id) {
        toast({ title: "Already requested", description: "A demo for this unit is already pending." })
        onClose(); return
      }
      onSuccess(unit.property_id)
      toast({ title: "Demo requested!", description: "A representative will confirm within 24 hours." })
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to submit request.")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm px-4">
      <div className="w-full max-w-lg border border-border bg-card shadow-[var(--shadow-xl)]">
        <div className="flex items-start justify-between gap-4 border-b border-border px-6 py-5">
          <div>
            <span className="inline-flex items-center gap-1.5 border border-border bg-primary px-2.5 py-0.5 text-[10px] font-black uppercase tracking-wider mb-2">
              <Zap className="h-3 w-3" strokeWidth={3} /> Request Demo
            </span>
            <h2 className="text-lg font-bold tracking-tight">{unit.name}</h2>
            <p className="text-sm text-muted-foreground mt-0.5">
              A PIPELINE.EV representative will confirm your slot within 24 hours.
            </p>
          </div>
          <button onClick={onClose} className="shrink-0 border border-border p-1.5 text-muted-foreground hover:bg-muted transition-colors">
            <X className="h-4 w-4" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="flex flex-col gap-5 px-6 py-5">
          <label className="flex flex-col gap-2">
            <span className="text-xs font-black uppercase tracking-wider">Preferred date &amp; time (optional)</span>
            <input type="datetime-local" value={preferredDate} onChange={e => setPreferredDate(e.target.value)}
              className="border border-border bg-white px-3 py-2.5 text-sm text-black focus:outline-none focus-visible:border-primary" />
          </label>
          <label className="flex flex-col gap-2">
            <span className="text-xs font-black uppercase tracking-wider">Additional notes (optional)</span>
            <textarea value={notes} onChange={e => setNotes(e.target.value)}
              placeholder="Any specific requirements or questions for the demo…"
              rows={3} className="resize-none border border-border bg-white px-3 py-2.5 text-sm text-black placeholder:text-muted-foreground focus:outline-none focus-visible:border-primary" />
          </label>
          {error && <p className="text-xs font-semibold text-destructive">{error}</p>}
          <div className="flex gap-3 pt-1">
            <button type="button" onClick={onClose}
              className="flex-1 border border-border bg-muted py-3 text-sm font-black uppercase tracking-wider text-muted-foreground hover:bg-secondary transition-colors">
              Cancel
            </button>
            <button type="submit" disabled={loading}
              className="flex-1 group flex items-center justify-center gap-2 border border-border bg-black py-3 text-sm font-black uppercase tracking-wider text-white hover:shadow-[var(--shadow-sm)] transition-shadow disabled:opacity-40">
              {loading ? "Submitting…" : "Request demo"}
              {!loading && <ArrowRight className="h-4 w-4 text-primary transition-transform group-hover:translate-x-0.5" strokeWidth={3} />}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ─── Inquiry Modal ────────────────────────────────────────────────────────────

function InquiryModal({
  unit, clientId, onClose, onSuccess,
}: {
  unit: MatchUnit; clientId: string
  onClose: () => void; onSuccess: (id: string) => void
}) {
  const { toast } = useToast()
  const [message, setMessage] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!message.trim()) return
    setLoading(true); setError(null)
    try {
      await submitInquiry(clientId, { property_id: unit.property_id, message: message.trim() })
      onSuccess(unit.property_id)
      toast({ title: "Question sent!", description: "Our team will respond shortly." })
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send question.")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm px-4">
      <div className="w-full max-w-lg border border-border bg-card shadow-[var(--shadow-xl)]">
        <div className="flex items-start justify-between gap-4 border-b border-border px-6 py-5">
          <div>
            <span className="inline-flex items-center gap-1.5 border border-border bg-secondary px-2.5 py-0.5 text-[10px] font-black uppercase tracking-wider mb-2">
              <HelpCircle className="h-3 w-3" strokeWidth={3} /> Ask a Question
            </span>
            <h2 className="text-lg font-bold tracking-tight">{unit.name}</h2>
            <p className="text-sm text-muted-foreground mt-0.5">Our team will respond — no commitment required.</p>
          </div>
          <button onClick={onClose} className="shrink-0 border border-border p-1.5 text-muted-foreground hover:bg-muted transition-colors">
            <X className="h-4 w-4" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="flex flex-col gap-5 px-6 py-5">
          <label className="flex flex-col gap-2">
            <span className="text-xs font-black uppercase tracking-wider">Your question</span>
            <textarea value={message} onChange={e => setMessage(e.target.value)}
              placeholder="e.g. What is the minimum floor load bearing requirement for this unit?"
              rows={4} autoFocus
              className="resize-none border border-border bg-white px-3 py-2.5 text-sm text-black placeholder:text-muted-foreground focus:outline-none focus-visible:border-primary" />
          </label>
          {error && <p className="text-xs font-semibold text-destructive">{error}</p>}
          <div className="flex gap-3 pt-1">
            <button type="button" onClick={onClose}
              className="flex-1 border border-border bg-muted py-3 text-sm font-black uppercase tracking-wider text-muted-foreground hover:bg-secondary transition-colors">
              Cancel
            </button>
            <button type="submit" disabled={loading || !message.trim()}
              className="flex-1 group flex items-center justify-center gap-2 border border-border bg-black py-3 text-sm font-black uppercase tracking-wider text-white hover:shadow-[var(--shadow-sm)] transition-shadow disabled:opacity-40">
              {loading ? "Sending…" : "Send question"}
              {!loading && <ArrowRight className="h-4 w-4 text-primary transition-transform group-hover:translate-x-0.5" strokeWidth={3} />}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ─── Compare Panel ────────────────────────────────────────────────────────────

function ComparePanel({
  units, onClose, onRequestDemo,
}: {
  units: MatchUnit[]; onClose: () => void; onRequestDemo: (u: MatchUnit) => void
}) {
  const rows: Array<{ label: string; getValue: (u: MatchUnit) => string }> = [
    { label: "Unit cost",         getValue: u => formatCost(u.cost) },
    { label: "Environment",       getValue: u => u.environment ?? "—" },
    { label: "Category",          getValue: u => u.property_type ?? "—" },
    { label: "Payload tier",      getValue: u => u.payload_tier != null ? `${u.payload_tier}/5` : "—" },
    { label: "Nav sensors",       getValue: u => u.nav_sensors != null ? String(u.nav_sensors) : "—" },
    { label: "Shift coverage",    getValue: u => u.operational_range_sqft != null ? `${u.operational_range_sqft.toLocaleString()} sqft` : "—" },
    { label: "Est. annual savings", getValue: u => u.estimated_annual_savings ? formatCost(u.estimated_annual_savings) + "/yr" : "—" },
    { label: "Payback period",    getValue: u => u.payback_months ? `~${u.payback_months} months` : "—" },
  ]

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm px-4 py-6">
      <div className="w-full max-w-4xl border border-border bg-card shadow-[var(--shadow-xl)] overflow-auto max-h-[90vh]">
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <span className="flex items-center gap-2 text-sm font-black uppercase tracking-wider">
            <GitCompare className="h-4 w-4 text-muted-foreground" />
            Comparing {units.length} units
          </span>
          <button onClick={onClose} className="border border-border p-1.5 text-muted-foreground hover:bg-muted transition-colors">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className="px-5 py-4 text-left text-[10px] font-black uppercase tracking-wider text-muted-foreground w-36">Specification</th>
                {units.map(u => (
                  <th key={u.property_id} className="px-5 py-4 text-left border-l border-border">
                    <div className="font-bold leading-snug text-sm">{u.name}</div>
                    {u.environment && (
                      <div className="flex items-center gap-1 mt-1 text-[10px] text-muted-foreground font-medium">
                        <MapPin className="h-3 w-3 shrink-0" />{u.environment}
                      </div>
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, ri) => (
                <tr key={row.label} className={ri % 2 === 0 ? "bg-muted/30" : ""}>
                  <td className="px-5 py-3 text-[10px] font-black uppercase tracking-wider text-muted-foreground">{row.label}</td>
                  {units.map(u => (
                    <td key={u.property_id} className="px-5 py-3 font-semibold border-l border-border">{row.getValue(u)}</td>
                  ))}
                </tr>
              ))}
              <tr className="border-t border-border">
                <td className="px-5 py-4 text-[10px] font-black uppercase tracking-wider text-muted-foreground">Actions</td>
                {units.map(u => (
                  <td key={u.property_id} className="px-5 py-4 border-l border-border">
                    <button onClick={() => { onClose(); onRequestDemo(u) }}
                      className="group flex items-center gap-1.5 border border-border bg-black px-3 py-2 text-[10px] font-black uppercase tracking-wider text-white hover:shadow-[var(--shadow-xs)] transition-shadow">
                      Request demo <ChevronRight className="h-3 w-3 text-primary" strokeWidth={3} />
                    </button>
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

// ─── Match Card ───────────────────────────────────────────────────────────────

function MatchCard({
  unit, index, isRequested, isInquired, isCompared,
  onRequestDemo, onAskQuestion, onToggleCompare, onFeedback,
}: {
  unit: MatchUnit; index: number
  isRequested: boolean; isInquired: boolean; isCompared: boolean
  onRequestDemo: (u: MatchUnit) => void
  onAskQuestion: (u: MatchUnit) => void
  onToggleCompare: (u: MatchUnit) => void
  onFeedback: (u: MatchUnit, update: Partial<UnitFeedback>) => void
}) {
  const [imgErr, setImgErr] = useState(false)
  const rankLabels = ["Top match", "2nd match", "3rd match", "4th match", "5th match"]

  return (
    <div className={`group flex flex-col border bg-card shadow-[var(--shadow-sm)] hover:shadow-[var(--shadow-md)] transition-shadow duration-200 border-l-[3px] ${isCompared ? "border-primary border-l-primary" : "border-border border-l-border hover:border-l-primary"}`}>
      {/* Image */}
      <div className="relative h-44 bg-neutral-100 flex items-center justify-center overflow-hidden border-b border-border">
        {unit.image_url && !imgErr ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={unit.image_url}
            alt={unit.name}
            className="h-full w-full object-contain p-2"
            loading="lazy"
            onError={() => setImgErr(true)}
          />
        ) : (
          <div className="flex flex-col items-center gap-2 text-muted-foreground">
            <Bot className="h-12 w-12 opacity-30" />
            <span className="text-[10px] font-black uppercase tracking-wider opacity-40">Image coming soon</span>
          </div>
        )}
        <div className="absolute top-3 left-3">
          <span className="inline-flex items-center gap-1 border border-border bg-card px-2.5 py-1 text-[10px] font-black uppercase tracking-wider shadow-[var(--shadow-xs)]">
            {index === 0 && <Sparkles className="h-3 w-3 text-primary" strokeWidth={3} />}
            {rankLabels[index] ?? `#${index + 1}`}
          </span>
        </div>
        <button onClick={() => onToggleCompare(unit)} title={isCompared ? "Remove from compare" : "Add to compare"}
          className={`absolute top-3 right-3 flex items-center gap-1.5 border px-2 py-1 text-[10px] font-black uppercase tracking-wider transition-colors ${isCompared ? "border-primary bg-primary text-primary-foreground" : "border-border bg-card text-muted-foreground hover:border-primary hover:text-primary"}`}>
          <GitCompare className="h-3 w-3" strokeWidth={3} />
          {isCompared ? "Comparing" : "Compare"}
        </button>
      </div>

      {/* Content */}
      <div className="flex flex-1 flex-col gap-4 p-5">
        <div>
          <h3 className="font-bold tracking-tight leading-snug text-base">{unit.name}</h3>
          <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1">
            <span className="text-xs font-semibold">{formatCost(unit.cost)}</span>
            {unit.environment && (
              <span className="flex items-center gap-1 text-xs text-muted-foreground">
                <MapPin className="h-3 w-3 shrink-0" />{unit.environment}
              </span>
            )}
          </div>
        </div>

        {/* Specs */}
        <div className="flex flex-wrap gap-1.5">
          {unit.payload_tier != null && (
            <span className="inline-flex items-center gap-1 border border-border bg-secondary px-2 py-0.5 text-[10px] font-bold">
              <span className="text-muted-foreground">Payload</span>
              <span>{unit.payload_tier}/5</span>
            </span>
          )}
          {unit.nav_sensors != null && (
            <span className="inline-flex items-center gap-1 border border-border bg-secondary px-2 py-0.5 text-[10px] font-bold">
              <span className="text-muted-foreground">Sensors</span>
              <span>{unit.nav_sensors}</span>
            </span>
          )}
          {unit.operational_range_sqft != null && (
            <span className="inline-flex items-center gap-1 border border-border bg-secondary px-2 py-0.5 text-[10px] font-bold">
              <span className="text-muted-foreground">Coverage</span>
              <span>{unit.operational_range_sqft.toLocaleString()} sqft</span>
            </span>
          )}
        </div>

        {/* Feedback Bar */}
        <div className="flex items-center gap-1.5 pt-1">
          <button
            type="button"
            onClick={() => onFeedback(unit, { interest: unit.my_feedback?.interest === "interested" ? null : "interested" })}
            className={`flex items-center gap-1 border px-2 py-1 text-[10px] font-black uppercase tracking-wider transition-colors ${
              unit.my_feedback?.interest === "interested"
                ? "border-emerald-600 bg-emerald-50 text-emerald-700"
                : "border-border bg-card text-muted-foreground hover:bg-secondary"
            }`}
          >
            <ThumbsUp className="h-3 w-3" />
            {unit.my_feedback?.interest === "interested" ? "Interested" : "Interest"}
          </button>
          <button
            type="button"
            onClick={() => onFeedback(unit, { interest: unit.my_feedback?.interest === "not_interested" ? null : "not_interested" })}
            className={`flex items-center gap-1 border px-2 py-1 text-[10px] font-black uppercase tracking-wider transition-colors ${
              unit.my_feedback?.interest === "not_interested"
                ? "border-rose-600 bg-rose-50 text-rose-700"
                : "border-border bg-card text-muted-foreground hover:bg-secondary"
            }`}
          >
            <ThumbsDown className="h-3 w-3" />
            {unit.my_feedback?.interest === "not_interested" ? "Passed" : "Pass"}
          </button>
          <button
            type="button"
            onClick={() => onFeedback(unit, { is_saved: !unit.my_feedback?.is_saved })}
            className={`ml-auto flex items-center gap-1 border px-2 py-1 text-[10px] font-black uppercase tracking-wider transition-colors ${
              unit.my_feedback?.is_saved
                ? "border-primary bg-primary text-primary-foreground"
                : "border-border bg-card text-muted-foreground hover:bg-secondary"
            }`}
          >
            {unit.my_feedback?.is_saved ? <BookmarkCheck className="h-3 w-3" /> : <Bookmark className="h-3 w-3" />}
            {unit.my_feedback?.is_saved ? "Saved" : "Save"}
          </button>
        </div>

        {/* ROI strip */}
        {(unit.payback_months || unit.estimated_annual_savings) && (
          <div className="border border-border bg-secondary/60 p-3 flex items-start gap-3">
            <TrendingUp className="h-4 w-4 text-primary shrink-0 mt-0.5" />
            <div className="flex flex-col gap-0.5">
              {unit.estimated_annual_savings && (
                <p className="text-xs text-muted-foreground leading-snug">
                  Est. <span className="font-bold text-foreground">{formatCost(unit.estimated_annual_savings)}/yr</span> in labour savings
                </p>
              )}
              {unit.payback_months && (
                <p className="text-xs text-muted-foreground leading-snug">
                  Payback: <span className="font-bold text-foreground">~{unit.payback_months} months</span>
                </p>
              )}
              <p className="text-[10px] text-muted-foreground/60 mt-0.5">Based on category benchmarks. Actual savings may vary.</p>
            </div>
          </div>
        )}

        {/* Why this fits (client-facing reasoning from client_facing_reasoning_cache only) */}
        {unit.reasoning && (
          <div className="border border-border bg-muted/60 p-3">
            <div className="mb-1.5 flex items-center gap-1.5">
              <Sparkles className="h-3 w-3 text-primary shrink-0" strokeWidth={2.5} />
              <span className="text-[10px] font-black uppercase tracking-wider text-muted-foreground">Why this fits you</span>
            </div>
            <p className="text-sm text-foreground/80 leading-relaxed line-clamp-3">{unit.reasoning}</p>
          </div>
        )}

        {/* CTAs */}
        <div className="mt-auto flex flex-col gap-2">
          {isRequested ? (
            <div className="flex items-center justify-center gap-2 border border-amber-200 bg-amber-50 px-4 py-2.5 text-xs font-black uppercase tracking-wider text-amber-700">
              <Clock className="h-3.5 w-3.5" /> Demo requested — awaiting confirmation
            </div>
          ) : (
            <button onClick={() => onRequestDemo(unit)}
              className="group/btn w-full flex items-center justify-center gap-2 border border-border bg-black px-4 py-2.5 text-xs font-black uppercase tracking-wider text-white hover:shadow-[var(--shadow-sm)] transition-shadow">
              Request demonstration
              <ChevronRight className="h-3.5 w-3.5 text-primary transition-transform group-hover/btn:translate-x-0.5" strokeWidth={3} />
            </button>
          )}
          {isInquired ? (
            <div className="flex items-center justify-center gap-2 border border-border bg-muted px-4 py-2 text-[10px] font-black uppercase tracking-wider text-muted-foreground">
              <MessageSquare className="h-3 w-3" /> Question sent — we will respond soon
            </div>
          ) : (
            <button onClick={() => onAskQuestion(unit)}
              className="w-full flex items-center justify-center gap-2 border border-border bg-white px-4 py-2 text-[10px] font-black uppercase tracking-wider text-foreground hover:bg-muted transition-colors">
              <HelpCircle className="h-3 w-3" strokeWidth={2.5} /> Ask a question
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

// ─── Matches Tab ──────────────────────────────────────────────────────────────

type SortKey = "default" | "cost_asc" | "cost_desc" | "payback_asc"

export function MatchesTab({
  clientId,
  data,
  loading,
  onNavigate,
}: {
  clientId: string
  data: DashboardData | null
  loading: boolean
  onNavigate?: (tab: PortalTab) => void
}) {
  const [activeModal,   setActiveModal]   = useState<MatchUnit | null>(null)
  const [inquiryModal,  setInquiryModal]  = useState<MatchUnit | null>(null)
  const [requestedIds,  setRequestedIds]  = useState<Set<string>>(new Set())
  const [inquiredIds,   setInquiredIds]   = useState<Set<string>>(new Set())
  const [compareIds,    setCompareIds]    = useState<Set<string>>(new Set())
  const [showCompare,   setShowCompare]   = useState(false)
  const [sortKey,       setSortKey]       = useState<SortKey>("default")
  const [filterEnv,     setFilterEnv]     = useState<string>("all")
  const [localFeedback, setLocalFeedback] = useState<Record<string, UnitFeedback>>({})

  async function handleFeedback(unit: MatchUnit, update: Partial<UnitFeedback>) {
    const prev = localFeedback[unit.property_id] ?? unit.my_feedback
    const updated: UnitFeedback = {
      interest: update.interest !== undefined ? update.interest : prev?.interest ?? null,
      reason: update.reason !== undefined ? update.reason : prev?.reason ?? null,
      is_saved: update.is_saved !== undefined ? update.is_saved : prev?.is_saved ?? false,
    }
    setLocalFeedback(p => ({ ...p, [unit.property_id]: updated }))
    try {
      await saveUnitFeedback(clientId, unit.property_id, updated)
    } catch {
      setLocalFeedback(p => ({ ...p, [unit.property_id]: prev as UnitFeedback }))
    }
  }

  const units = data?.matches ?? []

  // Seed requested IDs from existing demos (useEffect — setState is a side effect)
  useEffect(() => {
    if (!data) return
    setRequestedIds(new Set(
      data.scheduled_demos
        .filter(d => d.status === "requested" || d.status === "upcoming" || d.status === "offered")
        .map(d => d.property_id || (units.find(u => u.name === d.property_name)?.property_id ?? ""))
        .filter(Boolean)
    ))
  }, [data, units])

  // Unique environments for filter
  const environments = useMemo(() => {
    const envs = [...new Set(units.map(u => u.environment).filter(Boolean) as string[])]
    return envs.sort()
  }, [units])

  // Sort + filter
  const displayed = useMemo(() => {
    let list = [...units]
    if (filterEnv !== "all") list = list.filter(u => u.environment === filterEnv)
    switch (sortKey) {
      case "cost_asc":    list.sort((a, b) => (a.cost ?? Infinity) - (b.cost ?? Infinity)); break
      case "cost_desc":   list.sort((a, b) => (b.cost ?? 0) - (a.cost ?? 0)); break
      case "payback_asc": list.sort((a, b) => (a.payback_months ?? 999) - (b.payback_months ?? 999)); break
      default: break // default = ranked order from backend
    }
    return list
  }, [units, sortKey, filterEnv])

  function handleDemoSuccess(propertyId: string) {
    setRequestedIds(prev => new Set([...prev, propertyId]))
    setActiveModal(null)
  }

  function handleInquirySuccess(propertyId: string) {
    setInquiredIds(prev => new Set([...prev, propertyId]))
    setInquiryModal(null)
  }

  function handleToggleCompare(unit: MatchUnit) {
    setCompareIds(prev => {
      const next = new Set(prev)
      if (next.has(unit.property_id)) next.delete(unit.property_id)
      else if (next.size < 3) next.add(unit.property_id)
      return next
    })
  }

  const compareUnits = units.filter(u => compareIds.has(u.property_id))

  // ── Loading skeleton ───────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="mx-auto max-w-6xl px-4 sm:px-6 py-10 flex flex-col gap-6">
        <div className="flex gap-3">
          <Skeleton className="h-9 w-32" />
          <Skeleton className="h-9 w-40" />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="border border-border bg-card flex flex-col overflow-hidden">
              <Skeleton className="h-44 rounded-none" />
              <div className="flex flex-col gap-3 p-5">
                <Skeleton className="h-5 w-3/4" />
                <Skeleton className="h-4 w-1/2" />
                <Skeleton className="h-16" />
                <Skeleton className="h-8" />
              </div>
            </div>
          ))}
        </div>
      </div>
    )
  }

  // ── Empty state ────────────────────────────────────────────────────────────
  if (units.length === 0) {
    return (
      <div className="mx-auto max-w-6xl px-4 sm:px-6 py-10">
        <div className="border border-border bg-card p-12 text-center shadow-[var(--shadow-sm)]">
          <Bot className="mx-auto h-8 w-8 text-muted-foreground mb-3 opacity-50" />
          <p className="text-sm text-muted-foreground mb-4">
            No recommendations yet — your representative is preparing your profile.
          </p>
          {onNavigate && (
            <button
              type="button"
              onClick={() => onNavigate("catalog")}
              className="inline-flex items-center gap-2 border border-border bg-black px-4 py-2 text-xs font-black uppercase tracking-wider text-white hover:shadow-[var(--shadow-sm)] transition-shadow"
            >
              Browse all units
              <ArrowRight className="h-3.5 w-3.5 text-primary" strokeWidth={3} />
            </button>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-6xl px-4 sm:px-6 py-10 flex flex-col gap-6">
      {/* Modals */}
      {activeModal  && <DemoModal    unit={activeModal}  clientId={clientId} onClose={() => setActiveModal(null)}  onSuccess={handleDemoSuccess} />}
      {inquiryModal && <InquiryModal unit={inquiryModal} clientId={clientId} onClose={() => setInquiryModal(null)} onSuccess={handleInquirySuccess} />}
      {showCompare && compareUnits.length >= 2 && (
        <ComparePanel units={compareUnits} onClose={() => setShowCompare(false)} onRequestDemo={setActiveModal} />
      )}

      {/* Header + controls */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-xs font-black uppercase tracking-wider text-muted-foreground flex items-center gap-2">
          <RotateCcw className="h-3.5 w-3.5" />
          {displayed.length} unit{displayed.length !== 1 ? "s" : ""} matched
          {filterEnv !== "all" && ` · ${filterEnv}`}
        </h1>
        <div className="flex flex-wrap items-center gap-2">
          {onNavigate && (
            <button
              type="button"
              onClick={() => onNavigate("catalog")}
              className="group flex items-center gap-1.5 border border-border bg-card px-3 py-1.5 text-xs font-bold text-foreground hover:bg-muted transition-colors shadow-[var(--shadow-xs)]"
            >
              Browse all units
              <ArrowRight className="h-3.5 w-3.5 text-primary transition-transform group-hover:translate-x-0.5" strokeWidth={3} />
            </button>
          )}
          {/* Environment filter */}
          {environments.length > 0 && (
            <select
              id="matches-filter-env"
              value={filterEnv}
              onChange={e => setFilterEnv(e.target.value)}
              className="border border-border bg-white px-3 py-1.5 text-xs font-bold text-foreground focus:outline-none focus-visible:border-primary"
            >
              <option value="all">All environments</option>
              {environments.map(env => <option key={env} value={env}>{env}</option>)}
            </select>
          )}
          {/* Sort */}
          <select
            id="matches-sort"
            value={sortKey}
            onChange={e => setSortKey(e.target.value as SortKey)}
            className="border border-border bg-white px-3 py-1.5 text-xs font-bold text-foreground focus:outline-none focus-visible:border-primary"
          >
            <option value="default">Best match first</option>
            <option value="cost_asc">Price: low to high</option>
            <option value="cost_desc">Price: high to low</option>
            <option value="payback_asc">Fastest payback</option>
          </select>
        </div>
      </div>

      {/* Compare bar */}
      {compareIds.size >= 2 && (
        <div className="sticky top-[102px] z-40 border border-primary bg-primary shadow-[var(--shadow-md)] px-5 py-3 flex items-center justify-between gap-4">
          <span className="text-xs font-black uppercase tracking-wider">
            {compareIds.size} units selected — ready to compare
          </span>
          <div className="flex gap-3">
            <button onClick={() => setCompareIds(new Set())}
              className="border border-black/20 bg-black/10 px-3 py-1.5 text-[10px] font-black uppercase tracking-wider hover:bg-black/20 transition-colors">
              Clear
            </button>
            <button onClick={() => setShowCompare(true)}
              className="group flex items-center gap-2 border border-black/30 bg-black px-4 py-1.5 text-[10px] font-black uppercase tracking-wider text-white hover:shadow-[var(--shadow-xs)] transition-shadow">
              View comparison <GitCompare className="h-3.5 w-3.5" strokeWidth={3} />
            </button>
          </div>
        </div>
      )}
      {compareIds.size === 1 && (
        <p className="text-[10px] text-muted-foreground">Select 1 more unit to compare</p>
      )}

      {/* Grid */}
      {displayed.length === 0 ? (
        <div className="border border-border bg-card p-12 text-center">
          <XCircle className="mx-auto h-6 w-6 text-muted-foreground mb-2 opacity-50" />
          <p className="text-sm text-muted-foreground">No units match the current filter.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {displayed.map((unit, i) => (
            <MatchCard
              key={unit.property_id}
              unit={{
                ...unit,
                my_feedback: localFeedback[unit.property_id] !== undefined ? localFeedback[unit.property_id] : unit.my_feedback,
              }}
              index={units.indexOf(unit)} // original rank index
              isRequested={requestedIds.has(unit.property_id)}
              isInquired={inquiredIds.has(unit.property_id)}
              isCompared={compareIds.has(unit.property_id)}
              onRequestDemo={setActiveModal}
              onAskQuestion={setInquiryModal}
              onToggleCompare={handleToggleCompare}
              onFeedback={handleFeedback}
            />
          ))}
        </div>
      )}
    </div>
  )
}
