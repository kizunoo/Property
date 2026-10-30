"use client"

import { useEffect, useState } from "react"
import { Sparkles, TrendingUp, Target, Users, ShieldCheck, RefreshCw, Layers } from "lucide-react"
import { currency } from "@/lib/pipeline-data"
import {
  formatRM,
  demoProjection,
  closeRateFromPct,
  demoStrategyText,
  type PotentialPipelineResult,
} from "@/lib/display-price"

export interface PipelineProjectionData {
  assigned_agent_id: string | null
  agent_name: string
  active_pipeline_value: number | null
  projected_revenue: number | null
  unpriced_count?: number
  close_rate: number
  close_rate_pct: string
  untapped_clients: number
  active_clients: number
  won_count: number
  lost_count: number
  total_closed: number
  narrative: string
}

interface PipelineProjectionCardProps {
  agentId?: string | null
  agentName?: string | null
  syncTimestamp?: number
  potentialPipeline?: PotentialPipelineResult
}

export function PipelineProjectionCard({
  agentId,
  agentName,
  syncTimestamp,
  potentialPipeline,
}: PipelineProjectionCardProps) {
  const [data, setData] = useState<PipelineProjectionData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const hasDisplayPrice = Boolean(potentialPipeline && potentialPipeline.robotsUsed > 0)
  const isDemoMode = Boolean(
    potentialPipeline &&
    potentialPipeline.total > 0 &&
    (!data || data.active_clients === 0)
  )

  const effectiveCloseRate = data?.close_rate ?? (data ? closeRateFromPct(data.close_rate_pct) : 0.10) ?? 0.10
  const demoProj = isDemoMode && potentialPipeline
    ? demoProjection(potentialPipeline.total, effectiveCloseRate)
    : null

  const demoStrategy = isDemoMode && potentialPipeline
    ? demoStrategyText({
        untapped: data?.untapped_clients ?? 0,
        robotsUsed: potentialPipeline.robotsUsed,
        potentialTotal: potentialPipeline.total,
        projected: demoProj?.projected ?? 0,
        closeRatePct: data?.close_rate_pct ?? "10%",
      })
    : null

  useEffect(() => {
    let isMounted = true
    setLoading(true)
    setError(null)

    const params = new URLSearchParams()
    if (agentId && agentId !== "all") {
      params.set("agent_id", agentId)
    }

    const query = params.toString() ? `?${params.toString()}` : ""

    fetch(`/api/pipeline_projection${query}`)
      .then((res) => {
        if (!res.ok) {
          throw new Error(`Failed to load projection (HTTP ${res.status})`)
        }
        return res.json()
      })
      .then((json: PipelineProjectionData) => {
        if (isMounted) {
          setData(json)
          setLoading(false)
        }
      })
      .catch((err: Error) => {
        if (isMounted) {
          setError(err.message || "Failed to load projection")
          setLoading(false)
        }
      })

    return () => {
      isMounted = false
    }
  }, [agentId, syncTimestamp])

  return (
    <div className="relative mb-6 overflow-hidden rounded-[12px] border border-border bg-card shadow-[var(--shadow-sm)]">
      {/* Top Banner Header */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border bg-muted/20 px-5 py-3">
        <div className="flex items-center gap-2">
          <div className="flex h-6 w-6 items-center justify-center rounded-[6px] bg-primary text-black">
            <TrendingUp className="h-3.5 w-3.5" strokeWidth={2.5} />
          </div>
          <span className="text-xs font-black uppercase tracking-wider text-foreground">
            Prescriptive Sales &amp; Revenue Projection
          </span>
          <span className="rounded-[6px] border border-border bg-background px-2 py-0.5 text-[10px] font-bold text-muted-foreground">
            {data?.agent_name ?? agentName ?? "All Sales Reps (Executive View)"}
          </span>
        </div>
        <div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
          <span className="inline-block h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
          <span>Deterministic PostgreSQL Math · Groq Strategy</span>
        </div>
      </div>

      {/* Main Grid: Left side hard numbers, Right side AI Prescriptive Action */}
      <div className="grid grid-cols-1 divide-y divide-border lg:grid-cols-12 lg:divide-x lg:divide-y-0">
        {/* Left Side (Hard Deterministic Data) - 7 cols on lg */}
        <div className="p-5 sm:p-6 lg:col-span-7">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
              Mathematical Foundation
            </span>
            <span className="text-[10px] font-mono text-muted-foreground">
              Formula: Active E(x) × Historical Close Rate
            </span>
          </div>

          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
            {/* Stat 1: Active Pipeline */}
            <div className="flex flex-col justify-between rounded-[8px] border border-border bg-background p-3.5 shadow-[var(--shadow-xs)]">
              <div>
                <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                  Active Pipeline
                </div>
                <div className="mt-1 font-mono text-lg font-black tracking-tight text-foreground sm:text-xl">
                  {loading ? (
                    <span className="inline-block h-6 w-24 animate-pulse bg-muted rounded" />
                  ) : data?.active_pipeline_value != null ? (
                    currency(data.active_pipeline_value)
                  ) : isDemoMode && demoProj ? (
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span>{formatRM(demoProj.active)}</span>
                      <span className="inline-flex items-center rounded border border-sky-500/30 bg-sky-500/10 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-sky-600 dark:text-sky-400">
                        demo estimate
                      </span>
                    </div>
                  ) : hasDisplayPrice ? (
                    currency(0)
                  ) : (
                    "Awaiting quotes"
                  )}
                </div>
              </div>
              <div className="mt-2 text-[10px] font-semibold text-muted-foreground flex flex-col gap-0.5">
                <span>
                  {data && data.active_clients > 0
                    ? `${data.active_clients} active deal${data.active_clients === 1 ? "" : "s"}`
                    : isDemoMode
                    ? "if all prospects adopt"
                    : data
                    ? `${data.active_clients} active deals`
                    : "—"}
                </span>
                {!hasDisplayPrice && data && (data.unpriced_count ?? 0) > 0 && (
                  <span className="text-amber-600 font-bold">{data.unpriced_count} robot{(data.unpriced_count ?? 0) === 1 ? "" : "s"} awaiting quotes</span>
                )}
              </div>
            </div>

            {/* Stat 2: Historical Close Rate */}
            <div className="flex flex-col justify-between rounded-[8px] border border-border bg-background p-3.5 shadow-[var(--shadow-xs)]">
              <div>
                <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                  Close Rate
                </div>
                <div className="mt-1 font-mono text-lg font-black tracking-tight text-foreground sm:text-xl">
                  {loading ? (
                    <span className="inline-block h-6 w-16 animate-pulse bg-muted rounded" />
                  ) : (
                    data?.close_rate_pct ?? "10%"
                  )}
                </div>
              </div>
              <div className="mt-2 text-[10px] font-semibold text-muted-foreground">
                {data ? (
                  data.total_closed > 0 ? (
                    `${data.won_count} deployed / ${data.total_closed} closed`
                  ) : (
                    "10% baseline (no closed deals)"
                  )
                ) : (
                  "..."
                )}
              </div>
            </div>

            {/* Stat 3: Projected Revenue (Hero highlight) */}
            <div className="flex flex-col justify-between rounded-[8px] border-2 border-primary bg-primary/10 p-3.5 shadow-[var(--shadow-xs)]">
              <div>
                <div className="text-[10px] font-black uppercase tracking-wider text-foreground">
                  Projected Revenue
                </div>
                <div className="mt-1 font-mono text-lg font-black tracking-tight text-foreground sm:text-xl">
                  {loading ? (
                    <span className="inline-block h-6 w-24 animate-pulse bg-primary/30 rounded" />
                  ) : data?.projected_revenue != null ? (
                    currency(data.projected_revenue)
                  ) : isDemoMode && demoProj ? (
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span>{formatRM(demoProj.projected)}</span>
                      <span className="inline-flex items-center rounded border border-sky-500/30 bg-sky-500/10 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-sky-600 dark:text-sky-400">
                        demo estimate
                      </span>
                    </div>
                  ) : hasDisplayPrice ? (
                    currency(0)
                  ) : (
                    "Awaiting quotes"
                  )}
                </div>
              </div>
              <div className="mt-2 text-[10px] font-bold text-foreground/80">
                {isDemoMode ? `at ${data?.close_rate_pct ?? "10%"} close rate` : "Projected close value"}
              </div>
            </div>
          </div>

          {/* Potential pipeline summary under the boxes (hidden in demo mode to avoid repeating) */}
          {potentialPipeline && !isDemoMode && (
            <div className="mt-3 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
              <span>Potential pipeline if every prospect adopted</span>
              <span className="inline-flex items-center rounded border border-sky-500/30 bg-sky-500/10 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-sky-600 dark:text-sky-400">
                demo estimate
              </span>
              <span>:</span>
              <span className="font-mono font-bold text-foreground">
                {formatRM(potentialPipeline.total)}
              </span>
              <span>across {potentialPipeline.robotsUsed} robot{potentialPipeline.robotsUsed === 1 ? "" : "s"}</span>
            </div>
          )}

          {/* Sub-strip: Untapped Potential */}
          <div className="mt-4 flex flex-wrap items-center justify-between gap-2 rounded-[8px] border border-border bg-muted/30 px-3.5 py-2.5">
            <div className="flex items-center gap-2">
              <Users className="h-4 w-4 text-amber-600" />
              <span className="text-xs font-bold text-foreground">
                Untapped Opportunity:{" "}
                <span className="font-mono text-amber-700 font-black">
                  {loading ? "…" : (data?.untapped_clients ?? 0)} companies
                </span>{" "}
                in <span className="font-semibold text-muted-foreground">'New'</span> stage
              </span>
            </div>
            <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Run Shortlist to activate
            </span>
          </div>
        </div>

        {/* Right Side (AI Prescriptive Action) - 5 cols on lg */}
        <div className="flex flex-col justify-between bg-muted/10 p-5 sm:p-6 lg:col-span-5">
          <div>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-amber-600 shrink-0" strokeWidth={2.5} />
                <span className="text-xs font-black uppercase tracking-wider text-foreground">
                  AI Prescriptive Strategy
                </span>
              </div>
              <span className="rounded-[4px] border border-amber-400/40 bg-amber-50 px-2 py-0.5 text-[9px] font-black uppercase tracking-wider text-amber-800">
                {isDemoMode ? "Demo summary" : "Actionable Today"}
              </span>
            </div>

            <div className="mt-3">
              {loading ? (
                <div className="space-y-2 py-2">
                  <div className="h-3 w-full animate-pulse bg-muted rounded" />
                  <div className="h-3 w-5/6 animate-pulse bg-muted rounded" />
                  <div className="h-3 w-4/6 animate-pulse bg-muted rounded" />
                </div>
              ) : error ? (
                <div className="rounded border border-red-200 bg-red-50 p-3 text-xs text-red-700">
                  {error}
                </div>
              ) : isDemoMode && demoStrategy ? (
                <p className="font-sans text-xs leading-relaxed text-foreground font-medium sm:text-[13px]">
                  {demoStrategy}
                </p>
              ) : (
                <p className="font-sans text-xs leading-relaxed text-foreground font-medium sm:text-[13px]">
                  {data?.narrative}
                </p>
              )}
            </div>
          </div>

          <div className="mt-4 flex items-center justify-between border-t border-border pt-3">
            <span className="text-[9px] font-bold uppercase tracking-wider text-muted-foreground">
              Guaranteed Zero Hallucination Math
            </span>
            <span className="text-[9px] font-mono font-semibold text-muted-foreground">
              PIPELINE.EV AI Engine
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
