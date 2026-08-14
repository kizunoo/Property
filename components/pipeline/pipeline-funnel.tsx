"use client"

import { Bar, BarChart, CartesianGrid, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"
import { BarChart3 } from "lucide-react"
import { getDashboardSummary, type Client, type Tier } from "@/lib/pipeline-data"
import { ScrollConnect } from "@/components/animation/scroll-connect"


// ─── Types ────────────────────────────────────────────────────────────────────
interface FunnelRow {
  label: string
  count: number
  tier: Tier
}

interface TooltipProps {
  active?: boolean
  payload?: { payload: FunnelRow }[]
}

// ─── Tooltip ──────────────────────────────────────────────────────────────────
function FunnelTooltip({ active, payload }: TooltipProps) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="border-4 border-black bg-white px-4 py-3 shadow-[4px_4px_0px_0px_rgba(0,0,0,1)]">
      <div className="text-xs font-black uppercase tracking-wider">{d.label}</div>
      <div className="mt-1 font-mono text-3xl font-black leading-none">{d.count}</div>
      <div className="mt-1 text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
        {d.count === 1 ? "client" : "clients"} in this tier
      </div>
    </div>
  )
}

// ─── Bar fill by tier ─────────────────────────────────────────────────────────
const TIER_FILL: Record<Tier, string> = {
  TIER_3: "#c4c4c4",
  TIER_2: "#000000",
  TIER_1: "var(--primary)",
}

// ─── Component ────────────────────────────────────────────────────────────────
interface PipelineFunnelProps {
  clients: Client[]
}

export function PipelineFunnel({ clients }: PipelineFunnelProps) {
  // Single shared aggregation — same deduplication logic as Dashboard stat cards
  const { byTier, uniqueClientCount: total } = getDashboardSummary(clients)

  // Display order: Cold → Warm → VIP
  const funnelOrder: Tier[] = ["TIER_3", "TIER_2", "TIER_1"]

  const data: FunnelRow[] = funnelOrder.map((tier) => ({
    tier,
    label:
      tier === "TIER_1" ? "TIER 1 · VIP"
      : tier === "TIER_2" ? "TIER 2 · WARM"
      : "TIER 3 · COLD",
    count: byTier[tier],
  }))

  return (
    <ScrollConnect>
      <div className="border-4 border-black bg-white shadow-[8px_8px_0px_0px_rgba(0,0,0,1)]">
        {/* Header */}
        <div className="flex items-center justify-between gap-3 border-b-4 border-black bg-black px-5 py-3.5 sm:px-6">
          <div className="flex items-center gap-2 text-white">
            <BarChart3 className="h-4 w-4" strokeWidth={2.5} />
            <span className="text-xs font-black uppercase tracking-wider sm:text-sm">
              Current Tier Distribution
            </span>
          </div>
          <span className="border-2 border-black bg-primary px-2.5 py-1 text-[10px] font-black uppercase tracking-wider text-black sm:text-xs">
            Live
          </span>
        </div>


        {/* Chart */}
        <div className="h-[320px] p-4 sm:h-[360px] sm:p-6">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={data}
              margin={{ top: 32, right: 8, left: 0, bottom: 8 }}
              barCategoryGap="28%"
            >
              <CartesianGrid stroke="rgba(0,0,0,0.15)" vertical={false} />
              <XAxis
                dataKey="label"
                tick={{ fill: "#000000", fontWeight: 900, fontSize: 11 }}
                axisLine={{ stroke: "#000000", strokeWidth: 3 }}
                tickLine={{ stroke: "#000000", strokeWidth: 2 }}
              />
              <YAxis
                allowDecimals={false}
                tick={{ fill: "#000000", fontWeight: 700, fontSize: 11 }}
                axisLine={{ stroke: "#000000", strokeWidth: 3 }}
                tickLine={{ stroke: "#000000", strokeWidth: 2 }}
                width={36}
              />
              <Tooltip content={<FunnelTooltip />} cursor={{ fill: "rgba(0,0,0,0.06)" }} />
              <Bar
                dataKey="count"
                stroke="#000000"
                strokeWidth={4}
                maxBarSize={140}
                isAnimationActive={true}
                animationDuration={500}
                animationEasing="ease-out"
              >
                <LabelList
                  dataKey="count"
                  position="top"
                  style={{
                    fill: "#000",
                    fontWeight: 900,
                    fontSize: 18,
                    fontFamily: "var(--font-space-mono, monospace)",
                  }}
                />
                {data.map((entry) => (
                  <Cell key={entry.tier} fill={TIER_FILL[entry.tier]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </ScrollConnect>
  )
}
