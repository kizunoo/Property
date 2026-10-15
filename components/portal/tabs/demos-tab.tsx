"use client"

import { useEffect, useState, useCallback } from "react"
import {
  ArrowRight,
  Bot,
  CalendarCheck2,
  CalendarClock,
  CalendarPlus,
  Calendar as CalendarIcon,
  CheckCircle2,
  Clock,
  Download,
  Loader2,
  RefreshCw,
  X,
  XCircle,
  AlertCircle,
  RotateCcw,
  Ban,
  Check,
} from "lucide-react"
import type { Demo, CatalogUnit } from "@/lib/portal-types"
import {
  fetchMyDemos,
  requestDemo,
  confirmDemo,
  cancelDemo,
  rescheduleDemo,
  fetchCatalog,
} from "@/lib/portal-api"
import { useToast } from "@/hooks/use-toast"
import { Skeleton } from "@/components/ui/skeleton"

// ─── Status config ────────────────────────────────────────────────────────────

const STATUS_CONFIG: Record<
  string,
  {
    label: string
    icon: React.ReactNode
    className: string
  }
> = {
  requested: {
    label: "Awaiting confirmation",
    icon: <Clock className="h-3.5 w-3.5" />,
    className: "bg-amber-50 border border-amber-200 text-amber-700",
  },
  offered: {
    label: "Slot offered — Action needed",
    icon: <CalendarClock className="h-3.5 w-3.5 text-primary" />,
    className: "bg-primary/20 border border-primary text-foreground font-black",
  },
  upcoming: {
    label: "Confirmed",
    icon: <CalendarCheck2 className="h-3.5 w-3.5" />,
    className: "bg-primary border border-primary/30 text-primary-foreground",
  },
  completed: {
    label: "Completed",
    icon: <CheckCircle2 className="h-3.5 w-3.5" />,
    className: "bg-secondary border border-border text-secondary-foreground",
  },
  cancelled: {
    label: "Cancelled",
    icon: <XCircle className="h-3.5 w-3.5" />,
    className: "bg-muted border border-border text-muted-foreground",
  },
}

function formatDate(s: string | null): string {
  if (!s) return "Date TBC (Agent confirming timing)"
  try {
    return new Date(s).toLocaleDateString("en-MY", {
      weekday: "short",
      day: "numeric",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    })
  } catch {
    return s
  }
}

// ─── New Demo Request Modal (with unit selector) ──────────────────────────────

