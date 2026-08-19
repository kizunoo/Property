"use client"

import { useState, useEffect, useRef, type ComponentType } from "react"
import {
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

// ─── Column layout comment ────────────────────────────────────────────────────
//
//  The grid template lives in globals.css → .client-entity-inner
//  grid-template-columns: 220px 1fr 140px 160px 170px 96px 180px
//  gap: 28px
//
//  Column order: Client | Best Match | Prop. Value | Probability | E(x) | Segment | Action
//
//  The sticky header row uses the exact same template so labels align over every card.

// ─── Sub-components ───────────────────────────────────────────────────────────

function TierBadge({ tier }: { tier: DeduplicatedClient["tier"] }) {
  const styles: Record<DeduplicatedClient["tier"], string> = {
    TIER_1: "bg-primary text-black",
    TIER_2: "bg-black text-white",
    TIER_3: "bg-white text-black",
  }
  return (
    <span
      className={`inline-flex w-[72px] items-center justify-center border-2 border-black py-1 text-[10px] font-black uppercase tracking-wider ${styles[tier]}`}
    >
      {TIER_SHORT[tier]}
    </span>
  )
}

function ColHead({
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
      className={`inline-flex items-center gap-1.5 text-xs font-black uppercase tracking-wider ${
        align === "right" ? "justify-end w-full" : ""
      }`}
    >
      <Icon className="h-3.5 w-3.5 shrink-0" strokeWidth={2.5} />
      <span>{children}</span>
    </span>
  )
}

// ─── Entity Card ─────────────────────────────────────────────────────────────

function ClientEntity({
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
  const innerRef = useRef<HTMLDivElement>(null)

  // IntersectionObserver drives .is-visible — no GSAP, no scrub
  useEffect(() => {
    const el = innerRef.current
    if (!el) return
    const observer = new IntersectionObserver(
      ([entry]) => {
        el.classList.toggle("is-visible", entry.isIntersecting)
      },
      { threshold: 0.15 },
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  return (
    <div
      className={`client-entity${index % 2 === 1 ? " entity-alt" : ""}`}
    >
      <div
        ref={innerRef}
        className="client-entity-inner cursor-pointer hover:bg-primary/10 transition-colors"
        onClick={() => onSelect(client)}
      >
        {/* 1 · Client */}
        <div className="flex items-center gap-3 min-w-0">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center border-2 border-black bg-black text-xs font-black text-white">
            {client.initials}
          </div>
          <div className="min-w-0 flex-1">
            <div
              className="flex items-center gap-1 text-sm font-black leading-tight min-w-0"
              title={client.name}
            >
              <UserRound className="h-3.5 w-3.5 shrink-0 text-muted-foreground" strokeWidth={2.5} />
              <span className="truncate">{client.name}</span>
            </div>
            <div
              className="font-mono text-[11px] text-muted-foreground truncate"
              title={client.bestMatch.neighborhood}
            >
              {client.bestMatch.neighborhood}
            </div>
          </div>
        </div>

        {/* 2 · Highest Value Match */}
        <div
          className="flex flex-col justify-center gap-0.5 min-w-0"
          title={client.bestMatch.property}
        >
          <div className="flex items-center gap-1 text-sm font-bold min-w-0">
            <MapPin className="h-3 w-3 shrink-0 text-muted-foreground" strokeWidth={2.5} />
            <span className="truncate">{client.bestMatch.property}</span>
          </div>
          {client.otherMatchCount > 0 && (
            <span className="inline-flex w-fit items-center gap-1 border-2 border-black bg-black px-2 py-0.5 text-[10px] font-black uppercase tracking-wider text-primary">
              <Layers className="h-2.5 w-2.5 shrink-0" strokeWidth={2.5} />
              +{client.otherMatchCount} other listing{client.otherMatchCount > 1 ? "s" : ""}
            </span>
          )}
        </div>

        {/* 3 · Property Value */}
        <div className="flex items-center justify-end font-mono text-sm font-bold">
          <span className="truncate">{currency(client.bestMatch.propertyValue)}</span>
        </div>

        {/* 4 · Probability */}
        <div className="flex items-center justify-end gap-2">
          <div className="h-2.5 w-20 border-2 border-black bg-white overflow-hidden shrink-0">
            <div
              className="h-full bg-black prob-bar-anim"
              style={{ width: `${probPercent}%` }}
            />
          </div>
          <span className="w-8 text-right font-mono text-sm font-black shrink-0">
            {percent(client.bestMatch.probability)}
          </span>
        </div>

        {/* 5 · Expected Value */}
        <div className="flex items-center justify-end">
          <span className="inline-flex w-[148px] items-center justify-center border-2 border-black bg-primary px-2 py-1 font-mono text-sm font-black text-black shrink-0">
            <CountUp value={client.bestMatch.expectedValue} formatNumber={currency} />
          </span>
        </div>

        {/* 6 · Segment */}
        <div className="flex items-center gap-1.5 pl-2 flex-wrap">
          <TierBadge tier={client.tier} />
          {client.bestMatch.outcome === "won" && (
            <span className="inline-flex items-center border-2 border-black bg-primary px-1.5 py-0.5 text-[9px] font-black uppercase tracking-wider text-black">
              ✓ WON
            </span>
          )}
          {client.bestMatch.outcome === "lost" && (
            <span className="inline-flex items-center border-2 border-black bg-white px-1.5 py-0.5 text-[9px] font-black uppercase tracking-wider text-black">
              ✕ LOST
            </span>
          )}
        </div>

        {/* 7 · Action */}
        <div
          className="flex items-center"
          onClick={(e) => e.stopPropagation()}
        >
          {client.tier === "TIER_1" || client.tier === "TIER_2" ? (
            <button
              type="button"
              onClick={() => handleInvite(client)}
              className="flex items-center gap-1.5 whitespace-nowrap border-2 border-black bg-black text-white px-3 py-2 text-xs font-black uppercase tracking-wider shadow-[3px_3px_0px_0px_rgba(0,0,0,1)] transition-transform hover:translate-x-0.5 hover:translate-y-0.5 hover:shadow-none"
            >
              <Send className="h-3.5 w-3.5 text-primary shrink-0" strokeWidth={2.5} />
              Generate Invite
            </button>
          ) : (
            <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">—</span>
          )}
        </div>
      </div>
    </div>
  )
}

// ─── Sticky header row ────────────────────────────────────────────────────────
//
//  Uses inline style to mirror .client-entity-inner's grid-template-columns and gap
//  exactly — keeping header labels pinned over each card column.

const HEADER_GRID: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "220px 1fr 140px 160px 170px 96px 180px",
  gap: "28px",
  alignItems: "center",
  minWidth: 1040,
  padding: "12px 20px",
}

function TableHeader() {
  return (
    <div
      className="bg-black text-white border-4 border-black mb-2 sticky top-0 z-10"
      style={HEADER_GRID}
    >
      <ColHead icon={UserRound}>Client</ColHead>
      <ColHead icon={Home}>Highest Value Match</ColHead>
      <div className="flex justify-end"><ColHead icon={DollarSign} align="right">Property Value</ColHead></div>
      <div className="flex justify-end"><ColHead icon={PercentIcon} align="right">Probability</ColHead></div>
      <div className="flex justify-end"><ColHead icon={TrendingUp} align="right">Expected Value</ColHead></div>
      <div className="pl-2"><ColHead icon={Tags}>Segment</ColHead></div>
      <ColHead icon={Send}>Action</ColHead>
    </div>
  )
}

// ─── Table root ───────────────────────────────────────────────────────────────

interface ClientTableProps {
  clients: DeduplicatedClient[]
  onGenerateInvite: (client: DeduplicatedClient) => void
  onSelect: (client: DeduplicatedClient) => void
}

export function ClientTable({ clients, onGenerateInvite, onSelect }: ClientTableProps) {
  const [query, setQuery] = useState("")

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
    onGenerateInvite(client)
  }

  return (
    <div className="flex flex-col gap-3">
      {/* Search bar */}
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

      {/* Horizontal scroll wrapper — only triggers on viewports < 960 px */}
      <div className="overflow-x-auto">
        {/* Sticky header */}
        <TableHeader />

        {/* Entity cards */}
        {visible.length === 0 ? (
          <div className="px-5 py-10 text-center text-xs font-black uppercase tracking-wider text-muted-foreground">
            No clients match &ldquo;{query}&rdquo;
          </div>
        ) : (
          <div>
            {visible.map((client, index) => (
              <ClientEntity
                key={client.clientId}
                client={client}
                index={index}
                onSelect={onSelect}
                handleInvite={handleInvite}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
