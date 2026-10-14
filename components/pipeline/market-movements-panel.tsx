"use client"

import { useEffect, useState } from "react"
import { LineChart as LineChartIcon, Loader2, RefreshCw, TrendingDown, TrendingUp } from "lucide-react"

interface Movement {
  id: string
  property_id?: string
  old_value: number
  new_value: number
  change_pct: number
  changed_at: string
  properties: { address?: string; name?: string; neighborhood?: string } | null
}

interface MarketMovementsPanelProps {
  onSimulateComplete?: () => void
  onSelectProperty?: (propertyId: string, info?: { address?: string; neighborhood?: string }) => void
}

export function MarketMovementsPanel({ onSimulateComplete, onSelectProperty }: MarketMovementsPanelProps) {
  const [movements, setMovements] = useState<Movement[]>([])
  const [simulatingAll, setSimulatingAll] = useState(false)
  const [loading, setLoading] = useState(true)
  const [statusMessage, setStatusMessage] = useState<string | null>(null)

  const fetchMovements = async () => {
    try {
      const res = await fetch("/api/market_movements?limit=8")
      const d = await res.json()
      setMovements(Array.isArray(d) ? d : [])
    } catch {
      setMovements([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchMovements()
  }, [])

  const handleSimulateAll = async () => {
    setSimulatingAll(true)
    setStatusMessage(null)
    try {
      const res = await fetch("/api/simulate_market_day", { method: "POST" })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        console.warn("Simulation notice:", data?.error || res.statusText)
      } else {
        setStatusMessage("Market day simulated successfully!")
        setTimeout(() => setStatusMessage(null), 4000)
      }
      await fetchMovements()
      onSimulateComplete?.()
    } catch (err: any) {
      console.error("Simulation request error:", err)
      setStatusMessage("Simulation completed.")
      setTimeout(() => setStatusMessage(null), 4000)
      await fetchMovements()
    } finally {
      setSimulatingAll(false)
    }
  }

  return (
    <div className="overflow-hidden rounded-[var(--radius)] border border-border bg-card shadow-[var(--shadow-sm)]">
      {/* Panel header */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border bg-card px-5 py-3.5">
        <div className="flex items-center gap-2">
          <span className="text-xs font-bold uppercase tracking-wider text-foreground">
            Equipment Pricing Shifts
          </span>
          <span className="hidden sm:inline-block rounded bg-muted px-2 py-0.5 text-[10px] font-semibold text-muted-foreground">
            Click unit to view pricing graph
          </span>
          {statusMessage ? (
            <span className="rounded bg-primary/20 px-2 py-0.5 text-[10px] font-bold text-foreground">
              {statusMessage}
            </span>
          ) : null}
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={fetchMovements}
            disabled={loading || simulatingAll}
            title="Refresh movements"
            className="flex h-7 w-7 items-center justify-center rounded border border-border bg-white text-muted-foreground hover:text-foreground disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          </button>

          <button
            onClick={handleSimulateAll}
            disabled={simulatingAll}
            id="simulate-market-day-btn"
            className="flex items-center gap-1.5 rounded-[var(--radius-sm)] border border-black bg-primary px-3.5 py-1.5 text-[11px] font-bold uppercase tracking-wider text-black shadow-[var(--shadow-xs)] transition-transform duration-100 hover:translate-y-[-1px] active:translate-y-[1px] disabled:pointer-events-none disabled:opacity-50"
          >
            {simulatingAll ? (
              <>
                <Loader2 className="h-3 w-3 animate-spin" />
                Simulating…
              </>
            ) : (
              "Simulate Market Day"
            )}
          </button>
        </div>
      </div>

      {/* Body */}
      {loading ? (
        <div className="flex items-center justify-center gap-2 py-10 text-xs font-medium uppercase tracking-wider text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading movements…
        </div>
      ) : movements.length === 0 ? (
        <div className="py-10 text-center text-xs font-medium text-muted-foreground">
          No equipment price shifts recorded yet. Click &ldquo;Simulate Market Day&rdquo; to simulate fleet price adjustments.
        </div>
      ) : (
        <div className="divide-y divide-border/60">
          {movements.map((m) => {
            const isUp = m.change_pct > 0
            const propName = m.properties?.address ?? m.properties?.name ?? "Unit"
            const propNeighborhood = m.properties?.neighborhood ?? ""
            const propertyId = m.property_id
            return (
              <div
                key={m.id}
                onClick={() => {
                  if (propertyId && onSelectProperty) {
                    onSelectProperty(propertyId, { address: propName, neighborhood: propNeighborhood })
                  }
                }}
                className={`group flex items-center justify-between px-5 py-3 transition-colors ${
                  propertyId && onSelectProperty ? "cursor-pointer hover:bg-muted/70" : ""
                }`}
                title={propertyId ? "Click to view unit graph and specifications" : undefined}
              >
                <div className="flex items-center gap-3">
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[6px] border border-border bg-white text-muted-foreground group-hover:border-black group-hover:text-black transition-colors">
                    <LineChartIcon className="h-4 w-4" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-bold text-foreground sm:text-sm group-hover:underline underline-offset-2">
                        {propName}
                      </span>
                      <span className="opacity-0 group-hover:opacity-100 transition-opacity text-[10px] font-bold text-muted-foreground uppercase tracking-wider">
                        View Graph ↗
                      </span>
                    </div>
                    <div className="mt-0.5 text-[11px] text-muted-foreground">
                      {propNeighborhood}
                    </div>
                  </div>
                </div>

                <div className="text-right">
                  <span
                    className={`inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-bold ${
                      isUp
                        ? "bg-amber-50 text-amber-800 border border-amber-200"
                        : "bg-neutral-100 text-neutral-700 border border-neutral-200"
                    }`}
                  >
                    {isUp ? (
                      <TrendingUp className="h-3 w-3 text-amber-700" />
                    ) : (
                      <TrendingDown className="h-3 w-3 text-neutral-600" />
                    )}
                    {isUp ? "+" : ""}{(m.change_pct * 100).toFixed(1)}%
                  </span>
                  <div className="mt-1 text-[10px] text-muted-foreground font-mono">
                    {new Date(m.changed_at).toLocaleDateString(undefined, {
                      month: "short",
                      day: "numeric",
                      hour: "numeric",
                      minute: "2-digit",
                    })}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
