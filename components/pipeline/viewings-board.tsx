"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import {
  ArrowRight,
  CalendarCheck,
  CalendarClock,
  CalendarX,
  CheckCircle2,
  Loader2,
  RefreshCw,
  Users,
  X,
  XCircle,
} from "lucide-react"
import { TIER_SHORT, type DeduplicatedClient } from "@/lib/pipeline-data"
import {
  cancelViewing,
  completeViewing,
  fetchScheduledViewings,
  type ScheduledViewing,
} from "@/lib/schedule-viewing"

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatDateTime(iso: string) {
  try {
    return new Date(iso).toLocaleString("en-MY", { dateStyle: "medium", timeStyle: "short" })
  } catch {
    return iso
  }
}

// ─── Tier badge ───────────────────────────────────────────────────────────────

type Tier = DeduplicatedClient["tier"]

const TIER_STYLES: Record<Tier, string> = {
  TIER_1: "bg-primary text-black border-black",
  TIER_2: "bg-black text-white border-black",
  TIER_3: "bg-white text-black border-black",
}

function TierBadge({ tier }: { tier: Tier | undefined }) {
  if (!tier) return null
  return (
    <span className={`inline-block border-2 px-2 py-0.5 text-[10px] font-black uppercase tracking-wider ${TIER_STYLES[tier]}`}>
      {TIER_SHORT[tier]}
    </span>
  )
}

// ─── Column header ────────────────────────────────────────────────────────────

function ColumnHeader({
  label,
  count,
  accent,
  icon,
}: {
  label: string
  count: number
  accent: string
  icon: React.ReactNode
}) {
  return (
    <div className={`flex items-center justify-between border-b border-neutral-200 px-4 py-3 ${accent}`}>
      <div className="flex items-center gap-2">
        {icon}
        <span className="text-xs font-black uppercase tracking-widest">
          {label} — {count}
        </span>
      </div>
      <span className="flex h-6 w-6 items-center justify-center border border-neutral-200 bg-white font-mono text-xs font-black text-black">
        {count}
      </span>
    </div>
  )
}

// ─── Viewing card ─────────────────────────────────────────────────────────────

