"use client"

import { useEffect, useRef, useState } from "react"
import { Sparkles, RefreshCw, AlertCircle } from "lucide-react"
import { generateInsight } from "@/lib/generate-insight"
import type { Client } from "@/lib/pipeline-data"
import { DecryptedText } from "@/components/animation/decrypted-text"
import { ScrollConnect } from "@/components/animation/scroll-connect"


interface AnalyticsInsightPanelProps {
  clients: Client[]
  activeFilters: { tier: string; neighborhood: string }
}

type Status = "idle" | "loading" | "success" | "error"

// Stable cache key from the two filter dimensions only.
// Same filter → same key → cache hit, no LLM call.
function cacheKey(filters: { tier: string; neighborhood: string }) {
  return `${filters.tier}__${filters.neighborhood}`
}

export function AnalyticsInsightPanel({ clients, activeFilters }: AnalyticsInsightPanelProps) {
  const [insight, setInsight] = useState<string | null>(null)
  const [insightGeneratedAt, setInsightGeneratedAt] = useState<number>(() => Date.now())
  const [status, setStatus]   = useState<Status>("idle")
  const [error, setError]     = useState<string | null>(null)

  // Session-scoped in-memory cache: filterKey → generated insight string
  const cacheRef    = useRef<Map<string, string>>(new Map())
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const mountRef    = useRef(false)

  const load = (
    clientList: Client[],
    filters: { tier: string; neighborhood: string },
    forceRefresh = false,
  ) => {
    const key = cacheKey(filters)

    // Cache hit — show instantly, no spinner, no LLM call
    if (!forceRefresh && cacheRef.current.has(key)) {
      setInsight(cacheRef.current.get(key)!)
      setInsightGeneratedAt(Date.now())
      setStatus("success")
      setError(null)
      return
    }

    // Cache miss — call Groq
    setStatus("loading")
    setError(null)
    generateInsight(clientList, filters)
      .then((text) => {
        cacheRef.current.set(key, text)   // store so next visit is instant
        setInsight(text)
        setInsightGeneratedAt(Date.now())
        setStatus("success")
      })
      .catch((err: Error) => {
        setError(err.message ?? "Failed to generate insight")
        setStatus("error")
      })
  }

  // Debounced auto-refresh whenever filters change
  useEffect(() => {
    if (!mountRef.current) {
      mountRef.current = true
      load(clients, activeFilters)
      return
    }

    // Subsequent filter changes: check cache first (instant if hit), else debounce 600ms
    const key = cacheKey(activeFilters)
    if (cacheRef.current.has(key)) {
      // Immediate cache hit — cancel any pending debounce
      if (debounceRef.current) clearTimeout(debounceRef.current)
      load(clients, activeFilters)
      return
    }

    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      load(clients, activeFilters)
    }, 600)

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeFilters])

  // Manual refresh button: bypass cache and re-generate
  const handleRefresh = () => {
    const key = cacheKey(activeFilters)
    cacheRef.current.delete(key)   // evict so load() goes to LLM
    load(clients, activeFilters, true)
  }

  return (
    <ScrollConnect>
      <div className="border border-neutral-200 bg-white shadow-[0px_4px_16px_rgba(0,0,0,0.10)]">

      {/* Header */}
      <div className="flex items-center justify-between gap-3 border-b border-neutral-200 bg-black px-5 py-3.5 sm:px-6">
        <div className="flex items-center gap-2 text-white">
          <Sparkles className="h-4 w-4" strokeWidth={2.5} />
          <span className="text-xs font-black uppercase tracking-wider sm:text-sm">
            AI Pipeline Insight
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="border border-neutral-200 bg-primary px-2.5 py-1 text-[10px] font-black uppercase tracking-wider text-black sm:text-xs">
            Groq · GPT-OSS 120B
          </span>
          <button
            type="button"
            aria-label="Refresh insight"
            disabled={status === "loading"}
            onClick={handleRefresh}
            title="Re-generate (bypasses cache)"
            className="flex items-center justify-center border border-neutral-200 bg-white p-1.5 text-black transition-transform hover:shadow-[0px_1px_4px_rgba(0,0,0,0.07)] disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <RefreshCw
              className={`h-3.5 w-3.5 ${status === "loading" ? "animate-spin" : ""}`}
              strokeWidth={2.5}
            />
          </button>
        </div>
      </div>

      {/* Body */}
      <div className="px-5 py-4 sm:px-6 sm:py-5">
        {/* Loading shimmer */}
        {status === "loading" && (
          <div className="flex flex-col gap-2.5">
            <div className="h-4 w-full animate-pulse bg-black/10" />
            <div className="h-4 w-[85%] animate-pulse bg-black/10" />
            <div className="h-4 w-[65%] animate-pulse bg-black/10" />
          </div>
        )}

        {/* Error state */}
        {status === "error" && (
          <div className="flex items-start gap-3 border border-neutral-200 bg-[#fff0f0] px-4 py-3">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-black" strokeWidth={2.5} />
            <div>
              <div className="text-xs font-black uppercase tracking-wider">Insight unavailable</div>
              <div className="mt-1 text-xs font-bold text-muted-foreground">{error}</div>
            </div>
          </div>
        )}

        {/* Success */}
        {status === "success" && insight && (
          <div className="flex flex-col gap-3">
            <div className="h-1.5 w-16 border border-black bg-primary" />
            <DecryptedText
              key={insightGeneratedAt}
              text={insight}
              animateOn="view"
              sequential={true}
              revealDirection="start"
              speed={30}
              maxIterations={12}
              useOriginalCharsOnly={true}
              className="decrypt-revealed text-sm font-bold leading-relaxed tracking-wide text-black sm:text-[15px]"
              encryptedClassName="decrypt-encrypted text-sm font-bold leading-relaxed tracking-wide sm:text-[15px]"
            />
            <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
              Based on {clients.length} evaluation{clients.length !== 1 ? "s" : ""} in current view
            </div>
          </div>
        )}

        {/* Idle (before first load) */}
        {status === "idle" && (
          <div className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
            Generating insight…
          </div>
        )}
      </div>
      </div>
    </ScrollConnect>
  )
}
