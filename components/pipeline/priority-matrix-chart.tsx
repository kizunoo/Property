"use client"

import {
  CartesianGrid,
  ResponsiveContainer,
  ScatterChart,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
  ReferenceLine,
} from "recharts"
import { Crosshair } from "lucide-react"
import { currency, percent, type Client } from "@/lib/pipeline-data"
import { ScrollConnect } from "@/components/animation/scroll-connect"
import { useChartInsight, ChartInsightPanel } from "./chart-insight-panel"

// ─── Custom square scatter shape ─────────────────────────────────────────────
interface SquareDotProps {
  cx?: number
  cy?: number
  fill?: string
  payload?: ScatterPoint
  onClick?: (payload: ScatterPoint) => void
}

function SquareDot({ cx = 0, cy = 0, payload, onClick }: SquareDotProps) {
  const tierFill =
    payload?.tier === "TIER_1"
      ? "var(--primary)"
      : payload?.tier === "TIER_2"
        ? "#000000"
        : "#c4c4c4"

  const size = 14
  return (
    <rect
      x={cx - size / 2}
      y={cy - size / 2}
      width={size}
      height={size}
      fill={tierFill}
      stroke="#000000"
      strokeWidth={2.5}
      style={{ cursor: "pointer" }}
      onClick={() => payload && onClick?.(payload)}
    />
  )
}

// ─── Tooltip ─────────────────────────────────────────────────────────────────
interface ScatterPoint {
  clientId: string
  propertyId: string
  name: string
  neighborhood: string
  probability: number
  propertyValue: number
  expectedValue: number
  tier: string
}

interface TooltipProps {
  active?: boolean
  payload?: { payload: ScatterPoint }[]
}

function MatrixTooltip({ active, payload }: TooltipProps) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="border border-neutral-200 bg-white px-4 py-3 shadow-[0px_2px_8px_rgba(0,0,0,0.08)]">
      {/* Client name — prominent */}
      <div className="text-sm font-black uppercase tracking-wider">{d.name}</div>
      <div className="mb-2 text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
        {d.neighborhood}
      </div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1">
        <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">P(Buy)</span>
        <span className="text-right font-mono text-sm font-black">{percent(d.probability / 100)}</span>
        <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Property</span>
        <span className="text-right font-mono text-sm font-black">{currency(d.propertyValue)}</span>
        <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">E(x)</span>
        <span className="text-right font-mono text-sm font-black">{currency(d.expectedValue)}</span>
      </div>
      <div className="mt-2 border-t-2 border-black pt-2 text-[10px] font-black uppercase tracking-wider">
        {d.tier.replace("_", " ")} · Click dot for AI analysis
      </div>
    </div>
  )
}

// ─── Component ────────────────────────────────────────────────────────────────
interface PriorityMatrixChartProps {
  clients: Client[]
}

export function PriorityMatrixChart({ clients }: PriorityMatrixChartProps) {
  const { insight, loading, fetchInsight } = useChartInsight()

  const data: ScatterPoint[] = clients.map((c) => ({
    clientId: c.clientDbId || c.id,
    propertyId: c.propertyDbId || c.id,
    name: c.name,
    neighborhood: c.agent,
    probability: Math.round(c.probability * 100),   // 0–100 for X axis
    propertyValue: c.propertyValue,
    expectedValue: c.expectedValue,
    tier: c.tier,
  }))

  const handlePointClick = (pt: ScatterPoint) => {
    fetchInsight("scatter_point", { client_id: pt.clientId, property_id: pt.propertyId })
  }

  return (
    <ScrollConnect>
      <div className="border border-neutral-200 bg-white shadow-[0px_4px_16px_rgba(0,0,0,0.10)]">

      {/* Header */}
      <div className="flex items-center justify-between gap-3 border-b border-neutral-200 bg-black px-5 py-3.5 sm:px-6">
        <div className="flex items-center gap-2 text-white">
          <Crosshair className="h-4 w-4" strokeWidth={2.5} />
          <span className="text-xs font-black uppercase tracking-wider sm:text-sm">
            Priority Matrix · P(Buy) vs Property Value
          </span>
        </div>
        <span className="border border-neutral-200 bg-primary px-2.5 py-1 text-[10px] font-black uppercase tracking-wider text-black sm:text-xs">
          Click dot for AI analysis
        </span>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap items-center gap-4 border-b border-neutral-200 px-5 py-2.5">
        {(["TIER_1", "TIER_2", "TIER_3"] as const).map((tier) => {
          const fill =
            tier === "TIER_1" ? "var(--primary)" : tier === "TIER_2" ? "#000" : "#c4c4c4"
          const label = tier === "TIER_1" ? "VIP" : tier === "TIER_2" ? "WARM" : "COLD"
          return (
            <span key={tier} className="flex items-center gap-1.5 text-[10px] font-black uppercase tracking-wider">
              <span
                className="inline-block h-3 w-3 border border-neutral-200"
                style={{ background: fill }}
              />
              {label}
            </span>
          )
        })}
        <span className="ml-auto text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
          Click dot to analyze
        </span>
      </div>

      {/* Chart */}
      <div className="p-4 sm:p-6">
        <div className="h-[340px] sm:h-[380px]">
          <ResponsiveContainer width="100%" height="100%">
            <ScatterChart margin={{ top: 10, right: 16, left: 0, bottom: 10 }}>
              <CartesianGrid stroke="rgba(0,0,0,0.12)" strokeDasharray="0" />

              {/* VIP threshold line */}
              <ReferenceLine
                x={65}
                stroke="#000"
                strokeWidth={2}
                strokeDasharray="6 3"
                label={{ value: "65%", fill: "#000", fontSize: 10, fontWeight: 900 }}
              />

              <XAxis
                dataKey="probability"
                type="number"
                domain={[0, 100]}
                tickFormatter={(v: number) => `${v}%`}
                tick={{ fill: "#000000", fontWeight: 900, fontSize: 11 }}
                axisLine={{ stroke: "#000000", strokeWidth: 3 }}
                tickLine={{ stroke: "#000000", strokeWidth: 2 }}
                label={{
                  value: "P(Buy) Probability →",
                  position: "insideBottomRight",
                  offset: -8,
                  fill: "#000",
                  fontSize: 10,
                  fontWeight: 900,
                }}
              />
              <YAxis
                dataKey="propertyValue"
                type="number"
                tickFormatter={(v: number) => `RM${(v / 1_000_000).toFixed(1)}M`}
                tick={{ fill: "#000000", fontWeight: 700, fontSize: 11 }}
                axisLine={{ stroke: "#000000", strokeWidth: 3 }}
                tickLine={{ stroke: "#000000", strokeWidth: 2 }}
                width={60}
                label={{
                  value: "Property Value",
                  angle: -90,
                  position: "insideLeft",
                  offset: 12,
                  fill: "#000",
                  fontSize: 10,
                  fontWeight: 900,
                }}
              />

              <Tooltip
                content={<MatrixTooltip />}
                cursor={{ stroke: "#000", strokeWidth: 1, strokeDasharray: "4 2" }}
              />

              <Scatter
                data={data}
                shape={<SquareDot onClick={handlePointClick} />}
                isAnimationActive={true}
                animationDuration={600}
                animationEasing="ease-out"
                animationBegin={0}
              />
            </ScatterChart>
          </ResponsiveContainer>
        </div>
        <ChartInsightPanel insight={insight} loading={loading} />
      </div>
    </div>
    </ScrollConnect>
  )
}
