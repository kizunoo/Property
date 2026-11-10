"use client"

import React, { useState } from "react"
import { Check, Loader2, Send } from "lucide-react"
import { compareToMarket, daysLeft, type SupplierQuote } from "@/lib/quotes"
import { formatRM } from "@/lib/display-price"
import { publishQuoteToPortal } from "@/lib/fetch-quotes"

export interface QuoteCardProps {
  quote: SupplierQuote
  marketPrice?: number | null
  nowMs: number
  robotName?: string
  companyName?: string
  className?: string
  onPortalPublished?: () => void
}

export function QuoteCard({
  quote,
  marketPrice,
  nowMs,
  robotName,
  companyName,
  className = "",
  onPortalPublished,
}: QuoteCardProps) {
  const [publishing, setPublishing] = useState(false)
  const [published, setPublished] = useState(false)
  const [publishError, setPublishError] = useState<string | null>(null)

  const left = daysLeft(quote, nowMs)
  const cmp = compareToMarket(quote.priceMyr, marketPrice)

  const handlePublish = async () => {
    setPublishing(true)
    setPublishError(null)
    const res = await publishQuoteToPortal(quote.id)
    setPublishing(false)
    if (res.ok) {
      setPublished(true)
      if (onPortalPublished) onPortalPublished()
    } else {
      setPublishError(res.error || "Failed to publish to portal")
    }
  }

  return (
    <div
      className={`rounded-lg border border-neutral-700 bg-neutral-900/90 p-4 text-white shadow-sm ${className}`}
    >
      <div className="flex items-center justify-between gap-2 border-b border-neutral-800 pb-2">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="rounded bg-amber-500/20 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-amber-300 border border-amber-500/40">
            Simulated supplier quote
          </span>
          {robotName && (
            <span className="text-xs font-semibold text-neutral-200">
              {robotName}
            </span>
          )}
          {companyName && (
            <span className="text-xs text-neutral-400">
              for {companyName}
            </span>
          )}
        </div>
        <div className="text-xs font-mono text-neutral-400">
          {left > 0 ? `${left} day${left === 1 ? "" : "s"} left` : "Expired"}
        </div>
      </div>

      <div className="mt-3 flex items-baseline justify-between gap-4">
        <div>
          <div className="text-xs uppercase tracking-wider text-neutral-400">Quoted Price</div>
          <div className="text-xl font-bold font-mono text-[#FFD600]">
            {formatRM(quote.priceMyr)}
          </div>
        </div>
        {quote.leadTimeWeeks != null && (
          <div className="text-right">
            <div className="text-xs uppercase tracking-wider text-neutral-400">Lead Time</div>
            <div className="text-sm font-semibold text-neutral-200">
              {quote.leadTimeWeeks} weeks
            </div>
          </div>
        )}
      </div>

      {cmp && marketPrice != null && (
        <div className="mt-2.5 rounded bg-neutral-800/80 px-2.5 py-1.5 text-xs text-neutral-300">
          <span className="font-mono font-medium">Market now {formatRM(marketPrice)}</span>
          {cmp.pct > 0.0001 ? (
            <span className="ml-1 text-emerald-400">
              ({(cmp.pct * 100).toFixed(1)}% under the quote)
            </span>
          ) : cmp.pct < -0.0001 ? (
            <span className="ml-1 text-neutral-400">
              ({(Math.abs(cmp.pct) * 100).toFixed(1)}% over the quote)
            </span>
          ) : (
            <span className="ml-1 text-neutral-400">(matches the quote)</span>
          )}
        </div>
      )}

      {quote.terms && (
        <div className="mt-2.5 text-xs text-neutral-400 italic">
          Terms: {quote.terms}
        </div>
      )}

      {/* Client Portal Action */}
      <div className="mt-3.5 pt-3 border-t border-neutral-800 flex items-center justify-between gap-2 flex-wrap">
        <div className="text-[11px] text-neutral-400">
          {published ? (
            <span className="flex items-center gap-1.5 text-emerald-400 font-semibold">
              <Check className="h-3.5 w-3.5" />
              Active in Client Portal &ldquo;Quotes&rdquo; tab
            </span>
          ) : (
            <span>Publish this quote to company portal</span>
          )}
        </div>

        <button
          type="button"
          disabled={publishing || published}
          onClick={handlePublish}
          className={`flex items-center gap-1.5 rounded px-3 py-1.5 text-xs font-bold transition-all ${
            published
              ? "bg-emerald-950/60 border border-emerald-500/40 text-emerald-300 cursor-default"
              : "bg-[#FFD600] text-black hover:bg-[#e6c200] disabled:opacity-50"
          }`}
        >
          {publishing ? (
            <>
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              <span>Publishing…</span>
            </>
          ) : published ? (
            <>
              <Check className="h-3.5 w-3.5 text-emerald-400" />
              <span>Sent to Portal</span>
            </>
          ) : (
            <>
              <Send className="h-3.5 w-3.5" />
              <span>Send to Client Portal</span>
            </>
          )}
        </button>
      </div>
      {publishError && (
        <div className="mt-1 text-[10px] text-red-400 font-semibold">{publishError}</div>
      )}
    </div>
  )
}

