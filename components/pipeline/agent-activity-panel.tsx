"use client"

import React, { useEffect, useState } from "react"
import {
  Activity,
  Bot,
  Clock,
  Check,
  Copy,
  ChevronDown,
  ChevronUp,
  FileText,
  Send,
  X,
  XCircle,
} from "lucide-react"
import { QuoteCard } from "./quote-card"
import { logQuoteActivity, cancelQuoteRequest } from "@/lib/fetch-quotes"
import {
  isValidQuote,
  type ActivityRow,
  type AgentAction,
  type Names,
  type QuoteRequest,
  type SupplierQuote,
} from "@/lib/quotes"

export interface AgentActivityPanelProps {
  requests: QuoteRequest[]
  quotes: SupplierQuote[]
  activity: ActivityRow[]
  actions: AgentAction[]
  briefingLines: string[]
  marketByRobot: Record<string, number | null | undefined>
  nowMs: number
  names: Names
  onRefresh: () => void
  onDraftRequote?: (clientId: string, propertyId: string, marketPrice: number) => void
  onOpenDraft?: (req: QuoteRequest) => void
}

export function AgentActivityPanel({
  requests,
  quotes,
  activity,
  actions,
  briefingLines,
  marketByRobot,
  nowMs,
  names,
  onRefresh,
  onDraftRequote,
  onOpenDraft,
}: AgentActivityPanelProps) {
  const [mounted, setMounted] = useState(false)
  const [reviewingActionId, setReviewingActionId] = useState<string | null>(null)
  const [copiedId, setCopiedId] = useState<string | null>(null)
  const [acting, setActing] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  const handleDismissRequote = async (action: AgentAction) => {
    setActing(true)
    await logQuoteActivity(
      "requote_dismissed",
      action.quoteId,
      `Requote dismissed for ${names.robot(action.propertyId)}`
    )
    setActing(false)
    onRefresh()
  }

  const handleDismissExpiry = async (action: AgentAction) => {
    setActing(true)
    await logQuoteActivity(
      "expiry_dismissed",
      action.quoteId,
      `Expiry dismissed for ${names.robot(action.propertyId)}`
    )
    setActing(false)
    setReviewingActionId(null)
    onRefresh()
  }

  const handleMarkExpirySent = async (action: AgentAction) => {
    setActing(true)
    await logQuoteActivity(
      "expiry_followup_sent",
      action.quoteId,
      `Expiry follow-up sent to ${names.client(action.clientId)}`
    )
    setActing(false)
    setReviewingActionId(null)
    onRefresh()
  }

  const handleCopyText = (actionId: string, text: string) => {
    if (typeof navigator !== "undefined" && navigator.clipboard) {
      navigator.clipboard.writeText(text).then(() => {
        setCopiedId(actionId)
      })
    }
  }

  const handleCancelDraft = async (reqId: string) => {
    setActing(true)
    await cancelQuoteRequest(reqId)
    setActing(false)
    onRefresh()
  }

  // Set of (clientId, propertyId) pairs with active valid quotes
  const validQuotePairs = new Set(
    quotes
      .filter((q) => isValidQuote(q, nowMs))
      .map((q) => `${q.clientId}:${q.propertyId}`)
  )

  const waitingRequests = requests.filter((r) => {
    if (r.status === "sent") return true
    if (r.status === "draft") {
      // If an active valid quote already exists and this is an initial quote request,
      // the quote has already arrived — this draft is obsolete.
      if (r.kind === "quote" && validQuotePairs.has(`${r.clientId}:${r.propertyId}`)) {
        return false
      }
      return true
    }
    return false
  })
  const recentQuotes = quotes.slice(0, 5)
  const recentActivity = activity.slice(0, 10)

  return (
    <div className="rounded-xl border border-neutral-800 bg-[#0A0A0A] p-5 text-white shadow-md my-4">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-neutral-800 pb-3">
        <div className="flex items-center gap-2">
          <Bot className="h-4 w-4 text-[#FFD600]" />
          <h3 className="text-xs font-bold uppercase tracking-wider text-neutral-200">
            AGENT ACTIVITY
          </h3>
          <span className="rounded bg-neutral-800 px-2 py-0.5 text-[10px] font-semibold text-neutral-400">
            simulated supplier
          </span>
        </div>
        <button
          onClick={onRefresh}
          className="text-[11px] font-medium text-neutral-400 hover:text-white"
        >
          Refresh
        </button>
      </div>

      {/* 1. Briefing */}
      <div className="mt-4 rounded-lg border border-neutral-800/80 bg-neutral-900/60 p-3.5">
        <div className="text-[11px] font-bold uppercase tracking-wider text-neutral-400 mb-2">
          Briefing
        </div>
        <ul className="space-y-1.5 text-xs text-neutral-300">
          {briefingLines.map((line, idx) => (
            <li key={idx} className="flex items-start gap-2">
              <span className="text-[#FFD600] mt-0.5">•</span>
              <span>{line}</span>
            </li>
          ))}
        </ul>
      </div>

      {/* 2. Actions Waiting */}
      <div className="mt-5">
        <div className="text-[11px] font-bold uppercase tracking-wider text-neutral-400 mb-2.5 flex items-center gap-1.5">
          <span>Actions Waiting</span>
          <span className="rounded-full bg-neutral-800 px-1.5 py-0.2 text-[10px] text-neutral-300 font-mono">
            {actions.length}
          </span>
        </div>

        {actions.length === 0 ? (
          <div className="rounded-lg border border-neutral-900 bg-neutral-950/40 p-4 text-center text-xs text-neutral-500">
            No pending agent actions right now.
          </div>
        ) : (
          <div className="space-y-2.5">
            {actions.map((act) => (
              <div
                key={act.id}
                className="rounded-lg border border-neutral-800 bg-neutral-900/90 p-3 text-xs"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="font-semibold text-neutral-100">{act.title}</div>
                    <div className="mt-1 text-neutral-400">{act.detail}</div>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    {act.kind === "requote" ? (
                      <>
                        <button
                          type="button"
                          disabled={acting}
                          onClick={() => {
                            if (onDraftRequote && act.marketPriceMyr != null) {
                              onDraftRequote(act.clientId, act.propertyId, act.marketPriceMyr)
                            }
                          }}
                          className="rounded bg-[#FFD600] px-2.5 py-1 text-[11px] font-bold text-black hover:bg-[#e6c200] disabled:opacity-50"
                        >
                          Draft requote
                        </button>
                        <button
                          type="button"
                          disabled={acting}
                          onClick={() => handleDismissRequote(act)}
                          className="rounded border border-neutral-700 bg-transparent px-2 py-1 text-[11px] font-medium text-neutral-400 hover:text-white disabled:opacity-50"
                        >
                          Dismiss
                        </button>
                      </>
                    ) : (
                      <>
                        <button
                          type="button"
                          onClick={() =>
                            setReviewingActionId(
                              reviewingActionId === act.id ? null : act.id
                            )
                          }
                          className="rounded border border-neutral-700 bg-neutral-800 px-2.5 py-1 text-[11px] font-semibold text-neutral-200 hover:bg-neutral-700"
                        >
                          {reviewingActionId === act.id ? "Close message" : "Review message"}
                        </button>
                        <button
                          type="button"
                          disabled={acting}
                          onClick={() => handleDismissExpiry(act)}
                          className="rounded border border-neutral-700 bg-transparent px-2 py-1 text-[11px] font-medium text-neutral-400 hover:text-white disabled:opacity-50"
                        >
                          Dismiss
                        </button>
                      </>
                    )}
                  </div>
                </div>

                {act.kind === "expiry" && reviewingActionId === act.id && act.draft && (
                  <div className="mt-3 rounded border border-neutral-700/80 bg-neutral-950 p-3">
                    <div className="text-[10px] font-semibold uppercase tracking-wider text-neutral-400 mb-1">
                      Draft message for company
                    </div>
                    <p className="whitespace-pre-wrap font-mono text-xs text-neutral-300 leading-relaxed">
                      {act.draft}
                    </p>
                    <div className="mt-3 flex items-center justify-end gap-2 border-t border-neutral-800 pt-2">
                      <button
                        type="button"
                        onClick={() => handleCopyText(act.id, act.draft!)}
                        className="flex items-center gap-1 rounded border border-neutral-700 bg-neutral-900 px-2.5 py-1 text-[11px] font-medium text-neutral-200 hover:bg-neutral-800"
                      >
                        {copiedId === act.id ? (
                          <>
                            <Check className="h-3 w-3 text-emerald-400" />
                            <span>Copied</span>
                          </>
                        ) : (
                          <>
                            <Copy className="h-3 w-3 text-neutral-400" />
                            <span>Copy</span>
                          </>
                        )}
                      </button>
                      <button
                        type="button"
                        disabled={acting}
                        onClick={() => handleMarkExpirySent(act)}
                        className="rounded bg-emerald-600 px-2.5 py-1 text-[11px] font-bold text-white hover:bg-emerald-500 disabled:opacity-50"
                      >
                        Mark as sent
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 3. Waiting for Supplier */}
      <div className="mt-5">
        <div className="text-[11px] font-bold uppercase tracking-wider text-neutral-400 mb-2.5 flex items-center gap-1.5">
          <span>Waiting for Supplier</span>
          <span className="rounded-full bg-neutral-800 px-1.5 py-0.2 text-[10px] text-neutral-300 font-mono">
            {waitingRequests.length}
          </span>
        </div>

        {waitingRequests.length === 0 ? (
          <div className="rounded-lg border border-neutral-900 bg-neutral-950/40 p-4 text-center text-xs text-neutral-500">
            No requests waiting for supplier reply.
          </div>
        ) : (
          <div className="space-y-2">
            {waitingRequests.map((r) => (
              <div
                key={r.id}
                className="flex items-center justify-between rounded-lg border border-neutral-800/80 bg-neutral-900/60 p-3 text-xs"
              >
                <div>
                  <div className="font-semibold text-neutral-200">
                    {names.robot(r.propertyId)} · for {names.client(r.clientId)}
                  </div>
                  <div className="mt-0.5 text-neutral-400 flex items-center gap-1.5">
                    <Clock className="h-3 w-3 text-amber-400" />
                    <span>
                      {r.status === "draft"
                        ? "Draft awaiting your approval"
                        : "Waiting for supplier reply (simulated), expected within about 2 minutes"}
                    </span>
                  </div>
                </div>

                {r.status === "draft" && (
                  <div className="flex items-center gap-2 shrink-0">
                    {onOpenDraft && (
                      <button
                        type="button"
                        onClick={() => onOpenDraft(r)}
                        className="rounded bg-[#FFD600] px-2.5 py-1 text-[11px] font-bold text-black hover:bg-[#e6c200]"
                      >
                        Open draft
                      </button>
                    )}
                    <button
                      type="button"
                      disabled={acting}
                      onClick={() => handleCancelDraft(r.id)}
                      className="rounded border border-neutral-700 bg-transparent px-2 py-1 text-[11px] font-medium text-neutral-400 hover:text-white disabled:opacity-50"
                    >
                      Dismiss
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 4. Recent Quotes */}
      <div className="mt-5">
        <div className="text-[11px] font-bold uppercase tracking-wider text-neutral-400 mb-2.5 flex items-center gap-1.5">
          <span>Recent Quotes</span>
          <span className="rounded-full bg-neutral-800 px-1.5 py-0.2 text-[10px] text-neutral-300 font-mono">
            {recentQuotes.length}
          </span>
        </div>

        {recentQuotes.length === 0 ? (
          <div className="rounded-lg border border-neutral-900 bg-neutral-950/40 p-4 text-center text-xs text-neutral-500">
            No supplier quotes received yet.
          </div>
        ) : (
          <div className="space-y-2.5">
            {recentQuotes.map((q) => (
              <QuoteCard
                key={q.id}
                quote={q}
                marketPrice={marketByRobot[q.propertyId]}
                nowMs={nowMs}
                robotName={names.robot(q.propertyId)}
                companyName={names.client(q.clientId)}
              />
            ))}
          </div>
        )}
      </div>

      {/* 5. Activity Log */}
      <div className="mt-5">
        <div className="text-[11px] font-bold uppercase tracking-wider text-neutral-400 mb-2.5">
          Activity Log
        </div>

        {recentActivity.length === 0 ? (
          <div className="rounded-lg border border-neutral-900 bg-neutral-950/40 p-4 text-center text-xs text-neutral-500">
            No recent agent activity logged.
          </div>
        ) : (
          <div className="divide-y divide-neutral-800/80 rounded-lg border border-neutral-800/80 bg-neutral-900/40 text-xs">
            {recentActivity.map((a) => (
              <div key={a.id} className="flex items-start justify-between p-2.5">
                <div>
                  <div className="text-neutral-300">{a.summary}</div>
                  <div className="mt-0.5 text-[10px] font-mono text-neutral-500">
                    {a.kind}
                  </div>
                </div>
                <div className="text-[10px] font-mono text-neutral-500 shrink-0">
                  {mounted && a.createdAt
                    ? new Date(a.createdAt).toLocaleTimeString([], {
                        hour: "2-digit",
                        minute: "2-digit",
                      })
                    : ""}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

