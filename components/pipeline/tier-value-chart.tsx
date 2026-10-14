"use client"

import { Treemap, ResponsiveContainer, Tooltip } from "recharts"
import { LayoutDashboard } from "lucide-react"
import { currency, getDashboardSummary, type Client, type Tier } from "@/lib/pipeline-data"

import { ScrollConnect } from "@/components/animation/scroll-connect"
import { useChartInsight, ChartInsightPanel } from "./chart-insight-panel"


const TIER_ORDER: Tier[] = ["TIER_1", "TIER_2", "TIER_3"]

const TIER_META: Record<Tier, { label: string; shortLabel: string; fill: string; textColor: string }> = {
  TIER_1: { label: "TIER 1 · HIGH-FIT PROSPECT", shortLabel: "HIGH-FIT", fill: "var(--primary)", textColor: "#000000" },
  TIER_2: { label: "TIER 2 · POSSIBLE-FIT",      shortLabel: "POSSIBLE", fill: "#1a1a1a",        textColor: "#ffffff" },
  TIER_3: { label: "TIER 3 · LOW-FIT",           shortLabel: "LOW-FIT",  fill: "#c4c4c4",        textColor: "#000000" },
}

// ─── Tooltip ─────────────────────────────────────────────────────────────────
interface TooltipPayload {
  active?: boolean
  payload?: { payload: { label: string; value: number; count: number } }[]
}

function TreeTooltip({ active, payload }: TooltipPayload) {
  if (!active || !payload?.length) return null
  const item = payload[0].payload
  return (
    <div className="rounded-lg border border-neutral-200 bg-white px-4 py-3 shadow-[0px_4px_16px_rgba(0,0,0,0.12)]">
      <div className="text-xs font-semibold uppercase tracking-wider">{item.label}</div>
      <div className="mt-1 font-mono text-lg font-bold">{currency(item.value)}</div>
      <div className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
        {item.count} {item.count === 1 ? "company" : "companies"}
      </div>
    </div>
  )
}

// ─── Custom treemap cell renderer ─────────────────────────────────────────────
interface TreeCellProps {
  x?: number
  y?: number
  width?: number
  height?: number
  tier?: Tier
  value?: number
  count?: number
  onTierClick?: (tier: Tier) => void
}

function TreeCell({ x = 0, y = 0, width = 0, height = 0, tier, value, count, onTierClick }: TreeCellProps) {
  if (!tier || width < 2 || height < 2) return null
  const meta = TIER_META[tier]

  // Gap between segments: inset each cell by 3px on each side
  const gap = 3
  const rx = x + gap
  const ry = y + gap
  const rw = Math.max(0, width - gap * 2)
  const rh = Math.max(0, height - gap * 2)

  const cx = x + width / 2
  const cy = y + height / 2

  // Dimension categories
  const isTiny = width < 35 || height < 25
  const isCompactWidth = width < 90
  const isNarrow = width < 65
  const isShort = height < 52

  // Formatted labels
  const labelText = meta.shortLabel
  const valueText = value !== undefined ? currency(value) : null
  const countText = count !== undefined
    ? (isNarrow && width < 58
        ? `${count} ${count === 1 ? "co" : "cos"}`
        : `${count} ${count === 1 ? "company" : "companies"}`)
    : null

  return (
    <g style={{ cursor: onTierClick ? "pointer" : "default" }} onClick={() => onTierClick?.(tier)}>
      {/* Soft gap achieved by insetting rect; thin 1px stroke instead of heavy 3px */}
      <rect x={rx} y={ry} width={rw} height={rh} fill={meta.fill} stroke="rgba(255,255,255,0.25)" strokeWidth={1} rx={4} ry={4} />

      {!isTiny && (
        <>
          {/* Layout A: Wide horizontal strip */}
          {isShort && width >= 120 ? (
            width >= 210 ? (
              <text
                x={cx}
                y={cy}
                textAnchor="middle"
                dominantBaseline="middle"
                fill={meta.textColor}
                fontSize={10.5}
                fontWeight={700}
                fontFamily="var(--font-sans)"
                style={{ userSelect: "none" }}
              >
                {labelText}
                {valueText ? ` · ${valueText}` : ""}
                {countText ? ` · ${countText}` : ""}
              </text>
            ) : (
              <>
                <text
                  x={cx}
                  y={cy - 7}
                  textAnchor="middle"
                  dominantBaseline="middle"
                  fill={meta.textColor}
                  fontSize={9.5}
                  fontWeight={700}
                  fontFamily="var(--font-sans)"
                  style={{ userSelect: "none", textTransform: "uppercase", letterSpacing: "0.05em" }}
                >
                  {labelText}
                  {valueText ? `: ${valueText}` : ""}
                </text>
                {countText && (
                  <text
                    x={cx}
                    y={cy + 7}
                    textAnchor="middle"
                    dominantBaseline="middle"
                    fill={meta.textColor}
                    fontSize={8.5}
                    fontWeight={600}
                    fontFamily="var(--font-sans)"
                    opacity={0.8}
                    style={{ userSelect: "none", textTransform: "uppercase", letterSpacing: "0.05em" }}
                  >
                    {countText}
                  </text>
                )}
              </>
            )
          ) : (
            /* Layout B: Standard or Tall Vertical Block (including narrow Low-Fit bar) */
            <>
              {/* Tier Label */}
              <text
                x={cx}
                y={cy - 14}
                textAnchor="middle"
                dominantBaseline="middle"
                fill={meta.textColor}
                fontSize={isNarrow ? 9 : isCompactWidth ? 10.5 : 13}
                fontWeight={700}
                fontFamily="var(--font-sans)"
                style={{ userSelect: "none", textTransform: "uppercase", letterSpacing: isNarrow ? "0.03em" : "0.08em" }}
              >
                {labelText}
              </text>

              {/* RM Value */}
              {valueText && (
                <text
                  x={cx}
                  y={isCompactWidth ? cy + 1 : cy + 4}
                  textAnchor="middle"
                  dominantBaseline="middle"
                  fill={meta.textColor}
                  fontSize={isNarrow ? 9 : isCompactWidth ? 10.5 : 11}
                  fontWeight={600}
                  fontFamily="var(--font-sans)"
                  opacity={0.9}
                  style={{ userSelect: "none", letterSpacing: isNarrow ? "0" : undefined }}
                >
                  {valueText}
                </text>
              )}

              {/* Company Count */}
              {countText && (
                <text
                  x={cx}
                  y={isCompactWidth ? cy + 16 : cy + 22}
                  textAnchor="middle"
                  dominantBaseline="middle"
                  fill={meta.textColor}
                  fontSize={isNarrow ? 8 : isCompactWidth ? 9.5 : 10}
                  fontWeight={600}
                  fontFamily="var(--font-sans)"
                  opacity={0.75}
                  style={{ userSelect: "none", textTransform: "uppercase", letterSpacing: isNarrow ? "0.01em" : "0.06em" }}
                >
                  {countText}
                </text>
              )}
            </>
          )}
        </>
      )}
    </g>
  )
}

