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
  Bell,
} from "lucide-react"
import { TIER_SHORT, type DeduplicatedClient } from "@/lib/pipeline-data"
import {
  cancelViewing,
  completeViewing,
  fetchScheduledViewings,
  type ScheduledViewing,
} from "@/lib/schedule-viewing"

async function confirmViewing(viewingId: string): Promise<void> {
  const res = await fetch(`/api/confirm_demo/${viewingId}`, { method: "PATCH" })
  if (!res.ok) {
    const d = await res.json().catch(() => ({}))
    throw new Error(d.error ?? "Failed to confirm demo")
  }
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatDateTime(iso: string | null) {
  if (!iso) return "TBC"
  try {
    return new Date(iso).toLocaleString("en-MY", { dateStyle: "medium", timeStyle: "short" })
  } catch {
    return iso
  }
}

// ─── Tier badge ───────────────────────────────────────────────────────────────

type Tier = DeduplicatedClient["tier"]

const TIER_STYLES: Record<Tier, string> = {
  TIER_1: "bg-primary text-black border-primary",
  TIER_2: "bg-black text-white border-black",
  TIER_3: "bg-muted text-foreground border-border",
}

function TierBadge({ tier }: { tier: Tier | undefined }) {
  if (!tier) return null
  return (
    <span className={`inline-block rounded-[6px] border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${TIER_STYLES[tier]}`}>
      {TIER_SHORT[tier]}
    </span>
  )
}

// ─── Column header ────────────────────────────────────────────────────────────

function ColumnHeader({
  label,
  count,
  dotColor,
  icon,
}: {
  label: string
  count: number
  dotColor: string
  icon: React.ReactNode
}) {
  return (
    <div className="flex items-center justify-between border-b border-border bg-transparent px-5 py-3.5">
      <div className="flex items-center gap-2 text-foreground">
        <span className="h-2.5 w-2.5 rounded-full shrink-0" style={{ background: dotColor }} />
        {icon}
        <span className="text-xs font-bold uppercase tracking-wider text-foreground sm:text-sm">
          {label}
        </span>
      </div>
      <span className="flex h-6 min-w-6 items-center justify-center rounded-[var(--radius-sm)] border border-border bg-muted px-1.5 font-mono text-xs font-bold text-muted-foreground">
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
  onConfirm,
  completing,
  cancelling,
  confirming,
}: {
  viewing: ScheduledViewing
  dedupClients: DeduplicatedClient[]
  onComplete?: (id: string) => void
  onCancel?: (id: string) => void
  onConfirm?: (id: string) => void
  completing?: boolean
  cancelling?: boolean
  confirming?: boolean
}) {
  const client = viewing.clients
  const property = viewing.properties
  const tier = dedupClients.find((c) => c.clientId === viewing.client_id)?.tier

  const isMissedOrAuto =
    viewing.cancellation_reason === "auto_missed" ||
    (viewing.scheduled_at && new Date(viewing.scheduled_at).getTime() < Date.now() - 24 * 3600 * 1000)

  const isRequested = viewing.status === "requested"

  return (
    <div className="rounded-[8px] border border-border bg-card shadow-[var(--shadow-xs)] hover:shadow-[var(--shadow-sm)] transition-shadow duration-150">
      {/* Client-requested amber banner */}
      {isRequested && (
        <div className="flex items-center gap-2 border-b border-amber-200/40 bg-amber-50/80 px-4 py-2">
          <Bell className="h-3 w-3 shrink-0 text-amber-600" strokeWidth={2.5} />
          <span className="text-[10px] font-bold uppercase tracking-wider text-amber-700">
            Client Request — Needs Confirmation
          </span>
        </div>
      )}

      {/* Card header */}
      <div className="flex items-start justify-between gap-2 border-b border-border/60 px-4 py-3">
        <div>
          <div className="text-sm font-bold leading-tight text-foreground">{client?.name ?? viewing.client_id}</div>
          <div className="mt-0.5 font-mono text-[10px] text-muted-foreground">
            {property?.address ?? viewing.property_id}
          </div>
        </div>
        <TierBadge tier={tier} />
      </div>

      {/* Card body */}
      {viewing.scheduled_at ? (
        <div className="flex items-center gap-2 px-4 py-2.5">
          <CalendarClock className="h-3.5 w-3.5 shrink-0 text-muted-foreground" strokeWidth={2} />
          <span className="font-mono text-[11px] font-semibold text-muted-foreground">
            {formatDateTime(viewing.scheduled_at)}
          </span>
        </div>
      ) : isRequested ? (
        <div className="flex items-center gap-2 px-4 py-2.5">
          <CalendarClock className="h-3.5 w-3.5 shrink-0 text-amber-400" strokeWidth={2} />
          <span className="font-mono text-[11px] font-semibold text-amber-500">No date set — awaiting agent confirmation</span>
        </div>
      ) : null}

      {/* Confirmation State Badge */}
      <div className="px-4 pb-2.5 flex items-center gap-1.5 flex-wrap">
        {viewing.confirmation_status === "confirmed" || viewing.client_confirmed_at ? (
          <span className="inline-flex items-center gap-1 rounded-[6px] border border-emerald-500/30 bg-emerald-50 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400">
            <CheckCircle2 className="h-3 w-3 text-emerald-600 dark:text-emerald-400" />
            Confirmed by client
          </span>
        ) : viewing.status === "upcoming" ? (
          <span className="inline-flex items-center gap-1 rounded-[6px] border border-neutral-300/70 bg-neutral-100 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-neutral-600 dark:border-neutral-800 dark:bg-neutral-900 dark:text-neutral-400">
            <span className="h-1.5 w-1.5 rounded-full bg-amber-500 animate-pulse" />
            Scheduled (Unconfirmed)
          </span>
        ) : null}
      </div>

      {/* Confirm button (client-requested demos) */}
      {isRequested && onConfirm && (
        <div className="flex items-center gap-2 border-t border-amber-200/30 bg-amber-50/40 p-3">
          <button
            type="button"
            disabled={confirming || cancelling}
            onClick={() => onConfirm(viewing.id)}
            className="flex flex-1 items-center justify-center gap-1.5 rounded-[6px] border border-amber-300/60 bg-amber-400 py-1.5 text-xs font-bold uppercase tracking-wider text-black shadow-[var(--shadow-xs)] transition-all hover:bg-amber-300 hover:shadow-[var(--shadow-sm)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {confirming ? (
              <Loader2 className="h-3 w-3 animate-spin" strokeWidth={2.5} />
            ) : (
              <CheckCircle2 className="h-3.5 w-3.5" strokeWidth={2.5} />
            )}
            {confirming ? "Confirming…" : "Confirm demo"}
          </button>
          {onCancel && (
            <button
              type="button"
              disabled={confirming || cancelling}
              onClick={() => onCancel(viewing.id)}
              className="flex items-center justify-center gap-1.5 rounded-[6px] border border-border bg-muted px-3 py-1.5 text-xs font-bold uppercase tracking-wider text-muted-foreground shadow-[var(--shadow-xs)] transition-all hover:bg-muted/80 hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
            >
              {cancelling ? (
                <Loader2 className="h-3 w-3 animate-spin" strokeWidth={2.5} />
              ) : (
                <XCircle className="h-3.5 w-3.5" strokeWidth={2} />
              )}
              {cancelling ? "Cancelling…" : "Cancel"}
            </button>
          )}
        </div>
      )}

      {/* Action buttons (Scheduled/upcoming column only) */}
      {viewing.status === "upcoming" && (onComplete || onCancel) && (
        <div className="flex items-center gap-2 border-t border-border p-3">
          {onComplete && (
            <button
              type="button"
              disabled={completing || cancelling}
              onClick={() => onComplete(viewing.id)}
              className="flex flex-1 items-center justify-center gap-1.5 rounded-[6px] border border-border bg-black py-1.5 text-xs font-bold uppercase tracking-wider text-white shadow-[var(--shadow-xs)] transition-all hover:bg-neutral-800 hover:shadow-[var(--shadow-sm)] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {completing ? (
                <Loader2 className="h-3 w-3 animate-spin text-primary" strokeWidth={2.5} />
              ) : (
                <CheckCircle2 className="h-3.5 w-3.5 text-primary" strokeWidth={2.5} />
              )}
              {completing ? "Completing…" : "Complete"}
            </button>
          )}
          {onCancel && (
            <button
              type="button"
              disabled={completing || cancelling}
              onClick={() => onCancel(viewing.id)}
              className="flex items-center justify-center gap-1.5 rounded-[6px] border border-border bg-muted px-3 py-1.5 text-xs font-bold uppercase tracking-wider text-muted-foreground shadow-[var(--shadow-xs)] transition-all hover:bg-muted/80 hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
            >
              {cancelling ? (
                <Loader2 className="h-3 w-3 animate-spin" strokeWidth={2.5} />
              ) : (
                <XCircle className="h-3.5 w-3.5" strokeWidth={2} />
              )}
              {cancelling ? "Cancelling…" : "Cancel"}
            </button>
          )}
        </div>
      )}

      {/* Cancellation Tag (Cancelled column only) */}
      {viewing.status === "cancelled" && (
        <div className="border-t border-border bg-muted/20 px-4 py-2.5">
          {viewing.confirmation_status === "rescheduled" ? (
            <span className="inline-block rounded-[var(--radius-sm)] border border-amber-300 bg-amber-50 px-2.5 py-0.5 font-mono text-[10px] font-bold uppercase tracking-wider text-amber-700 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-400">
              Rescheduled by client
            </span>
          ) : viewing.confirmation_status === "cancelled_by_client" || viewing.cancellation_reason?.toLowerCase().includes("client") ? (
            <span className="inline-block rounded-[var(--radius-sm)] border border-rose-300 bg-rose-50 px-2.5 py-0.5 font-mono text-[10px] font-bold uppercase tracking-wider text-rose-700 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-400">
              Cancelled by client
            </span>
          ) : isMissedOrAuto ? (
            <span className="inline-block rounded-[var(--radius-sm)] border border-border bg-muted px-2.5 py-0.5 font-mono text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
              Missed / Auto-cancelled
            </span>
          ) : (
            <span className="inline-block rounded-[var(--radius-sm)] border border-border bg-muted px-2.5 py-0.5 font-mono text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
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
  const [confirming, setConfirming] = useState<string | null>(null)   // viewing id being confirmed
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

  const handleConfirm = async (viewingId: string) => {
    setConfirming(viewingId)
    try {
      await confirmViewing(viewingId)
      setViewings((prev) =>
        prev.map((v) => v.id === viewingId ? { ...v, status: "upcoming" } : v)
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to confirm demo")
    } finally {
      setConfirming(null)
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

  // Scheduled: upcoming OR client-requested status (VIP & WARM clients)
  const scheduledViewings = viewings.filter((v) => {
    if (v.status !== "upcoming" && v.status !== "requested") return false
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
        <div className="flex items-center gap-3 rounded-[var(--radius)] border border-primary/40 bg-primary/15 px-5 py-4 shadow-[var(--shadow-sm)]">
          <CheckCircle2 className="h-5 w-5 shrink-0 text-black" strokeWidth={2.5} />
          <p className="flex-1 text-sm font-bold text-foreground">
            Viewing completed.{" "}
            <span className="font-mono">{toast.clientName}&apos;s</span> P(Buy) updated to{" "}
            <span className="font-mono font-bold">{Math.round(toast.probability * 100)}%</span>
            {" — "}{toast.tier}
          </p>
          <button
            type="button"
            onClick={() => setToast(null)}
            className="shrink-0 rounded-[var(--radius-sm)] border border-border p-1 text-foreground hover:bg-muted"
            aria-label="Dismiss"
          >
            <X className="h-4 w-4" strokeWidth={2.5} />
          </button>
        </div>
      )}

      {error && (
        <div className="rounded-[var(--radius)] border border-border bg-muted/40 p-4">
          <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">{error}</span>
        </div>
      )}

      {/* Header banner & Refresh control */}
      <div className="flex items-center justify-between">
        <div className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
          Demos Pipeline Board
        </div>
        <button
          type="button"
          onClick={loadViewings}
          className="flex items-center gap-2 rounded-[var(--radius-sm)] border border-border bg-card px-3 py-1.5 text-xs font-bold uppercase tracking-wider shadow-[var(--shadow-xs)] transition-all hover:bg-muted hover:shadow-[var(--shadow-sm)]"
        >
          <RefreshCw className="h-3.5 w-3.5" strokeWidth={2.5} />
          Refresh
        </button>
      </div>

      {/* Compact summary bar for Matched clients */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 rounded-[10px] border border-border bg-card p-4 sm:p-5 shadow-[var(--shadow-sm)]">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[8px] bg-primary">
            <Users className="h-5 w-5 text-black" strokeWidth={2.5} />
          </div>
          <div>
            <div className="text-sm font-bold uppercase tracking-wider text-foreground">
              <span className="font-display text-base font-bold">{matchedCount}</span> High/Possible-Fit Prospects ready for demo
            </div>
            <div className="text-[11px] font-semibold text-muted-foreground">
              Qualified companies matching robot units without active scheduled demos
            </div>
          </div>
        </div>
        {onNavigateToClients && (
          <button
            type="button"
            onClick={onNavigateToClients}
            className="flex items-center gap-2 rounded-[8px] border border-border bg-black px-4 py-2 text-xs font-bold uppercase tracking-wider text-white shadow-[var(--shadow-xs)] transition-all hover:bg-neutral-800 hover:shadow-[var(--shadow-sm)]"
          >
            Go to Companies <ArrowRight className="h-4 w-4 text-primary" strokeWidth={2.5} />
          </button>
        )}
      </div>

      {/* Three status-based Kanban columns */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">

        {/* Column 1 — Scheduled */}
        <div className="overflow-hidden rounded-[var(--radius)] border border-border bg-card shadow-[var(--shadow-sm)]">
          <ColumnHeader
            label="Scheduled"
            count={scheduledViewings.length}
            dotColor="#171717"
            icon={<CalendarClock className="h-4 w-4 text-muted-foreground" strokeWidth={2} />}
          />
          <div className="flex flex-col gap-3 p-4 max-h-[750px] overflow-y-auto scrollbar-none">
            {scheduledViewings.length === 0 ? (
              <p className="py-6 text-center text-xs font-semibold text-muted-foreground">
                No upcoming demos scheduled
              </p>
            ) : (
              scheduledViewings.map((v) => (
                <ViewingCard
                  key={v.id}
                  viewing={v}
                  dedupClients={dedupClients}
                  onComplete={v.status === "upcoming" ? handleComplete : undefined}
                  onCancel={handleCancel}
                  onConfirm={v.status === "requested" ? handleConfirm : undefined}
                  completing={completing === v.id}
                  cancelling={cancelling === v.id}
                  confirming={confirming === v.id}
                />
              ))
            )}
          </div>
        </div>

        {/* Column 2 — Completed */}
        <div className="overflow-hidden rounded-[var(--radius)] border border-border bg-card shadow-[var(--shadow-sm)]">
          <ColumnHeader
            label="Completed"
            count={completedViewings.length}
            dotColor="#ffd400"
            icon={<CalendarCheck className="h-4 w-4 text-muted-foreground" strokeWidth={2} />}
          />
          <div className="flex flex-col gap-3 p-4 max-h-[750px] overflow-y-auto scrollbar-none">
            {completedViewings.length === 0 ? (
              <p className="py-6 text-center text-xs font-semibold text-muted-foreground">
                No completed demos yet
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
        <div className="overflow-hidden rounded-[var(--radius)] border border-border bg-card shadow-[var(--shadow-sm)]">
          <ColumnHeader
            label="Cancelled"
            count={cancelledViewings.length}
            dotColor="#a3a3a3"
            icon={<CalendarX className="h-4 w-4 text-muted-foreground" strokeWidth={2} />}
          />
          <div className="flex flex-col gap-3 p-4 max-h-[750px] overflow-y-auto scrollbar-none">
            {cancelledViewings.length === 0 ? (
              <p className="py-6 text-center text-xs font-semibold text-muted-foreground">
                No cancelled demos
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
