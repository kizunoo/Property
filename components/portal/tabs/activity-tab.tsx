"use client"

import { useEffect, useState, useCallback } from "react"
import {
  CalendarCheck2, CheckCircle2, Clock, RefreshCw, XCircle,
} from "lucide-react"
import type { ActivityItem } from "@/lib/portal-types"
import { fetchActivity } from "@/lib/portal-api"
import { Skeleton } from "@/components/ui/skeleton"

// ─── Status icon map ──────────────────────────────────────────────────────────

const STATUS_ICON: Record<string, React.ReactNode> = {
  requested: <Clock       className="h-4 w-4 text-amber-600"      />,
  upcoming:  <CalendarCheck2 className="h-4 w-4 text-black"       />,
  completed: <CheckCircle2 className="h-4 w-4 text-muted-foreground" />,
  cancelled: <XCircle     className="h-4 w-4 text-muted-foreground" />,
}

const STATUS_LABEL: Record<string, string> = {
  requested: "Demo requested",
  upcoming:  "Demo confirmed",
  completed: "Demo completed",
  cancelled: "Demo cancelled",
}

const STATUS_DOT: Record<string, string> = {
  requested: "bg-amber-400",
  upcoming:  "bg-primary",
  completed: "bg-muted-foreground/40",
  cancelled: "bg-muted-foreground/20",
}

function formatDate(s: string | null): string {
  if (!s) return "Date TBC"
  return new Date(s).toLocaleDateString("en-MY", {
    weekday: "long", day: "numeric", month: "long", year: "numeric",
  })
}

function formatTime(s: string | null): string {
  if (!s) return ""
  return new Date(s).toLocaleTimeString("en-MY", { hour: "2-digit", minute: "2-digit" })
}

// Group items by calendar day
function groupByDay(items: ActivityItem[]): Map<string, ActivityItem[]> {
  const map = new Map<string, ActivityItem[]>()
  for (const item of items) {
    const key = item.date ? new Date(item.date).toDateString() : "Date TBC"
    if (!map.has(key)) map.set(key, [])
    map.get(key)!.push(item)
  }
  return map
}

// ─── Activity Tab ─────────────────────────────────────────────────────────────

export function ActivityTab({ clientId }: { clientId: string }) {
  const [items, setItems] = useState<ActivityItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const d = await fetchActivity(clientId)
      setItems(d.activity)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load activity.")
    } finally {
      setLoading(false)
    }
  }, [clientId])

  useEffect(() => { load() }, [load])

  if (loading) {
    return (
      <div className="mx-auto max-w-3xl px-4 sm:px-6 py-10 flex flex-col gap-4">
        <Skeleton className="h-6 w-40" />
        {[...Array(4)].map((_, i) => (
          <div key={i} className="flex gap-4">
            <Skeleton className="h-8 w-8 rounded-full shrink-0" />
            <Skeleton className="h-16 flex-1" />
          </div>
        ))}
      </div>
    )
  }

  if (error) {
    return (
      <div className="mx-auto max-w-3xl px-4 sm:px-6 py-10">
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

  if (items.length === 0) {
    return (
      <div className="mx-auto max-w-3xl px-4 sm:px-6 py-10">
        <div className="border border-border bg-card p-12 text-center shadow-[var(--shadow-sm)]">
          <RefreshCw className="mx-auto h-6 w-6 text-muted-foreground opacity-40 mb-3" />
          <p className="text-sm text-muted-foreground">No activity yet — your timeline will appear here once you start requesting demos.</p>
        </div>
      </div>
    )
  }

  const grouped = groupByDay(items)

  return (
    <div className="mx-auto max-w-3xl px-4 sm:px-6 py-10 flex flex-col gap-8">
      <h1 className="text-[10px] font-black uppercase tracking-wider text-muted-foreground flex items-center gap-2">
        <RefreshCw className="h-3.5 w-3.5" />
        Activity timeline
      </h1>

      {/* Timeline groups by day */}
      {[...grouped.entries()].map(([day, dayItems]) => (
        <section key={day} aria-label={`Activity on ${day}`}>
          {/* Day header */}
          <div className="flex items-center gap-3 mb-4">
            <span className="text-xs font-black uppercase tracking-wider text-muted-foreground">{day}</span>
            <div className="flex-1 h-px bg-border" />
          </div>

          {/* Timeline items */}
          <div className="relative">
            {/* Vertical line */}
            <div className="absolute left-4 top-2 bottom-2 w-px bg-border" aria-hidden="true" />

            <div className="flex flex-col gap-1">
              {dayItems.map((item, i) => {
                const dot   = STATUS_DOT[item.status]   ?? "bg-border"
                const icon  = STATUS_ICON[item.status]  ?? <Clock className="h-4 w-4 text-muted-foreground" />
                const label = STATUS_LABEL[item.status] ?? item.status

                return (
                  <div
                    key={`${item.viewing_id}-${i}`}
                    className="relative flex gap-4 items-start pl-10 pb-4 last:pb-0"
                  >
                    {/* Dot on the line */}
                    <span
                      className={`absolute left-[11px] top-[7px] h-2.5 w-2.5 rounded-full border-2 border-background ${dot}`}
                      aria-hidden="true"
                    />

                    {/* Card */}
                    <div className="flex-1 border border-border bg-card shadow-[var(--shadow-xs)] p-4 flex items-start gap-3">
                      <span className="shrink-0 mt-0.5">{icon}</span>
                      <div className="flex flex-col gap-0.5 min-w-0">
                        <p className="text-sm font-bold leading-snug truncate">{item.property_name}</p>
                        <p className="text-xs text-muted-foreground font-medium">{label}</p>
                        {item.date && (
                          <p className="text-[11px] text-muted-foreground/70 mt-0.5">{formatTime(item.date)}</p>
                        )}
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </section>
      ))}
    </div>
  )
}