function NewDemoModal({
  clientId,
  onClose,
  onSuccess,
}: {
  clientId: string
  onClose: () => void
  onSuccess: () => void
}) {
  const { toast } = useToast()
  const [catalogUnits, setCatalogUnits] = useState<CatalogUnit[]>([])
  const [loadingCatalog, setLoadingCatalog] = useState(true)
  const [selectedPropertyId, setSelectedPropertyId] = useState<string>("")
  const [preferredDate, setPreferredDate] = useState("")
  const [notes, setNotes] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    fetchCatalog(clientId)
      .then((data) => {
        if (!active) return
        setCatalogUnits(data.units || [])
        if (data.units?.length > 0) {
          setSelectedPropertyId(data.units[0].property_id)
        }
      })
      .catch((err) => {
        if (!active) return
        setError("Failed to load robot units. Please try again.")
      })
      .finally(() => {
        if (active) setLoadingCatalog(false)
      })
    return () => {
      active = false
    }
  }, [clientId])

  const selectedUnit = catalogUnits.find((u) => u.property_id === selectedPropertyId)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!selectedPropertyId) {
      setError("Please select a robot unit to demonstrate.")
      return
    }

    setSubmitting(true)
    setError(null)

    try {
      const res = await requestDemo(clientId, {
        property_id: selectedPropertyId,
        preferred_date: preferredDate ? new Date(preferredDate).toISOString() : null,
        notes: notes.trim() || null,
      })

      if (!res.success) {
        setError(res.message || "A demo for this unit is already scheduled.")
        return
      }

      toast({
        title: "Demo request submitted!",
        description:
          "Your PIPELINE.EV sales representative will review the slot and confirm shortly.",
      })
      onSuccess()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to submit demo request.")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm px-4">
      <div className="w-full max-w-lg border border-border bg-card shadow-[var(--shadow-xl)]">
        {/* Header */}
        <div className="flex items-start justify-between gap-4 border-b border-border px-6 py-5">
          <div>
            <span className="inline-flex items-center gap-1.5 border border-border bg-primary px-2.5 py-0.5 text-[10px] font-black uppercase tracking-wider mb-2">
              <CalendarPlus className="h-3 w-3" strokeWidth={3} /> Request Hardware Demo
            </span>
            <h2 className="text-lg font-bold tracking-tight">Book a demonstration</h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              Select a robot model from your catalog and propose a date. Our technical sales team will confirm within 24 hours.
            </p>
          </div>
          <button
            onClick={onClose}
            className="shrink-0 border border-border p-1.5 text-muted-foreground hover:bg-muted transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="flex flex-col gap-4 px-6 py-5">
          {/* Unit selector */}
          <div className="flex flex-col gap-2">
            <label htmlFor="unit-select" className="text-xs font-black uppercase tracking-wider">
              Robot Model <span className="text-destructive">*</span>
            </label>
            {loadingCatalog ? (
              <div className="h-10 flex items-center gap-2 border border-border bg-muted/40 px-3 text-xs text-muted-foreground">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading robot catalog…
              </div>
            ) : catalogUnits.length === 0 ? (
              <p className="text-xs text-destructive">No robot models found in catalog.</p>
            ) : (
              <select
                id="unit-select"
                value={selectedPropertyId}
                onChange={(e) => setSelectedPropertyId(e.target.value)}
                className="h-10 border border-border bg-background px-3 text-sm text-foreground focus:outline-none focus:border-primary font-medium"
              >
                {catalogUnits.map((item) => (
                  <option key={item.property_id} value={item.property_id}>
                    {item.name} — {item.environment || item.property_type || "Industrial"}
                  </option>
                ))}
              </select>
            )}

            {/* Selected unit preview card */}
            {selectedUnit && (
              <div className="mt-1 flex items-center gap-3 border border-border/60 bg-muted/30 p-2.5 text-xs">
                {selectedUnit.image_url ? (
                  <img
                    src={selectedUnit.image_url}
                    alt={selectedUnit.name}
                    className="h-10 w-12 object-cover border border-border shrink-0"
                  />
                ) : (
                  <div className="flex h-10 w-12 items-center justify-center border border-border bg-black/10 shrink-0">
                    <Bot className="h-5 w-5 text-muted-foreground" />
                  </div>
                )}
                <div className="flex-1 min-w-0">
                  <p className="font-bold truncate text-foreground">{selectedUnit.name}</p>
                  <p className="text-[11px] text-muted-foreground">
                    Target: {selectedUnit.environment || "Industrial facility"} • CapEx:{" "}
                    {selectedUnit.cost ? `RM ${selectedUnit.cost.toLocaleString()}` : "Inquire"}
                  </p>
                </div>
              </div>
            )}
          </div>

          {/* Preferred date */}
          <div className="flex flex-col gap-2">
            <label htmlFor="preferred-date" className="text-xs font-black uppercase tracking-wider">
              Preferred Date &amp; Time (Optional)
            </label>
            <input
              id="preferred-date"
              type="datetime-local"
              value={preferredDate}
              onChange={(e) => setPreferredDate(e.target.value)}
              className="border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:border-primary"
            />
            <span className="text-[10px] text-muted-foreground">
              If left blank, your sales rep will offer available slots for your team to confirm.
            </span>
          </div>

          {/* Additional notes */}
          <div className="flex flex-col gap-2">
            <label htmlFor="demo-notes" className="text-xs font-black uppercase tracking-wider">
              Facility Requirements / Scope Notes (Optional)
            </label>
            <textarea
              id="demo-notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="e.g. On-site power available, testing 50kg payload run, team of 4 attendees…"
              rows={3}
              className="resize-none border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary"
            />
          </div>

          {error && (
            <div className="border border-destructive/30 bg-destructive/10 p-2.5 text-xs font-semibold text-destructive flex items-center gap-2">
              <AlertCircle className="h-4 w-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* Action buttons */}
          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 border border-border bg-muted py-2.5 text-xs font-black uppercase tracking-wider text-muted-foreground hover:bg-secondary transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting || loadingCatalog || !selectedPropertyId}
              className="flex-1 group flex items-center justify-center gap-2 border border-border bg-black py-2.5 text-xs font-black uppercase tracking-wider text-white hover:bg-zinc-800 transition-colors disabled:opacity-40"
            >
              {submitting ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" /> Submitting…
                </>
              ) : (
                <>
                  Submit Request
                  <ArrowRight className="h-3.5 w-3.5 text-primary transition-transform group-hover:translate-x-0.5" />
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ─── Reschedule Modal ────────────────────────────────────────────────────────

function RescheduleModal({
  clientId,
  demo,
  onClose,
  onSuccess,
}: {
  clientId: string
  demo: Demo
  onClose: () => void
  onSuccess: () => void
}) {
  const { toast } = useToast()
  const [preferredDate, setPreferredDate] = useState("")
  const [notes, setNotes] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleReschedule(e: React.FormEvent) {
    e.preventDefault()
    setSubmitting(true)
    setError(null)

    try {
      await rescheduleDemo(clientId, demo.id, {
        preferred_date: preferredDate ? new Date(preferredDate).toISOString() : null,
        notes: notes.trim() || null,
      })

      toast({
        title: "Reschedule requested",
        description: "Your previous slot was released and a new request was logged for your rep.",
      })
      onSuccess()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to reschedule.")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm px-4">
      <div className="w-full max-w-md border border-border bg-card shadow-[var(--shadow-xl)]">
        <div className="flex items-start justify-between gap-4 border-b border-border px-6 py-4">
          <div>
            <h2 className="text-base font-bold tracking-tight">Reschedule Demonstration</h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              Unit: <span className="font-semibold text-foreground">{demo.property_name}</span>
            </p>
          </div>
          <button
            onClick={onClose}
            className="shrink-0 border border-border p-1.5 text-muted-foreground hover:bg-muted"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <form onSubmit={handleReschedule} className="flex flex-col gap-4 px-6 py-5">
          <div className="rounded border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">
            Current slot: <span className="font-bold">{formatDate(demo.scheduled_at)}</span>
            <p className="text-[11px] mt-1 text-amber-700">
              Requesting a reschedule releases this slot and notifies your sales rep to assign a new time.
            </p>
          </div>

          <div className="flex flex-col gap-2">
            <label htmlFor="reschedule-date" className="text-xs font-black uppercase tracking-wider">
              New Preferred Date &amp; Time
            </label>
            <input
              id="reschedule-date"
              type="datetime-local"
              value={preferredDate}
              onChange={(e) => setPreferredDate(e.target.value)}
              className="border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:border-primary"
            />
          </div>

          <div className="flex flex-col gap-2">
            <label htmlFor="reschedule-notes" className="text-xs font-black uppercase tracking-wider">
              Reason / Notes
            </label>
            <textarea
              id="reschedule-notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="e.g. Schedule clash with plant shutdown; need afternoon slot instead."
              rows={3}
              className="resize-none border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary"
            />
          </div>

          {error && <p className="text-xs font-semibold text-destructive">{error}</p>}

          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 border border-border bg-muted py-2 text-xs font-black uppercase tracking-wider text-muted-foreground hover:bg-secondary"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="flex-1 flex items-center justify-center gap-2 border border-border bg-black py-2 text-xs font-black uppercase tracking-wider text-white hover:bg-zinc-800 disabled:opacity-40"
            >
              {submitting ? <Loader2 className="h-3 w-3 animate-spin text-primary" /> : "Confirm Reschedule"}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ─── Main Demos Tab ───────────────────────────────────────────────────────────

export function DemosTab({ clientId }: { clientId: string }) {
  const { toast } = useToast()
  const [demos, setDemos] = useState<Demo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showNewDemo, setShowNewDemo] = useState(false)
  const [rescheduleTarget, setRescheduleTarget] = useState<Demo | null>(null)
  const [actionInProgress, setActionInProgress] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchMyDemos(clientId)
      setDemos(data.demos || (data as any).viewings || [])
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load demonstrations.")
    } finally {
      setLoading(false)
    }
  }, [clientId])

  useEffect(() => {
    load()
  }, [load])

  async function handleConfirmSlot(demoId: string) {
    setActionInProgress(demoId)
    try {
      await confirmDemo(clientId, demoId)
      toast({
        title: "Demonstration slot confirmed!",
        description: "Your session is confirmed. You can now download the calendar invite (.ics).",
      })
      await load()
    } catch (err) {
      toast({
        title: "Confirmation failed",
        description: err instanceof Error ? err.message : "Please try again.",
        variant: "destructive",
      })
    } finally {
      setActionInProgress(null)
    }
  }

  async function handleCancelDemo(demoId: string) {
    if (!window.confirm("Are you sure you want to cancel this demonstration?")) {
      return
    }
    setActionInProgress(demoId)
    try {
      await cancelDemo(clientId, demoId, "Cancelled by client via portal")
      toast({
        title: "Demonstration cancelled",
        description: "The demonstration request has been cancelled.",
      })
      await load()
    } catch (err) {
      toast({
        title: "Cancellation failed",
        description: err instanceof Error ? err.message : "Please try again.",
        variant: "destructive",
      })
    } finally {
      setActionInProgress(null)
    }
  }

  const upcoming = demos.filter(
    (d) => d.status === "upcoming" || d.status === "requested" || d.status === "offered"
  )
  const past = demos.filter((d) => d.status === "completed" || d.status === "cancelled")

  if (loading) {
    return (
      <div className="mx-auto max-w-4xl px-4 sm:px-6 py-10 flex flex-col gap-6">
        <Skeleton className="h-8 w-48" />
        {[...Array(3)].map((_, i) => (
          <Skeleton key={i} className="h-28" />
        ))}
      </div>
    )
  }

  if (error) {
    return (
      <div className="mx-auto max-w-4xl px-4 sm:px-6 py-10">
        <div className="border border-border bg-card p-8 text-center shadow-[var(--shadow-sm)]">
          <XCircle className="mx-auto h-6 w-6 text-destructive mb-2" />
          <p className="text-sm font-semibold text-destructive mb-4">{error}</p>
          <button
            onClick={load}
            className="border border-border bg-black px-4 py-2 text-xs font-black uppercase tracking-wider text-white hover:bg-zinc-800"
          >
            Try again
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-4xl px-4 sm:px-6 py-10 flex flex-col gap-8">
      {showNewDemo && (
        <NewDemoModal
          clientId={clientId}
          onClose={() => setShowNewDemo(false)}
          onSuccess={() => {
            setShowNewDemo(false)
            load()
          }}
        />
      )}

      {rescheduleTarget && (
        <RescheduleModal
          clientId={clientId}
          demo={rescheduleTarget}
          onClose={() => setRescheduleTarget(null)}
          onSuccess={() => {
            setRescheduleTarget(null)
            load()
          }}
        />
      )}

      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4 border-b border-border pb-4">
        <div>
          <h1 className="text-[10px] font-black uppercase tracking-wider text-muted-foreground flex items-center gap-2">
            <CalendarClock className="h-3.5 w-3.5 text-primary" />
            Hardware Demonstrations
          </h1>
          <p className="text-sm font-bold text-foreground mt-0.5">
            Schedule, confirm, and manage hands-on robot evaluations
          </p>
        </div>
        <button
          id="request-new-demo-btn"
          onClick={() => setShowNewDemo(true)}
          className="group flex items-center gap-2 border border-border bg-black px-4 py-2.5 text-xs font-black uppercase tracking-wider text-white hover:bg-zinc-800 transition-colors shadow-[var(--shadow-xs)]"
        >
          <CalendarPlus className="h-3.5 w-3.5 text-primary" strokeWidth={3} />
          Request New Demo
        </button>
      </div>

      {/* Upcoming / Requested / Offered Demos */}
      <section aria-label="Upcoming demonstrations">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-xs font-black uppercase tracking-wider text-muted-foreground">
            Active Demonstrations ({upcoming.length})
          </h2>
          <button
            onClick={load}
            title="Refresh demos"
            className="text-xs text-muted-foreground hover:text-foreground p-1"
          >
            <RefreshCw className="h-3.5 w-3.5" />
          </button>
        </div>

        {upcoming.length === 0 ? (
          <div className="border border-border bg-card p-8 text-center">
            <Bot className="mx-auto h-7 w-7 text-muted-foreground opacity-40 mb-2" />
            <p className="text-sm font-bold text-foreground">No active demo bookings</p>
            <p className="text-xs text-muted-foreground mt-1 max-w-sm mx-auto">
              Request an on-site demonstration for any robot model in your catalog to evaluate performance on your plant floor.
            </p>
            <button
              onClick={() => setShowNewDemo(true)}
              className="mt-4 border border-border bg-black px-4 py-2 text-xs font-black uppercase tracking-wider text-white hover:bg-zinc-800"
            >
              Request a demo
            </button>
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            {upcoming.map((demo) => {
              const cfg = STATUS_CONFIG[demo.status] ?? STATUS_CONFIG.requested
              const isBusy = actionInProgress === demo.id
              const canConfirmSlot =
                demo.can_confirm &&
                (demo.status === "requested" || demo.status === "offered")

              return (
                <div
                  key={demo.id}
                  className="border border-border bg-card p-5 shadow-[var(--shadow-sm)] flex flex-col gap-4 transition-all"
                >
                  <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
                    {/* Unit & Environment details */}
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-base text-foreground leading-snug">
                          {demo.property_name || "Robot Unit"}
                        </span>
                        <span
                          className={`inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-black uppercase tracking-wider ${cfg.className}`}
                        >
                          {cfg.icon}
                          {cfg.label}
                        </span>
                      </div>
                      {demo.property_environment && (
                        <p className="text-xs text-muted-foreground mt-0.5">
                          Target Environment: {demo.property_environment}
                        </p>
                      )}
                      <div className="flex items-center gap-2 text-xs text-muted-foreground mt-2">
                        <CalendarIcon className="h-3.5 w-3.5 text-primary shrink-0" />
                        <span className="font-medium text-foreground">
                          {formatDate(demo.scheduled_at)}
                        </span>
                      </div>
                    </div>

                    {/* Primary Confirmation Action if slot offered or awaiting client check */}
                    {canConfirmSlot && (
                      <button
                        onClick={() => handleConfirmSlot(demo.id)}
                        disabled={isBusy}
                        className="self-start sm:self-auto flex items-center gap-1.5 border border-primary bg-primary px-3.5 py-1.5 text-xs font-black uppercase tracking-wider text-primary-foreground hover:bg-primary/90 transition-colors shrink-0 disabled:opacity-50"
                      >
                        {isBusy ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <Check className="h-3.5 w-3.5 stroke-[3]" />
                        )}
                        Confirm Slot
                      </button>
                    )}
                  </div>

                  {/* Actions Strip */}
                  <div className="flex items-center gap-2 pt-3 border-t border-border flex-wrap">
                    {/* Add to Calendar */}
                    {demo.ics_url ? (
                      <a
                        href={demo.ics_url}
                        download={`demo_${demo.id}.ics`}
                        className="inline-flex items-center gap-1.5 border border-border bg-secondary px-3 py-1 text-xs font-bold uppercase tracking-wider text-foreground hover:bg-secondary/80 transition-colors"
                      >
                        <Download className="h-3.5 w-3.5 text-primary" />
                        Add to Calendar (.ics)
                      </a>
                    ) : null}

                    {/* Reschedule */}
                    {demo.can_reschedule && (
                      <button
                        onClick={() => setRescheduleTarget(demo)}
                        disabled={isBusy}
                        className="inline-flex items-center gap-1.5 border border-border bg-background px-3 py-1 text-xs font-bold uppercase tracking-wider text-muted-foreground hover:bg-muted hover:text-foreground transition-colors disabled:opacity-40"
                      >
                        <RotateCcw className="h-3.5 w-3.5" />
                        Reschedule
                      </button>
                    )}

                    {/* Cancel */}
                    {demo.can_cancel && (
                      <button
                        onClick={() => handleCancelDemo(demo.id)}
                        disabled={isBusy}
                        className="inline-flex items-center gap-1.5 border border-border bg-background px-3 py-1 text-xs font-bold uppercase tracking-wider text-destructive hover:bg-destructive/10 transition-colors ml-auto disabled:opacity-40"
                      >
                        <Ban className="h-3.5 w-3.5" />
                        Cancel Demo
                      </button>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </section>

      {/* Past Demonstrations — Responsive Table on Desktop, Cards on Mobile */}
      {past.length > 0 && (
        <section aria-label="Past demonstrations">
          <h2 className="text-xs font-black uppercase tracking-wider text-muted-foreground mb-3">
            Past Demonstrations ({past.length})
          </h2>

          <div className="border border-border bg-card shadow-[var(--shadow-sm)] overflow-hidden">
            {/* Desktop Table Header */}
            <div className="hidden sm:grid sm:grid-cols-[1fr_200px_160px] gap-4 border-b border-border bg-muted/50 px-5 py-3">
              <span className="text-[10px] font-black uppercase tracking-wider text-muted-foreground">
                Robot Model
              </span>
              <span className="text-[10px] font-black uppercase tracking-wider text-muted-foreground">
                Date &amp; Time
              </span>
              <span className="text-[10px] font-black uppercase tracking-wider text-muted-foreground">
                Status
              </span>
            </div>

            {/* Rows (Mobile: Stacked cards | Desktop: 3-col grid) */}
            <div className="divide-y divide-border">
              {past.map((demo) => {
                const cfg = STATUS_CONFIG[demo.status] ?? STATUS_CONFIG.cancelled
                return (
                  <div
                    key={demo.id}
                    className="p-4 sm:px-5 sm:py-3.5 sm:grid sm:grid-cols-[1fr_200px_160px] sm:items-center sm:gap-4 flex flex-col gap-2"
                  >
                    <div>
                      <p className="text-sm font-bold text-foreground">
                        {demo.property_name || "Robot Unit"}
                      </p>
                      {demo.property_environment && (
                        <p className="text-[11px] text-muted-foreground sm:hidden">
                          {demo.property_environment}
                        </p>
                      )}
                    </div>

                    <div className="text-xs text-muted-foreground">
                      <span className="sm:hidden font-bold text-[10px] uppercase text-muted-foreground mr-1">
                        Date:
                      </span>
                      {formatDate(demo.scheduled_at)}
                    </div>

                    <div>
                      <span
                        className={`inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-black uppercase tracking-wider ${cfg.className}`}
                      >
                        {cfg.icon}
                        {cfg.label}
                      </span>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </section>
      )}
    </div>
  )
}

// Backwards-compatible alias export
export const ViewingsTab = DemosTab
