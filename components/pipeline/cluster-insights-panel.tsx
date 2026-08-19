"use client"

import { useState } from "react"
import { Building2, Sparkles, Loader2 } from "lucide-react"
import { currency, type Client } from "@/lib/pipeline-data"
import { ScrollConnect } from "@/components/animation/scroll-connect"
import { DecryptedText } from "@/components/animation/decrypted-text"

interface ClusterInsightsPanelProps {
  clients: Client[]
}

interface ClusterCardState {
  insight: string | null
  loading: boolean
}

export function ClusterInsightsPanel({ clients }: ClusterInsightsPanelProps) {
  const [clusterStates, setClusterStates] = useState<Record<string, ClusterCardState>>({})

  // Deduplicate unique clients based on clientDbId
  const seen = new Set<string>()
  const uniqueClients = clients.filter((c) => {
    const id = c.clientDbId || c.id
    if (seen.has(id)) return false
    seen.add(id)
    return true
  })

  // Group by preferredNeighborhood
  const clusterMap = new Map<string, { count: number; totalEx: number }>()
  for (const c of uniqueClients) {
    const nbhd = c.preferredNeighborhood ?? "Unknown"
    const cur = clusterMap.get(nbhd) ?? { count: 0, totalEx: 0 }
    clusterMap.set(nbhd, {
      count: cur.count + 1,
      totalEx: cur.totalEx + c.expectedValue,
    })
  }

  const clusters = Array.from(clusterMap.entries())
    .map(([neighborhood, data]) => ({
      neighborhood,
      count: data.count,
      totalEx: data.totalEx,
    }))
    .sort((a, b) => b.totalEx - a.totalEx)

  const handleGetStrategy = async (neighborhood: string) => {
    setClusterStates((prev) => ({
      ...prev,
      [neighborhood]: { insight: null, loading: true },
    }))

    try {
      const res = await fetch("/api/chart_insight", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          slice_type: "cluster",
          slice_data: { neighborhood },
        }),
      })
      const data = await res.json()
      setClusterStates((prev) => ({
        ...prev,
        [neighborhood]: { insight: data.insight ?? "No strategy generated", loading: false },
      }))
    } catch (err) {
      setClusterStates((prev) => ({
        ...prev,
        [neighborhood]: { insight: "Failed to generate strategy note.", loading: false },
      }))
    }
  }

  return (
    <ScrollConnect>
      <div className="border border-neutral-200 bg-white shadow-[0px_4px_16px_rgba(0,0,0,0.10)]">
        {/* Header */}
        <div className="flex items-center justify-between gap-3 border-b border-neutral-200 bg-black px-5 py-3.5 sm:px-6">
          <div className="flex items-center gap-2 text-white">
            <Building2 className="h-4 w-4 text-primary" strokeWidth={2.5} />
            <span className="text-xs font-black uppercase tracking-wider sm:text-sm">
              Neighborhood Cluster Intelligence ({clusters.length} Areas)
            </span>
          </div>
          <span className="border border-neutral-200 bg-primary px-2.5 py-1 text-[10px] font-black uppercase tracking-wider text-black sm:text-xs">
            On-Demand AI Strategy
          </span>
        </div>

        {/* Grid of 8 Neighborhood Cluster Cards */}
        <div className="grid grid-cols-1 gap-4 p-4 sm:grid-cols-2 sm:p-6 lg:grid-cols-4">
          {clusters.map((cl) => {
            const state = clusterStates[cl.neighborhood] || { insight: null, loading: false }

            return (
              <div
                key={cl.neighborhood}
                className="flex flex-col justify-between border border-neutral-200 bg-neutral-50 p-4 shadow-[0px_2px_8px_rgba(0,0,0,0.08)] transition-transform hover:shadow-[0px_2px_8px_rgba(0,0,0,0.08)]"
              >
                <div>
                  <div className="flex items-start justify-between gap-2">
                    <span className="font-sans text-sm font-black uppercase tracking-wide text-black">
                      {cl.neighborhood}
                    </span>
                    <span className="border border-neutral-200 bg-white px-2 py-0.5 font-mono text-[10px] font-black">
                      {cl.count} {cl.count === 1 ? "Lead" : "Leads"}
                    </span>
                  </div>

                  <div className="mt-2 font-mono text-base font-black text-black">
                    {currency(cl.totalEx)}
                  </div>
                  <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                    Total Pipeline E(x)
                  </div>

                  {/* AI Strategy inline display */}
                  {state.insight && (
                    <div className="mt-3 border border-neutral-200 bg-black p-2.5 font-mono text-xs font-bold leading-relaxed text-white">
                      <DecryptedText
                        text={state.insight}
                        animateOn="view"
                        sequential
                        speed={15}
                        maxIterations={8}
                        useOriginalCharsOnly
                        className="text-white"
                        encryptedClassName="text-[#777]"
                      />
                    </div>
                  )}
                </div>

                <div className="mt-4 border-t-2 border-black pt-3">
                  <button
                    type="button"
                    disabled={state.loading}
                    onClick={() => handleGetStrategy(cl.neighborhood)}
                    className="flex w-full items-center justify-center gap-1.5 border border-neutral-200 bg-primary py-2 text-[11px] font-black uppercase tracking-wider text-black shadow-[0px_1px_4px_rgba(0,0,0,0.07)] transition-all hover:shadow-[0px_1px_3px_rgba(0,0,0,0.06)] disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {state.loading ? (
                      <>
                        <Loader2 className="h-3 w-3 animate-spin text-black" strokeWidth={2.5} />
                        <span>Analyzing…</span>
                      </>
                    ) : (
                      <>
                        <Sparkles className="h-3 w-3 text-black" strokeWidth={2.5} />
                        <span>{state.insight ? "Regenerate" : "Get Strategy"}</span>
                      </>
                    )}
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </ScrollConnect>
  )
}
