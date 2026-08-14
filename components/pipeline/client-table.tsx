"use client"

import { useCallback, useEffect, useRef, useState, type ComponentType } from "react"
import {
  CheckCircle2,
  DollarSign,
  Home,
  Layers,
  MapPin,
  Search,
  Send,
  Tags,
  TrendingUp,
  UserRound,
  Percent as PercentIcon,
} from "lucide-react"
import { gsap } from "gsap"
import { ScrollTrigger } from "gsap/ScrollTrigger"
import { TIER_SHORT, currency, percent, type DeduplicatedClient } from "@/lib/pipeline-data"
import { CountUp } from "@/components/animation/count-up"
import { RowConnect } from "@/components/animation/row-connect"

gsap.registerPlugin(ScrollTrigger)

// 7-column grid matching header + row cells.
// Every track uses minmax(0, Nfr) — without the minmax(0, …) floor, a track's
// implicit minimum is "auto" (its content's natural width), so columns in one
// row can end up a different width than the same column in another row once
// content lengths differ. Since each row is its own independent grid (they
// need to be, to animate individually), that mismatch is what caused the
// columns to drift out of alignment between rows.
const GRID_COLS =
  "grid-cols-[minmax(0,1.8fr)_minmax(0,1.8fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1.2fr)_minmax(0,0.8fr)_minmax(0,1fr)]"

interface ClientTableProps {
  clients: DeduplicatedClient[]
  onGenerateInvite: (client: DeduplicatedClient) => void
  onSelect: (client: DeduplicatedClient) => void
}

function TierBadge({ tier }: { tier: DeduplicatedClient["tier"] }) {
  const styles: Record<DeduplicatedClient["tier"], string> = {
    TIER_1: "bg-primary text-black",
    TIER_2: "bg-black text-white",
    TIER_3: "bg-white text-black",
  }
  return (
    <span
      className={`inline-block border-2 border-black px-2.5 py-1 text-[10px] sm:text-xs font-black uppercase tracking-wider ${styles[tier]}`}
    >
      {TIER_SHORT[tier]}
    </span>
  )
}