function ViewingCard({
  viewing,
  dedupClients,
  onComplete,
  onCancel,
  completing,
  cancelling,
}: {
  viewing: ScheduledViewing
  dedupClients: DeduplicatedClient[]
  onComplete?: (id: string) => void
  onCancel?: (id: string) => void
  completing?: boolean
  cancelling?: boolean
}) {
  const client = viewing.clients
  const property = viewing.properties
  const tier = dedupClients.find((c) => c.clientId === viewing.client_id)?.tier

  const isMissedOrAuto =
    viewing.cancellation_reason === "auto_missed" ||
    (viewing.scheduled_at && new Date(viewing.scheduled_at).getTime() < Date.now() - 24 * 3600 * 1000)

  return (
    <div className="border border-neutral-200 bg-white shadow-[0px_2px_8px_rgba(0,0,0,0.08)]">
      {/* Card header */}
      <div className="flex items-start justify-between gap-2 border-b border-neutral-200/20 px-4 py-3">
        <div>
          <div className="text-sm font-black leading-tight">{client?.name ?? viewing.client_id}</div>
          <div className="mt-0.5 font-mono text-[10px] text-muted-foreground">
            {property?.address ?? viewing.property_id}
          </div>
        </div>
        <TierBadge tier={tier} />
      </div>

      {/* Card body */}
      {viewing.scheduled_at && (
        <div className="flex items-center gap-2 px-4 py-2.5">
          <CalendarClock className="h-3.5 w-3.5 shrink-0 text-muted-foreground" strokeWidth={2.5} />
          <span className="font-mono text-[11px] font-bold text-muted-foreground">
            {formatDateTime(viewing.scheduled_at)}
          </span>
        </div>
      )}

      {/* Action buttons (Scheduled column only) */}
      {viewing.status === "upcoming" && (onComplete || onCancel) && (
        <div className="flex items-center gap-2 border-t-2 border-black/20 p-3">
          {onComplete && (
            <button
              type="button"
              disabled={completing || cancelling}
              onClick={() => onComplete(viewing.id)}
              className="flex flex-1 items-center justify-center gap-1.5 border border-neutral-200 bg-black py-1.5 text-[10px] font-black uppercase tracking-wider text-white shadow-[0px_1px_4px_rgba(0,0,0,0.07)] transition-all hover:shadow-[0px_2px_8px_rgba(0,0,0,0.08)] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {completing ? (
                <Loader2 className="h-3 w-3 animate-spin text-primary" strokeWidth={2.5} />
              ) : (
                <CheckCircle2 className="h-3 w-3 text-primary" strokeWidth={2.5} />
              )}
              {completing ? "Completing…" : "Complete"}
            </button>
          )}
          {onCancel && (
            <button
              type="button"
              disabled={completing || cancelling}
              onClick={() => onCancel(viewing.id)}
              className="flex items-center justify-center gap-1.5 border border-neutral-200 bg-white px-3 py-1.5 text-[10px] font-black uppercase tracking-wider text-red-600 shadow-[0px_1px_4px_rgba(0,0,0,0.07)] transition-all hover:bg-red-50 hover:shadow-[0px_2px_8px_rgba(0,0,0,0.08)] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {cancelling ? (
                <Loader2 className="h-3 w-3 animate-spin text-red-600" strokeWidth={2.5} />
              ) : (
                <XCircle className="h-3 w-3 text-red-600" strokeWidth={2.5} />
              )}
              {cancelling ? "Cancelling…" : "Cancel"}
            </button>
          )}
        </div>
      )}

      {/* Cancellation Tag (Cancelled column only) */}
      {viewing.status === "cancelled" && (
        <div className="border-t-2 border-black/20 bg-muted/20 px-4 py-2">
          {isMissedOrAuto ? (
            <span className="inline-block border-2 border-red-600 bg-red-100 px-2 py-0.5 font-mono text-[10px] font-black uppercase tracking-wider text-red-700">
              Missed / Auto-cancelled
            </span>
          ) : (
            <span className="inline-block border border-neutral-200 bg-muted px-2 py-0.5 font-mono text-[10px] font-black uppercase tracking-wider text-black">
              Cancelled by agent
            </span>
          )}
        </div>
      )}
    </div>
  )
}

// ─── Completion toast ──────────────────────────────────────────────────────────

interface CompletionToast {
  clientName: string
  probability: number
  tier: string
}

// ─── Main component ───────────────────────────────────────────────────────────

interface ViewingsBoardProps {
  dedupClients: DeduplicatedClient[]
  onNavigateToClients?: () => void
}

