"use client"

import { useEffect, useState, useCallback } from "react"
import {
  ArrowRight, Bot, CalendarCheck2, CalendarClock, CalendarPlus,
  CheckCircle2, Clock, RefreshCw, X, XCircle,
} from "lucide-react"
import type { Viewing } from "@/lib/portal-types"
import { fetchMyViewings, requestDemo } from "@/lib/portal-api"
import { useToast } from "@/hooks/use-toast"
import { Skeleton } from "@/components/ui/skeleton"

// ─── Status config ────────────────────────────────────────────────────────────

const STATUS_CONFIG: Record<string, {
  label: string
  icon: React.ReactNode
  className: string
}> = {
  requested: {
    label: "Awaiting confirmation",
    icon: <Clock className="h-3.5 w-3.5" />,
    className: "bg-amber-50 border border-amber-200 text-amber-700",
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
  if (!s) return "Date TBC"
  return new Date(s).toLocaleDateString("en-MY", {
    weekday: "long", day: "numeric", month: "long", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  })
}

// ─── New demo request modal ───────────────────────────────────────────────────

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
  const [propertyHint, setPropertyHint] = useState("")
  const [preferredDate, setPreferredDate] = useState("")
  const [notes, setNotes]   = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError]   = useState<string | null>(null)

  // We can't look up property_id from a name here — the Viewings tab doesn't
  // load the full matches list. The user just picks a date/note; the agent
  // picks the unit. So we need a property_id.  For the general "request a new
  // demo from the Viewings tab" use-case, we send a general inquiry instead.
  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!propertyHint.trim() && !preferredDate && !notes.trim()) return
    setLoading(true); setError(null)

    // Build a free-text inquiry since we don't have a specific property_id here
    const message = [
      propertyHint ? `Unit of interest: ${propertyHint}` : null,
      preferredDate ? `Preferred date/time: ${new Date(preferredDate).toLocaleString("en-MY")}` : null,
      notes ? `Notes: ${notes}` : null,
      "Please contact me to arrange a demonstration.",
    ].filter(Boolean).join("\n")

    try {
      const res = await fetch(`/api/portal/${clientId}/inquiry`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          property_id: "00000000-0000-0000-0000-000000000000", // general inquiry sentinel
          message,
        }),
      })
      if (!res.ok) {
        const d = await res.json()
        setError(d.error ?? "Failed to submit request.")
        return
      }
      toast({ title: "Request sent!", description: "A representative will be in touch shortly." })
      onSuccess()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Connection error.")
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
              <CalendarPlus className="h-3 w-3" strokeWidth={3} /> Request New Demo
            </span>
            <h2 className="text-lg font-bold tracking-tight">Book a demonstration</h2>
            <p className="text-sm text-muted-foreground mt-0.5">
              Tell us which unit and when you'd like to see it. We&apos;ll confirm within 24 hours.
            </p>
          </div>
          <button onClick={onClose} className="shrink-0 border border-border p-1.5 text-muted-foreground hover:bg-muted transition-colors">
            <X className="h-4 w-4" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="flex flex-col gap-5 px-6 py-5">
          <label className="flex flex-col gap-2">
            <span className="text-xs font-black uppercase tracking-wider">Unit of interest (optional)</span>
            <input type="text" value={propertyHint} onChange={e => setPropertyHint(e.target.value)}
              placeholder="e.g. SCOUT-300 Patrol Unit or leave blank for agent to recommend"
              className="border border-border bg-white px-3 py-2.5 text-sm text-black placeholder:text-muted-foreground focus:outline-none focus-visible:border-primary" />
          </label>
          <label className="flex flex-col gap-2">
            <span className="text-xs font-black uppercase tracking-wider">Preferred date &amp; time (optional)</span>
            <input type="datetime-local" value={preferredDate} onChange={e => setPreferredDate(e.target.value)}
              className="border border-border bg-white px-3 py-2.5 text-sm text-black focus:outline-none focus-visible:border-primary" />
          </label>
          <label className="flex flex-col gap-2">
            <span className="text-xs font-black uppercase tracking-wider">Additional notes (optional)</span>
            <textarea value={notes} onChange={e => setNotes(e.target.value)}
              placeholder="Any requirements, questions, or constraints…"
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
              {loading ? "Submitting…" : "Submit request"}
              {!loading && <ArrowRight className="h-4 w-4 text-primary transition-transform group-hover:translate-x-0.5" strokeWidth={3} />}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ─── Viewings Tab ─────────────────────────────────────────────────────────────

