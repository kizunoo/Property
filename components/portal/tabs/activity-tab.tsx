"use client"

import { useEffect, useState, useCallback } from "react"
import {
  CalendarCheck2,
  CheckCircle2,
  Clock,
  FileText,
  MessageSquare,
  RefreshCw,
  Settings2,
  XCircle,
  Zap,
} from "lucide-react"
import type { ActivityEventType, ActivityItem } from "@/lib/portal-types"
import { fetchActivity } from "@/lib/portal-api"
import { Skeleton } from "@/components/ui/skeleton"

// ─── Event Icons & Styling ───────────────────────────────────────────────────

const EVENT_CONFIG: Record<
  ActivityEventType,
  {
    icon: React.ReactNode
    badgeClass: string
    dotClass: string
    typeLabel: string
  }
> = {
  demo: {
    icon: <CalendarCheck2 className="h-4 w-4 text-primary" />,
    badgeClass: "bg-primary/10 border-primary/30 text-primary-foreground",
    dotClass: "bg-primary",
    typeLabel: "Hardware Demo",
  },
  quote: {
    icon: <FileText className="h-4 w-4 text-emerald-600" />,
    badgeClass: "bg-emerald-50 border-emerald-200 text-emerald-700",
    dotClass: "bg-emerald-500",
    typeLabel: "Quotation",
  },
  message: {
    icon: <MessageSquare className="h-4 w-4 text-sky-600" />,
    badgeClass: "bg-sky-50 border-sky-200 text-sky-700",
    dotClass: "bg-sky-500",
    typeLabel: "Inquiry Message",
  },
  profile: {
    icon: <Settings2 className="h-4 w-4 text-purple-600" />,
    badgeClass: "bg-purple-50 border-purple-200 text-purple-700",
    dotClass: "bg-purple-500",
    typeLabel: "Profile Update",
  },
}

function formatDate(iso: string | null): string {
  if (!iso) return "Date TBC"
  try {
    return new Date(iso).toLocaleDateString("en-MY", {
      weekday: "short",
      day: "numeric",
      month: "short",
      year: "numeric",
    })
  } catch {
    return iso
  }
}

function formatTime(iso: string | null): string {
  if (!iso) return ""
  try {
    return new Date(iso).toLocaleTimeString("en-MY", {
      hour: "2-digit",
      minute: "2-digit",
    })
  } catch {
    return ""
  }
}

// Group items by calendar day
function groupByDay(items: ActivityItem[]): Map<string, ActivityItem[]> {
  const map = new Map<string, ActivityItem[]>()
  for (const item of items) {
    const key = item.at ? formatDate(item.at) : "Date TBC"
    if (!map.has(key)) map.set(key, [])
    map.get(key)!.push(item)
  }
  return map
}

// ─── Activity Tab Component ──────────────────────────────────────────────────

export function ActivityTab({ clientId }: { clientId: string }) {
  const [items, setItems] = useState<ActivityItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const d = await fetchActivity(clientId)
      setItems(d.activity || [])
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load activity.")
    } finally {
      setLoading(false)
    }
  }, [clientId])

  useEffect(() => {
    load()
  }, [load])

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
          <button
            onClick={load}
            className="border border-border bg-black px-4 py-2 text-xs font-black uppercase tracking-wider text-white hover:shadow-[var(--shadow-sm)] transition-shadow"
          >
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
          <RefreshCw className="mx-auto h-8 w-8 text-muted-foreground opacity-40 mb-3" />
          <h3 className="font-bold text-base mb-1">No activity logged yet</h3>
          <p className="text-sm text-muted-foreground max-w-md mx-auto">
            Your timeline records demonstration requests, quotations, inquiries, and specification
            updates as your engagement progresses.
          </p>
        </div>
      </div>
    )
  }

  const grouped = groupByDay(items)

  return (
    <div className="mx-auto max-w-3xl px-4 sm:px-6 py-10 flex flex-col gap-8">
      <div>
        <h1 className="text-[10px] font-black uppercase tracking-wider text-muted-foreground flex items-center gap-2">
          <RefreshCw className="h-3.5 w-3.5" />
          Activity timeline ({items.length} events)
        </h1>
        <p className="text-sm font-semibold mt-1">Audit log of your interactions and requests</p>
      </div>

      {/* Timeline groups by day */}
      {[...grouped.entries()].map(([day, dayItems]) => (
        <section key={day} aria-label={`Activity on ${day}`}>
          {/* Day header */}
          <div className="flex items-center gap-3 mb-4">
            <span className="text-xs font-black uppercase tracking-wider text-muted-foreground">
              {day}
            </span>
            <div className="flex-1 h-px bg-border" />
          </div>

          {/* Timeline items */}
          <div className="relative">
            {/* Vertical line */}
            <div className="absolute left-4 top-2 bottom-2 w-px bg-border" aria-hidden="true" />

            <div className="flex flex-col gap-2">
              {dayItems.map((item, i) => {
                const conf = EVENT_CONFIG[item.event_type] ?? EVENT_CONFIG.demo

                return (
                  <div
                    key={`${item.ref_id}-${i}`}
                    className="relative flex gap-4 items-start pl-10 pb-3 last:pb-0"
                  >
                    {/* Dot on the line */}
                    <span
                      className={`absolute left-[11px] top-[14px] h-2.5 w-2.5 rounded-full border-2 border-background ${conf.dotClass}`}
                      aria-hidden="true"
                    />

                    {/* Card */}
                    <div className="flex-1 border border-border bg-card shadow-[var(--shadow-xs)] p-4 flex items-start gap-3">
                      <span className="shrink-0 mt-0.5">{conf.icon}</span>
                      <div className="flex flex-col gap-1 min-w-0 flex-1">
                        <div className="flex items-center justify-between gap-2 flex-wrap">
                          <span
                            className={`inline-flex items-center px-2 py-0.5 text-[9px] font-black uppercase tracking-wider border ${conf.badgeClass}`}
                          >
                            {conf.typeLabel}
                          </span>
                          {item.at && (
                            <span className="text-[11px] text-muted-foreground/70">
                              {formatTime(item.at)}
                            </span>
                          )}
                        </div>
                        <p className="text-sm font-bold leading-snug">{item.label}</p>
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