function ColumnHeading({
  icon: Icon,
  children,
  align = "left",
}: {
  icon: ComponentType<{ className?: string; strokeWidth?: number }>
  children: React.ReactNode
  align?: "left" | "right"
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 whitespace-nowrap ${align === "right" ? "justify-end w-full" : ""}`}
    >
      <Icon className="h-3.5 w-3.5 shrink-0" strokeWidth={2.5} />
      {children}
    </span>
  )
}

function ClientTableRow({
  client,
  index,
  onSelect,
  handleInvite,
  onHeightChange,
  onProgress,
  onUnregister,
}: {
  client: DeduplicatedClient
  index: number
  onSelect: (client: DeduplicatedClient) => void
  handleInvite: (client: DeduplicatedClient) => void
  onHeightChange: (id: string, height: number) => void
  onProgress: (id: string, progress: number) => void
  onUnregister: (id: string) => void
}) {
  const probPercent = Math.round(client.bestMatch.probability * 100)
  const rowBg = index % 2 === 1 ? "bg-secondary" : "bg-card"
  const hasOtherMatches = client.otherMatchCount > 0

  return (
    <RowConnect
      id={client.clientId}
      onClick={() => onSelect(client)}
      onHeightChange={onHeightChange}
      onProgress={onProgress}
      onUnregister={onUnregister}
      className={`grid ${GRID_COLS} min-w-[920px] min-h-[76px] items-stretch cursor-pointer transition-colors hover:bg-primary/20 ${rowBg}`}
    >
      {/* Client name + neighbourhood */}
      <div role="cell" className="flex min-w-0 items-center px-4 py-4 sm:px-5">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center border-2 border-black bg-black text-xs font-black text-white">
            {client.initials}
          </div>
          <div className="min-w-0">
            <div className="flex min-w-0 items-center gap-1.5 text-sm font-black leading-tight sm:text-base">
              <UserRound className="h-3.5 w-3.5 shrink-0 text-muted-foreground" strokeWidth={2.5} />
              <span className="truncate">{client.name}</span>
            </div>
            <div className="truncate font-mono text-[11px] text-muted-foreground">
              {client.bestMatch.neighborhood}
            </div>
          </div>
        </div>
      </div>

      {/* Highest Value Match property + "+N other" indicator */}
      <div role="cell" className="flex min-w-0 items-center px-4 py-4 sm:px-5">
        <div className="flex min-w-0 flex-col gap-1">
          <div className="flex min-w-0 items-center gap-1.5 text-sm font-bold">
            <MapPin className="h-3 w-3 shrink-0 text-muted-foreground" strokeWidth={2.5} />
            <span className="truncate">{client.bestMatch.property}</span>
          </div>
          <span
            className={`inline-flex w-fit items-center gap-1 border-2 border-black bg-black px-2 py-0.5 text-[10px] font-black uppercase tracking-wider text-primary ${
              hasOtherMatches ? "" : "invisible"
            }`}
          >
            <Layers className="h-2.5 w-2.5 shrink-0" strokeWidth={2.5} />
            +{client.otherMatchCount || 1} other listing{client.otherMatchCount > 1 ? "s" : ""}
          </span>
        </div>
      </div>

      {/* Property value */}
      <div role="cell" className="flex items-center justify-end px-4 py-4 text-right font-mono text-sm font-bold sm:px-5">
        {currency(client.bestMatch.propertyValue)}
      </div>

      {/* Probability bar */}
      <div role="cell" className="flex items-center justify-end px-4 py-4 sm:px-5">
        <div className="flex items-center justify-end gap-2">
          <div className="h-2.5 w-16 shrink-0 border-2 border-black bg-white overflow-hidden sm:w-20">
            <div
              className="h-full bg-black prob-bar-anim"
              style={{ width: `${probPercent}%` }}
            />
          </div>
          <span className="w-10 shrink-0 text-right font-mono text-sm font-black">
            {percent(client.bestMatch.probability)}
          </span>
        </div>
      </div>

      {/* Expected value */}
      <div role="cell" className="flex items-center justify-end px-4 py-4 sm:px-5">
        <span className="inline-flex w-[140px] shrink-0 items-center justify-center border-2 border-black bg-primary px-2 py-1 font-mono text-sm font-black text-black">
          <CountUp
            value={client.bestMatch.expectedValue}
            formatNumber={currency}
          />
        </span>
      </div>

      {/* Tier */}
      <div role="cell" className="flex items-center px-4 py-4 sm:px-5">
        <TierBadge tier={client.tier} />
      </div>

      {/* Action */}
      <div
        role="cell"
        className="flex items-center px-4 py-4 sm:px-5"
        onClick={(e) => e.stopPropagation()}
      >
        {client.tier === "TIER_1" || client.tier === "TIER_2" ? (
          <button
            type="button"
            onClick={() => handleInvite(client)}
            className="flex items-center gap-1.5 whitespace-nowrap border-2 border-black bg-black text-white px-3 py-2 text-xs font-black uppercase tracking-wider shadow-[3px_3px_0px_0px_rgba(0,0,0,1)] transition-transform hover:translate-x-0.5 hover:translate-y-0.5 hover:shadow-none"
          >
            <Send className="h-3.5 w-3.5 text-primary" strokeWidth={2.5} />
            Generate Invite
          </button>
        ) : (
          <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">—</span>
        )}
      </div>
    </RowConnect>
  )
}

export function ClientTable({ clients, onGenerateInvite, onSelect }: ClientTableProps) {
  const [invited, setInvited] = useState<Record<string, boolean>>({})
  const [query, setQuery] = useState("")

  const tableRef = useRef<HTMLDivElement>(null)
  const headerRef = useRef<HTMLDivElement>(null)
  const rowHeights = useRef<Map<string, number>>(new Map())
  const rowProgress = useRef<Map<string, number>>(new Map())

  // The table's own border/shadow box is only ever as tall as the header plus
  // whatever rows have actually "connected" so far — never the full 28-row
  // height up front. Rows that haven't connected yet simply overflow below
  // this box (overflow is visible, not hidden) and read as floating cards
  // outside the table, not as content trapped inside a slot the table has
  // already claimed.
  const recomputeHeight = useCallback(() => {
    const table = tableRef.current
    const header = headerRef.current
    if (!table || !header) return
    let total = header.offsetHeight
    rowHeights.current.forEach((height, id) => {
      const progress = rowProgress.current.get(id) ?? 0
      total += height * progress
    })
    table.style.height = `${Math.max(total, header.offsetHeight)}px`
  }, [])

  const handleRowHeight = useCallback(
    (id: string, height: number) => {
      rowHeights.current.set(id, height)
      recomputeHeight()
    },
    [recomputeHeight],
  )

  const handleRowProgress = useCallback(
    (id: string, progress: number) => {
      rowProgress.current.set(id, progress)
      recomputeHeight()
    },
    [recomputeHeight],
  )

  const handleRowUnregister = useCallback(
    (id: string) => {
      rowHeights.current.delete(id)
      rowProgress.current.delete(id)
      recomputeHeight()
    },
    [recomputeHeight],
  )

  const visible = query.trim()
    ? clients.filter((c) => {
        const q = query.toLowerCase()
        return (
          c.name.toLowerCase().includes(q) ||
          c.clientId.toLowerCase().includes(q) ||
          c.bestMatch.property.toLowerCase().includes(q) ||
          c.bestMatch.neighborhood.toLowerCase().includes(q)
        )
      })
    : clients

  // Whenever the visible row set changes (initial mount, search filtering),
  // force GSAP to re-sync every row's connect progress with the current
  // scroll position, so rows already past the "connect" line render as
  // connected immediately instead of waiting for the next scroll tick.
  useEffect(() => {
    const raf = requestAnimationFrame(() => ScrollTrigger.refresh())
    return () => cancelAnimationFrame(raf)
  }, [visible.length, query])

  function handleInvite(client: DeduplicatedClient) {
    setInvited((prev) => ({ ...prev, [client.clientId]: true }))
    onGenerateInvite(client)
  }

  return (
    <div className="flex flex-col gap-3">
      {/* ── Search bar ── */}
      <div className="relative">
        <Search
          className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
          strokeWidth={2.5}
        />
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search by client name, property, or neighbourhood..."
          className="w-full border-4 border-black bg-white py-3 pl-10 pr-4 font-mono text-sm font-bold placeholder:font-sans placeholder:font-bold placeholder:text-muted-foreground shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] outline-none transition-shadow focus:shadow-none focus:translate-x-0.5 focus:translate-y-0.5"
        />
      </div>

      {/* ── Grid table ── */}
      <div
        ref={tableRef}
        role="table"
        aria-label="Client pipeline"
        className="border-4 border-black bg-card shadow-[8px_8px_0px_0px_rgba(0,0,0,1)] overflow-visible"
      >
        {/* Scrollable container — scroll-x for narrow viewports.
            Vertical overflow stays visible so unconnected rows can spill
            below the table's currently-grown boundary instead of being
            clipped. */}
        <div className="overflow-x-auto overflow-y-visible scrollbar-none">

          {/* Header */}
          <div
            ref={headerRef}
            role="rowgroup"
            className={`grid ${GRID_COLS} min-w-[920px] bg-black text-white border-b-4 border-black`}
          >
            <div role="columnheader" className="min-w-0 px-4 py-3.5 text-left text-xs font-black uppercase tracking-wider sm:px-5">
              <ColumnHeading icon={UserRound}>Client</ColumnHeading>
            </div>
            <div role="columnheader" className="min-w-0 px-4 py-3.5 text-left text-xs font-black uppercase tracking-wider sm:px-5">
              <ColumnHeading icon={Home}>Highest Value Match</ColumnHeading>
            </div>
            <div role="columnheader" className="min-w-0 px-4 py-3.5 text-right text-xs font-black uppercase tracking-wider sm:px-5">
              <ColumnHeading icon={DollarSign} align="right">Property Value</ColumnHeading>
            </div>
            <div role="columnheader" className="min-w-0 px-4 py-3.5 text-right text-xs font-black uppercase tracking-wider sm:px-5">
              <ColumnHeading icon={PercentIcon} align="right">Probability</ColumnHeading>
            </div>
            <div role="columnheader" className="min-w-0 px-4 py-3.5 text-right text-xs font-black uppercase tracking-wider sm:px-5">
              <ColumnHeading icon={TrendingUp} align="right">Expected Value</ColumnHeading>
            </div>
            <div role="columnheader" className="min-w-0 px-4 py-3.5 text-left text-xs font-black uppercase tracking-wider sm:px-5">
              <ColumnHeading icon={Tags}>Segment</ColumnHeading>
            </div>
            <div role="columnheader" className="min-w-0 px-4 py-3.5 text-left text-xs font-black uppercase tracking-wider sm:px-5">
              <ColumnHeading icon={Send}>Action</ColumnHeading>
            </div>
          </div>

          {/* Rows */}
          <div role="rowgroup">
            {visible.length === 0 && (
              <div
                role="row"
                className="px-5 py-10 text-center text-xs font-black uppercase tracking-wider text-muted-foreground"
              >
                No clients match &ldquo;{query}&rdquo;
              </div>
            )}
            {visible.map((client, index) => (
              <ClientTableRow
                key={client.clientId}
                client={client}
                index={index}
                onSelect={onSelect}
                handleInvite={handleInvite}
                onHeightChange={handleRowHeight}
                onProgress={handleRowProgress}
                onUnregister={handleRowUnregister}
              />
            ))}
          </div>

        </div>
      </div>
    </div>
  )
}