export function ViewingsTab({ clientId }: { clientId: string }) {
  const { toast } = useToast()
  const [viewings, setViewings] = useState<Viewing[]>([])
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState<string | null>(null)
  const [showNewDemo, setShowNewDemo] = useState(false)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const d = await fetchMyViewings(clientId)
      setViewings(d.viewings)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load viewings.")
    } finally {
      setLoading(false)
    }
  }, [clientId])

  useEffect(() => { load() }, [load])

  const upcoming = viewings.filter(v => v.status === "upcoming" || v.status === "requested")
  const past     = viewings.filter(v => v.status === "completed" || v.status === "cancelled")

  if (loading) {
    return (
      <div className="mx-auto max-w-4xl px-4 sm:px-6 py-10 flex flex-col gap-6">
        <Skeleton className="h-8 w-48" />
        {[...Array(3)].map((_, i) => <Skeleton key={i} className="h-24" />)}
      </div>
    )
  }

  if (error) {
    return (
      <div className="mx-auto max-w-4xl px-4 sm:px-6 py-10">
        <div className="border border-border bg-card p-8 text-center shadow-[var(--shadow-sm)]">
          <XCircle className="mx-auto h-6 w-6 text-destructive mb-2" />
          <p className="text-sm font-semibold text-destructive mb-4">{error}</p>
          <button onClick={load}
            className="border border-border bg-black px-4 py-2 text-xs font-black uppercase tracking-wider text-white hover:shadow-[var(--shadow-sm)] transition-shadow">
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
          onSuccess={() => { setShowNewDemo(false); load() }}
        />
      )}

      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-[10px] font-black uppercase tracking-wider text-muted-foreground flex items-center gap-2">
          <CalendarClock className="h-3.5 w-3.5" />
          Your demonstrations
        </h1>
        <button
          id="request-new-demo-btn"
          onClick={() => setShowNewDemo(true)}
          className="group flex items-center gap-2 border border-border bg-black px-4 py-2 text-xs font-black uppercase tracking-wider text-white hover:shadow-[var(--shadow-sm)] transition-shadow"
        >
          <CalendarPlus className="h-3.5 w-3.5 text-primary" strokeWidth={3} />
          Request new demo
        </button>
      </div>

      {/* Upcoming / requested */}
      <section aria-label="Upcoming demos">
        <h2 className="text-xs font-black uppercase tracking-wider text-muted-foreground mb-3">
          Upcoming ({upcoming.length})
        </h2>
        {upcoming.length === 0 ? (
          <div className="border border-border bg-card p-8 text-center">
            <Bot className="mx-auto h-6 w-6 text-muted-foreground opacity-40 mb-2" />
            <p className="text-sm text-muted-foreground">No upcoming demos yet.</p>
            <button onClick={() => setShowNewDemo(true)}
              className="mt-4 border border-border bg-black px-4 py-2 text-xs font-black uppercase tracking-wider text-white hover:shadow-[var(--shadow-sm)] transition-shadow">
              Request one now
            </button>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            {upcoming.map(v => {
              const cfg = STATUS_CONFIG[v.status] ?? STATUS_CONFIG.requested
              const isRequested = v.status === "requested"
              return (
                <div key={v.id} className="border border-border bg-card shadow-[var(--shadow-sm)] p-5 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                  <div className="flex flex-col gap-1.5">
                    <p className="font-bold text-sm leading-snug">{v.property_name ?? "Unit TBC"}</p>
                    {v.property_environment && (
                      <p className="text-xs text-muted-foreground">{v.property_environment}</p>
                    )}
                    <p className="text-xs text-muted-foreground">{formatDate(v.scheduled_at)}</p>
                  </div>
                  <div className="flex items-center gap-3 flex-wrap">
                    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-[10px] font-black uppercase tracking-wider ${cfg.className}`}>
                      {cfg.icon}{cfg.label}
                    </span>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </section>

      {/* Past */}
      {past.length > 0 && (
        <section aria-label="Past demos">
          <h2 className="text-xs font-black uppercase tracking-wider text-muted-foreground mb-3">
            Past ({past.length})
          </h2>
          <div className="border border-border bg-card shadow-[var(--shadow-sm)] overflow-hidden">
            <div className="grid grid-cols-[1fr_180px_160px] gap-4 border-b border-border bg-muted/50 px-5 py-3">
              <span className="text-[10px] font-black uppercase tracking-wider text-muted-foreground">Unit</span>
              <span className="text-[10px] font-black uppercase tracking-wider text-muted-foreground">Date</span>
              <span className="text-[10px] font-black uppercase tracking-wider text-muted-foreground">Status</span>
            </div>
            {past.map((v, i) => {
              const cfg = STATUS_CONFIG[v.status] ?? STATUS_CONFIG.cancelled
              return (
                <div key={v.id} className={`grid grid-cols-[1fr_180px_160px] gap-4 items-center px-5 py-4 ${i < past.length - 1 ? "border-b border-border" : ""}`}>
                  <p className="text-sm font-semibold leading-snug">{v.property_name ?? "Unit"}</p>
                  <p className="text-xs text-muted-foreground">{formatDate(v.scheduled_at)}</p>
                  <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-[10px] font-black uppercase tracking-wider ${cfg.className}`}>
                    {cfg.icon}{cfg.label}
                  </span>
                </div>
              )
            })}
          </div>
        </section>
      )}
    </div>
  )
}
