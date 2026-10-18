"use client"

import { useCallback, useEffect, useState } from "react"

type Inquiry = {
  inquiry_id: string
  client_id: string
  company: string
  priority: "urgent" | "high" | "normal" | "low"
  category: string | null
  summary: string
  reasons: string[]
  created_at: string | null
  triage_status: string | null
}

const STYLE: Record<Inquiry["priority"], string> = {
  urgent: "bg-red-600 text-white",
  high: "bg-amber-400 text-black",
  normal: "bg-muted text-foreground",
  low: "bg-muted text-muted-foreground",
}

const CATEGORY: Record<string, string> = {
  pricing_quote: "Pricing / quote",
  demo_request: "Demo request",
  technical_question: "Technical",
  complaint_issue: "Complaint / problem",
  general: "General",
  unclear: "Unclear",
}

function ago(iso: string | null): string {
  if (!iso) return ""
  const mins = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000))
  if (mins < 1) return "just now"
  if (mins < 60) return `${mins}m ago`
  if (mins < 1440) return `${Math.round(mins / 60)}h ago`
  return `${Math.round(mins / 1440)}d ago`
}

// Rep-console only. Polls so new company inquiries appear without a refresh. All text is rendered as plain text.
export function PriorityInquiries({ onOpenClient }: { onOpenClient?: (clientId: string) => void }) {
  const [items, setItems] = useState<Inquiry[]>([])
  const [failed, setFailed] = useState(false)

  const load = useCallback(async () => {
    try {
      const res = await fetch("/api/console/inquiries/priority", { credentials: "same-origin" })
      if (!res.ok) throw new Error(String(res.status))
      const data = await res.json()
      setItems(Array.isArray(data?.inquiries) ? data.inquiries : [])
      setFailed(false)
    } catch {
      setFailed(true)
    }
  }, [])

  useEffect(() => {
    load()
    const tick = () => { if (document.visibilityState === "visible") load() }
    const timer = setInterval(tick, 30000)
    document.addEventListener("visibilitychange", tick)
    return () => {
      clearInterval(timer)
      document.removeEventListener("visibilitychange", tick)
    }
  }, [load])

  const hot = items.filter((i) => i.priority === "urgent" || i.priority === "high").length

  return (
    <section className="rounded-lg border bg-background text-foreground">
      <div className="flex items-center justify-between border-b px-4 py-2 text-sm font-medium">
        <span>Priority inquiries{hot > 0 ? ` (${hot} need attention)` : ""}</span>
        <span className="text-xs font-normal text-muted-foreground">AI-labelled · review before acting</span>
      </div>
      {failed && <p className="px-4 py-2 text-xs text-muted-foreground">Couldn&apos;t refresh. Retrying…</p>}
      {items.length === 0 && !failed && (
        <p className="px-4 py-3 text-sm text-muted-foreground">No open company inquiries.</p>
      )}
      <ul className="divide-y">
        {items.map((i) => (
          <li key={i.inquiry_id} className="flex items-start gap-3 px-4 py-2 text-sm">
            <span className={`mt-0.5 rounded px-2 py-0.5 text-xs font-semibold uppercase ${STYLE[i.priority]}`}>
              {i.priority}
            </span>
            <div className="min-w-0 flex-1">
              <div className="font-medium">
                {i.company}
                <span className="ml-2 text-xs font-normal text-muted-foreground">
                  {CATEGORY[i.category ?? ""] ?? "Message"} · {ago(i.created_at)}
                </span>
              </div>
              <p className="truncate text-muted-foreground">{i.summary}</p>
              {i.reasons.length > 0 && (
                <p className="text-xs text-muted-foreground">Why: {i.reasons.join(" · ")}</p>
              )}
            </div>
            {onOpenClient && (
              <button
                type="button"
                onClick={() => onOpenClient(i.client_id)}
                className="rounded-md border px-2 py-1 text-xs font-medium"
              >
                Open
              </button>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}

export default PriorityInquiries