export function ViewingsBoard({ dedupClients, onNavigateToClients }: ViewingsBoardProps) {
  const [viewings, setViewings]     = useState<ScheduledViewing[]>([])
  const [loading, setLoading]       = useState(true)
  const [error, setError]           = useState<string | null>(null)
  const [completing, setCompleting] = useState<string | null>(null)   // viewing id being completed
  const [cancelling, setCancelling] = useState<string | null>(null)   // viewing id being cancelled
  const [toast, setToast]           = useState<CompletionToast | null>(null)
  const toastTimerRef               = useRef<ReturnType<typeof setTimeout> | null>(null)

  const loadViewings = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchScheduledViewings()
      setViewings(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load viewings")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadViewings()
  }, [loadViewings])

  const handleComplete = async (viewingId: string) => {
    setCompleting(viewingId)
    try {
      const result = await completeViewing(viewingId)
      // Update the local viewing to status=completed
      setViewings((prev) =>
        prev.map((v) => v.id === viewingId ? { ...v, status: "completed" } : v)
      )
      if (toastTimerRef.current) clearTimeout(toastTimerRef.current)
      const t: CompletionToast = {
        clientName: result.clientName,
        probability: result.probability,
        tier: result.tier.replace("_", " "),
      }
      setToast(t)
      toastTimerRef.current = setTimeout(() => setToast(null), 7000)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to complete viewing")
    } finally {
      setCompleting(null)
    }
  }

  const handleCancel = async (viewingId: string) => {
    setCancelling(viewingId)
    try {
      await cancelViewing(viewingId, "agent")
      setViewings((prev) =>
        prev.map((v) =>
          v.id === viewingId
            ? { ...v, status: "cancelled", cancellation_reason: "agent" }
            : v
        )
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to cancel viewing")
    } finally {
      setCancelling(null)
    }
  }

  // ── Compute counts and status columns ────────────────────────────────────

  const clientIdsWithAnyViewing = new Set(viewings.map((v) => v.client_id))

  // Matched count: VIP (TIER_1) and WARM (TIER_2) clients without a scheduled_viewings row
  const matchedCount = dedupClients.filter(
    (c) =>
      (c.tier === "TIER_1" || c.tier === "TIER_2") &&
      !clientIdsWithAnyViewing.has(c.clientId)
  ).length

  // Scheduled: upcoming status (VIP & WARM clients)
  const scheduledViewings = viewings.filter((v) => {
    if (v.status !== "upcoming") return false
    const tier = dedupClients.find((c) => c.clientId === v.client_id)?.tier
    return tier === "TIER_1" || tier === "TIER_2"
  })

  // Completed: completed status (VIP & WARM clients)
  const completedViewings = viewings.filter((v) => {
    if (v.status !== "completed") return false
    const tier = dedupClients.find((c) => c.clientId === v.client_id)?.tier
    return tier === "TIER_1" || tier === "TIER_2"
  })

  // Cancelled: cancelled status (VIP & WARM clients)
  const cancelledViewings = viewings.filter((v) => {
    if (v.status !== "cancelled") return false
    const tier = dedupClients.find((c) => c.clientId === v.client_id)?.tier
    return tier === "TIER_1" || tier === "TIER_2"
  })

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 border border-neutral-200 bg-white py-24 shadow-[0px_4px_16px_rgba(0,0,0,0.10)]">
        <Loader2 className="h-8 w-8 animate-spin text-black" strokeWidth={2.5} />
        <p className="text-xs font-black uppercase tracking-wider text-muted-foreground">Loading viewings…</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      {/* Completion toast */}
      {toast && (
        <div className="flex items-center gap-3 border border-neutral-200 bg-primary px-5 py-4 shadow-[0px_2px_8px_rgba(0,0,0,0.08)]">
          <CheckCircle2 className="h-5 w-5 shrink-0 text-black" strokeWidth={2.5} />
          <p className="flex-1 text-sm font-black text-black">
            Viewing completed.{" "}
            <span className="font-mono">{toast.clientName}&apos;s</span> P(Buy) updated to{" "}
            <span className="font-mono">{Math.round(toast.probability * 100)}%</span>
            {" — "}{toast.tier}
          </p>
          <button
            type="button"
            onClick={() => setToast(null)}
            className="shrink-0 border border-neutral-200 p-1 text-black hover:bg-black hover:text-primary"
            aria-label="Dismiss"
          >
            <X className="h-4 w-4" strokeWidth={2.5} />
          </button>
        </div>
      )}

      {error && (
        <div className="border border-neutral-200 bg-white p-4">
          <span className="text-xs font-black uppercase tracking-wider text-red-600">{error}</span>
        </div>
      )}

      {/* Header banner & Refresh control */}
      <div className="flex items-center justify-between">
        <div className="text-[10px] font-black uppercase tracking-widest text-muted-foreground">
          Viewings Pipeline Board
        </div>
        <button
          type="button"
          onClick={loadViewings}
          className="flex items-center gap-2 border border-neutral-200 bg-white px-3 py-1.5 text-xs font-black uppercase tracking-wider shadow-[0px_1px_4px_rgba(0,0,0,0.07)] transition-transform"
        >
          <RefreshCw className="h-3.5 w-3.5" strokeWidth={2.5} />
          Refresh
        </button>
      </div>

      {/* Compact summary bar for Matched clients */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border border-neutral-200 bg-white p-4 shadow-[0px_2px_8px_rgba(0,0,0,0.08)]">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center border border-neutral-200 bg-primary">
            <Users className="h-5 w-5 text-black" strokeWidth={2.5} />
          </div>
          <div>
            <div className="text-sm font-black uppercase tracking-wider">
              <span className="font-mono text-base font-black">{matchedCount}</span> VIP/WARM clients ready to schedule
            </div>
            <div className="text-[11px] font-bold text-muted-foreground">
              Qualified clients matching properties without active scheduled viewings
            </div>
          </div>
        </div>
        {onNavigateToClients && (
          <button
            type="button"
            onClick={onNavigateToClients}
            className="flex items-center gap-2 border border-neutral-200 bg-black px-4 py-2 text-xs font-black uppercase tracking-wider text-white shadow-[0px_1px_4px_rgba(0,0,0,0.07)] transition-all hover:shadow-[0px_2px_8px_rgba(0,0,0,0.08)]"
          >
            Go to Clients <ArrowRight className="h-4 w-4 text-primary" strokeWidth={2.5} />
          </button>
        )}
      </div>

      {/* Three status-based Kanban columns */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">

        {/* Column 1 — Scheduled */}
        <div className="border border-neutral-200 shadow-[0px_2px_8px_rgba(0,0,0,0.08)]">
          <ColumnHeader
            label="Scheduled"
            count={scheduledViewings.length}
            accent="bg-black text-white"
            icon={<CalendarClock className="h-4 w-4 text-white" strokeWidth={2.5} />}
          />
          <div className="flex flex-col gap-3 p-3 max-h-[750px] overflow-y-auto scrollbar-none">
            {scheduledViewings.length === 0 ? (
              <p className="py-6 text-center text-[11px] font-bold text-muted-foreground">
                No upcoming viewings scheduled
              </p>
            ) : (
              scheduledViewings.map((v) => (
                <ViewingCard
                  key={v.id}
                  viewing={v}
                  dedupClients={dedupClients}
                  onComplete={handleComplete}
                  onCancel={handleCancel}
                  completing={completing === v.id}
                  cancelling={cancelling === v.id}
                />
              ))
            )}
          </div>
        </div>

        {/* Column 2 — Completed */}
        <div className="border border-neutral-200 shadow-[0px_2px_8px_rgba(0,0,0,0.08)]">
          <ColumnHeader
            label="Completed"
            count={completedViewings.length}
            accent="bg-primary"
            icon={<CalendarCheck className="h-4 w-4" strokeWidth={2.5} />}
          />
          <div className="flex flex-col gap-3 p-3 max-h-[750px] overflow-y-auto scrollbar-none">
            {completedViewings.length === 0 ? (
              <p className="py-6 text-center text-[11px] font-bold text-muted-foreground">
                No completed viewings yet
              </p>
            ) : (
              completedViewings.map((v) => (
                <ViewingCard
                  key={v.id}
                  viewing={v}
                  dedupClients={dedupClients}
                />
              ))
            )}
          </div>
        </div>

        {/* Column 3 — Cancelled */}
        <div className="border border-neutral-200 shadow-[0px_2px_8px_rgba(0,0,0,0.08)]">
          <ColumnHeader
            label="Cancelled"
            count={cancelledViewings.length}
            accent="bg-muted text-black"
            icon={<CalendarX className="h-4 w-4" strokeWidth={2.5} />}
          />
          <div className="flex flex-col gap-3 p-3 max-h-[750px] overflow-y-auto scrollbar-none">
            {cancelledViewings.length === 0 ? (
              <p className="py-6 text-center text-[11px] font-bold text-muted-foreground">
                No cancelled viewings
              </p>
            ) : (
              cancelledViewings.map((v) => (
                <ViewingCard
                  key={v.id}
                  viewing={v}
                  dedupClients={dedupClients}
                />
              ))
            )}
          </div>
        </div>

      </div>
    </div>
  )
}
