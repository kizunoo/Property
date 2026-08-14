"use client"

import { useState, type ComponentType } from "react"
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
import { TIER_SHORT, currency, percent, type DeduplicatedClient } from "@/lib/pipeline-data"
import { CountUp } from "@/components/animation/count-up"

// 7-column grid matching header + row cells
const GRID_COLS = "grid-cols-[1.8fr_1.8fr_1fr_1fr_1.2fr_0.8fr_1fr]"

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
    <span className={`inline-flex items-center gap-1.5 ${align === "right" ? "justify-end w-full" : ""}`}>
      <Icon className="h-3.5 w-3.5" strokeWidth={2.5} />
      {children}
    </span>
  )
}

function ClientTableRow({
  client,
  index,
  onSelect,
  handleInvite,
}: {
  client: DeduplicatedClient
  index: number
  onSelect: (client: DeduplicatedClient) => void
  handleInvite: (client: DeduplicatedClient) => void
}) {
  const probPercent = Math.round(client.bestMatch.probability * 100)
  const rowBg = index % 2 === 1 ? "bg-secondary" : "bg-card"

  return (
    <div
      role="row"
      onClick={() => onSelect(client)}
      className={`grid ${GRID_COLS} min-w-[920px] items-stretch cursor-pointer transition-colors hover:bg-primary/20 ${rowBg}`}
    >
      {/* Client name + neighbourhood */}
      <div role="cell" className="flex items-center px-4 py-4 sm:px-5">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center border-2 border-black bg-black text-xs font-black text-white">
            {client.initials}
          </div>
          <div>
            <div className="flex items-center gap-1.5 text-sm font-black leading-tight sm:text-base">
              <UserRound className="h-3.5 w-3.5 shrink-0 text-muted-foreground" strokeWidth={2.5} />
              {client.name}
            </div>
            <div className="font-mono text-[11px] text-muted-foreground">
              {client.bestMatch.neighborhood}
            </div>
          </div>
        </div>
      </div>

      {/* Highest Value Match property + "+N other" indicator */}
      <div role="cell" className="flex items-center px-4 py-4 sm:px-5">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-1.5 text-sm font-bold">
            <MapPin className="h-3 w-3 shrink-0 text-muted-foreground" strokeWidth={2.5} />
            {client.bestMatch.property}
          </div>
          {client.otherMatchCount > 0 && (
            <span className="inline-flex w-fit items-center gap-1 border-2 border-black bg-black px-2 py-0.5 text-[10px] font-black uppercase tracking-wider text-primary">
              <Layers className="h-2.5 w-2.5" strokeWidth={2.5} />
              +{client.otherMatchCount} other listing{client.otherMatchCount > 1 ? "s" : ""}
            </span>
          )}
        </div>
      </div>

      {/* Property value */}
      <div role="cell" className="px-4 py-4 text-right font-mono text-sm font-bold sm:px-5 flex items-center justify-end">
        {currency(client.bestMatch.propertyValue)}
      </div>

      {/* Probability bar */}
      <div role="cell" className="px-4 py-4 sm:px-5 flex items-center justify-end">
        <div className="flex items-center justify-end gap-2">
          <div className="h-2.5 w-16 border-2 border-black bg-white overflow-hidden sm:w-20">
            <div
              className="h-full bg-black prob-bar-anim"
              style={{ width: `${probPercent}%` }}
            />
          </div>
          <span className="w-10 text-right font-mono text-sm font-black">
            {percent(client.bestMatch.probability)}
          </span>
        </div>
      </div>

      {/* Expected value */}
      <div role="cell" className="px-4 py-4 sm:px-5 flex items-center justify-end">
        <span className="inline-flex w-[140px] items-center justify-center border-2 border-black bg-primary px-2 py-1 font-mono text-sm font-black text-black">
          <CountUp
            value={client.bestMatch.expectedValue}
            formatNumber={currency}
          />
        </span>
      </div>

      {/* Tier */}
      <div role="cell" className="px-4 py-4 sm:px-5 flex items-center">
        <TierBadge tier={client.tier} />
      </div>

      {/* Action */}
      <div
        role="cell"
        className="px-4 py-4 sm:px-5 flex items-center"
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
    </div>
  )
}

export function ClientTable({ clients, onGenerateInvite, onSelect }: ClientTableProps) {
  const [invited, setInvited] = useState<Record<string, boolean>>({})
  const [query, setQuery]   = useState("")

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
        role="table"
        aria-label="Client pipeline"
        className="border-4 border-black bg-card shadow-[8px_8px_0px_0px_rgba(0,0,0,1)] overflow-hidden"
      >
        {/* Scrollable container — scroll-x for narrow viewports */}
        <div className="overflow-x-auto scrollbar-none">

          {/* Header */}
          <div
            role="rowgroup"
            className={`grid ${GRID_COLS} min-w-[920px] bg-black text-white border-b-4 border-black`}
          >
            <div role="columnheader" className="px-4 py-3.5 text-left text-xs font-black uppercase tracking-wider sm:px-5">
              <ColumnHeading icon={UserRound}>Client</ColumnHeading>
            </div>
            <div role="columnheader" className="px-4 py-3.5 text-left text-xs font-black uppercase tracking-wider sm:px-5">
              <ColumnHeading icon={Home}>Highest Value Match</ColumnHeading>
            </div>
            <div role="columnheader" className="px-4 py-3.5 text-right text-xs font-black uppercase tracking-wider sm:px-5">
              <ColumnHeading icon={DollarSign} align="right">Property Value</ColumnHeading>
            </div>
            <div role="columnheader" className="px-4 py-3.5 text-right text-xs font-black uppercase tracking-wider sm:px-5">
              <ColumnHeading icon={PercentIcon} align="right">Probability</ColumnHeading>
            </div>
            <div role="columnheader" className="px-4 py-3.5 text-right text-xs font-black uppercase tracking-wider sm:px-5">
              <ColumnHeading icon={TrendingUp} align="right">Expected Value</ColumnHeading>
            </div>
            <div role="columnheader" className="px-4 py-3.5 text-left text-xs font-black uppercase tracking-wider sm:px-5">
              <ColumnHeading icon={Tags}>Segment</ColumnHeading>
            </div>
            <div role="columnheader" className="px-4 py-3.5 text-left text-xs font-black uppercase tracking-wider sm:px-5">
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
              />
            ))}
          </div>

        </div>
      </div>
    </div>
  )
}