// ─── Component ────────────────────────────────────────────────────────────────
interface TierValueChartProps {
  clients: Client[]
  onTierClick?: (tier: Tier) => void
}

export function TierValueChart({ clients, onTierClick }: TierValueChartProps) {
  const { insight, loading, fetchInsight } = useChartInsight()
  // Single shared aggregation — same deduplication logic as Dashboard stat cards
  const { byTier, byTierEx } = getDashboardSummary(clients)

  const rawData = TIER_ORDER.map((tier) => ({
    tier,
    label: TIER_META[tier].label,
    value: byTierEx[tier],
    count: byTier[tier],
  })).filter((d) => d.value > 0)

  const treeChildren = rawData.map((d) => ({ ...d, name: d.label, size: d.value }))

  const handleCellClick = (tier: Tier) => {
    fetchInsight("tier", { tier })
    if (onTierClick) onTierClick(tier)
  }

  return (
    <ScrollConnect>
      <div className="overflow-hidden rounded-[var(--radius)] border border-border bg-card shadow-[var(--shadow-sm)]">
        <div className="flex items-center justify-between gap-3 border-b border-border bg-transparent px-5 py-3.5 sm:px-6">
          <div className="flex items-center gap-2 text-foreground">
            <LayoutDashboard className="h-4 w-4 text-muted-foreground" strokeWidth={2} />
            <span className="text-xs font-bold uppercase tracking-wider text-foreground sm:text-sm">
              Expected Value by Fit-Tier
            </span>
          </div>
          <span className="rounded-[var(--radius-sm)] border border-border bg-muted px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground sm:text-xs">
            Click segment for AI analysis
          </span>
        </div>

        <div className="p-4 sm:p-5">
          <div className="h-[280px] sm:h-[300px]">
            <ResponsiveContainer width="100%" height="100%">
              <Treemap
                data={treeChildren}
                dataKey="size"
                aspectRatio={4 / 3}
                isAnimationActive={true}
                animationDuration={600}
                animationEasing="ease-out"
                content={<TreeCell onTierClick={handleCellClick} />}
              >
                <Tooltip content={<TreeTooltip />} />
              </Treemap>
            </ResponsiveContainer>
          </div>
          <ChartInsightPanel insight={insight} loading={loading} />
        </div>
      </div>
    </ScrollConnect>
  )
}
