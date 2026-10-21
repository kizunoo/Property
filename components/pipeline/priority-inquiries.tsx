"use client"

import { useCallback, useEffect, useState } from "react"

import { InquiryDetailModal } from "./inquiry-detail-modal"

type Priority = "urgent" | "high" | "normal" | "low"

type Inquiry = {
  inquiry_id: string
  client_id: string
  company: string
  priority: Priority
  category: string | null
  summary: string
  reasons: string[]
  created_at: string | null
  triage_status: string | null
}

// Styled to match the dark "Today's outreach worklist" panel (black, yellow accents, mono details).
const CHIP: Record<Priority, string> = {
  urgent: "bg-red-600 text-white",
  high: "bg-[#FFD600] text-black",
  normal: "bg-neutral-700 text-neutral-100",
  low: "bg-neutral-800 text-neutral-400",
}

const CATEGORY: Record<string, string> = {
  pricing_quote: "Pricing / quote",
  demo_request: "Demo request",
  technical_question: "Technical",
  complaint_issue: "Problem / safety",
  general: "General",
  unclear: "Unclear",
}

const COLLAPSED_COUNT = 5

function ago(iso: string | null): string {
  if (!iso) return ""
  const mins = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000))
  if (mins < 1) return "just now"
  if (mins < 60) return `${mins}m ago`
  if (mins < 1440) return `${Math.round(mins / 60)}h ago`
  return `${Math.round(mins / 1440)}d ago`
}

// Rep-console only. Place inside the dashboard's centered content column, above the outreach worklist.
// Polls so new company inquiries appear without a refresh. All text is rendered as plain text.
export function PriorityInquiries({ onOpenClient }: { onOpenClient?: (clientId: string) => void }) {
  const [items, setItems] = useState<Inquiry[]>([])
  const [failed, setFailed] = useState(false)
  const [showAll, setShowAll] = useState(false)
  const [openId, setOpenId] = useState<string | null>(null)

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
    const tick = () => {
      if (document.visibilityState === "visible") load()
    }
    const timer = setInterval(tick, 30000)
    document.addEventListener("visibilitychange", tick)
    return () => {
      clearInterval(timer)
      document.removeEventListener("visibilitychange", tick)
    }
  }, [load])

  const hot = items.filter((i) => i.priority === "urgent" || i.priority === "high").length
  const visible = showAll ? items : items.slice(0, COLLAPSED_COUNT)

  return (
    <section className="mb-6 overflow-hidden rounded-lg border border-black bg-black text-white">
      <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-3">
        <h2 className="text-xs font-bold uppercase tracking-wide text-[#FFD600]">
          {items.length === 0
            ? "Priority inquiries"
            : `Priority inquiries — ${hot > 0 ? `${hot} need attention` : `${items.length} open`}`}
        </h2>
        <span className="text-[10px] uppercase tracking-wide text-neutral-400">
          AI-labelled · review before acting
        </span>
      </div>

      {failed && (
        <p className="border-t border-neutral-800 px-4 py-2 font-mono text-[11px] text-neutral-400">
          Couldn&apos;t refresh. Retrying…
        </p>
      )}
      {items.length === 0 && !failed && (
        <p className="border-t border-neutral-800 px-4 py-3 font-mono text-xs text-neutral-400">
          No open company inquiries.
        </p>
      )}

      <ul>
        {visible.map((i) => {
          const extraReasons = i.reasons.slice(1) // first reason repeats the category
          return (
            <li key={i.inquiry_id} className="flex items-start gap-3 border-t border-neutral-800 px-4 py-3">
              <span
                className={`mt-0.5 shrink-0 rounded px-2 py-0.5 text-[10px] font-bold uppercase ${CHIP[i.priority]}`}
              >
                {i.priority}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-baseline gap-x-2">
                  <span className="text-sm font-bold">{i.company}</span>
                  <span className="font-mono text-[11px] text-neutral-400">
                    {CATEGORY[i.category ?? ""] ?? "Message"} · {ago(i.created_at)}
                  </span>
                </div>
                <p className="mt-0.5 line-clamp-2 font-mono text-xs text-neutral-200">{i.summary}</p>
                {extraReasons.length > 0 && (
                  <p className="mt-0.5 font-mono text-[10px] text-neutral-500">
                    Why: {extraReasons.join(" · ")}
                  </p>
                )}
              </div>
              <button
                type="button"
                onClick={() => setOpenId(i.inquiry_id)}
                className="shrink-0 rounded border border-[#FFD600] px-3 py-1 text-[11px] font-bold uppercase text-[#FFD600] hover:bg-[#FFD600] hover:text-black"
              >
                Review
              </button>
            </li>
          )
        })}
      </ul>

      {items.length > COLLAPSED_COUNT && (
        <button
          type="button"
          onClick={() => setShowAll((s) => !s)}
          className="w-full border-t border-neutral-800 px-4 py-2 text-left text-[11px] font-bold uppercase tracking-wide text-[#FFD600] hover:bg-neutral-900"
        >
          {showAll ? "Show fewer" : `Show all ${items.length}`}
        </button>
      )}
      {openId && (
        <InquiryDetailModal
          inquiryId={openId}
          onClose={() => setOpenId(null)}
          onOpenClient={onOpenClient}
          onChanged={load}
        />
      )}
    </section>
  )
}

export default PriorityInquiries
