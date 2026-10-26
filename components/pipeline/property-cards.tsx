"use client"

import { useState } from "react"
import { Building2, CheckCircle2, MapPin, Search, Users } from "lucide-react"
import { currency, type Property } from "@/lib/pipeline-data"
import { priceLabel } from "@/lib/price"
import { PixelatedImageCanvas } from "./pixelated-image-canvas"
import { ScrollConnect } from "@/components/animation/scroll-connect"


const STATUS_STYLES: Record<Property["status"], string> = {
  LISTED: "bg-white text-black",
  PENDING: "bg-black text-white",
  "UNDER OFFER": "bg-primary text-black",
  CLOSED: "bg-neutral-900 text-amber-300 border-amber-400/50",
}

function PropertyCard({
  property,
  onSelect,
  onFindBuyers,
}: {
  property: Property
  onSelect: () => void
  onFindBuyers: () => void
}) {
  const isClosed = property.status === "CLOSED"

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault()
          onSelect()
        }
      }}
      className={`group flex w-full flex-col rounded-lg border bg-card shadow-[0px_4px_16px_rgba(0,0,0,0.10)] cursor-pointer text-left transition-all hover:shadow-[0px_6px_24px_rgba(0,0,0,0.12)] active:shadow-[0px_2px_8px_rgba(0,0,0,0.08)] ${isClosed ? "border-amber-200/80 bg-amber-50/10" : "border-neutral-200"}`}
    >
      {/* Image with optional recently-moved price badge */}
      <div className="relative">
        <PixelatedImageCanvas
          src={property.imageUrl}
          alt={property.address}
          containerHeightClass="h-48 sm:h-52"
          borderBottomOnly={true}
        />
        {property.lastPriceChangeAt &&
          new Date(property.lastPriceChangeAt).getTime() > Date.now() - 24 * 60 * 60 * 1000 &&
          property.lastPriceChangePct !== undefined && (
            <span
              style={{
                position: "absolute",
                top: "10px",
                right: "10px",
                padding: "4px 9px",
                borderRadius: "6px",
                fontSize: "11px",
                fontWeight: 700,
                letterSpacing: "0.04em",
                background: property.lastPriceChangePct > 0 ? "#FFF8DC" : "#f0f0f0",
                color: property.lastPriceChangePct > 0 ? "#8a6d00" : "#555",
                boxShadow: "0px 1px 4px rgba(0,0,0,0.10)",
              }}
            >
              {property.lastPriceChangePct > 0 ? "▲" : "▼"}{" "}
              {Math.abs(property.lastPriceChangePct * 100).toFixed(1)}%
            </span>
          )}
      </div>

      <div className="flex flex-1 flex-col gap-3 p-5 sm:p-6">
        <div className="flex items-start justify-between gap-3">
          <h3 className="text-lg font-bold leading-tight tracking-tight sm:text-xl">{property.address || property.name}</h3>
          <span
            className={`shrink-0 border px-2 py-1 text-[10px] font-black uppercase tracking-wider ${STATUS_STYLES[property.status]}`}
          >
            {property.status}
          </span>
        </div>
        <div className="flex items-center gap-1.5 text-xs font-bold text-muted-foreground sm:text-sm">
          <MapPin className="h-3.5 w-3.5 shrink-0" strokeWidth={2.5} />
          {property.neighborhood || "—"}
        </div>

        {/* Assigned Sales Rep badge */}
        {property.assignedAgent && (
          <div className="flex items-center gap-1.5">
            <div
              title={`Assigned Sales Rep: ${property.assignedAgent.name}`}
              className="flex h-5 w-5 items-center justify-center rounded-full bg-neutral-900 text-[9px] font-black text-primary shrink-0"
            >
              {property.assignedAgent.initials}
            </div>
            <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Sales Rep: {property.assignedAgent.name}
            </span>
          </div>
        )}

        {/* Closed deal owner indicator */}
        {isClosed && (
          <div className="flex items-center gap-1.5 rounded-[4px] bg-amber-100/70 border border-amber-300/80 px-2.5 py-1 text-[11px] font-bold text-amber-950">
            <CheckCircle2 className="h-3.5 w-3.5 text-amber-800 shrink-0" />
            <span>
              Deployed Unit {property.ownerName ? <>· Deployed to <strong className="font-black text-amber-900">{property.ownerName}</strong></> : ""}
            </span>
          </div>
        )}

        <div className="mt-auto flex flex-col gap-2 border-t-2 border-black pt-3">
          <div>
            <div className="text-[10px] font-black uppercase tracking-wider text-muted-foreground">
              {isClosed ? "Deployed / Unit Value" : "Unit Cost"}
            </div>
            <div className="font-mono text-2xl font-black leading-none sm:text-3xl">{priceLabel(property.value, currency)}</div>
          </div>
          {isClosed ? (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                onSelect()
              }}
              className="flex w-full items-center justify-center gap-1.5 border border-neutral-300 bg-neutral-100 py-2 text-[10px] font-black uppercase tracking-wider text-neutral-800 transition-all hover:bg-neutral-200"
            >
              <CheckCircle2 className="h-3 w-3 text-amber-800" strokeWidth={2.5} />
              View Deployed Unit Specs
            </button>
          ) : (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                onFindBuyers()
              }}
              className="flex w-full items-center justify-center gap-1.5 border border-neutral-200 bg-primary py-2 text-[10px] font-black uppercase tracking-wider text-black transition-all hover:shadow-[0px_1px_4px_rgba(0,0,0,0.07)]"
            >
              <Users className="h-3 w-3" strokeWidth={2.5} />
              Find Likely Adopters
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

interface PropertyCardsProps {
  properties: Property[]
  onSelect: (property: Property) => void
  onFindBuyers: (property: Property) => void
}

export function PropertyCards({ properties, onSelect, onFindBuyers }: PropertyCardsProps) {
  const [query, setQuery] = useState("")
  const [statusFilter, setStatusFilter] = useState<"ALL" | "ACTIVE" | "CLOSED">("ALL")

  const activeCount = properties.filter((p) => p.status !== "CLOSED").length
  const closedCount = properties.filter((p) => p.status === "CLOSED").length

  const visibleProperties = properties.filter((p) => {
    // Status filter
    if (statusFilter === "ACTIVE" && p.status === "CLOSED") return false
    if (statusFilter === "CLOSED" && p.status !== "CLOSED") return false

    // Search query filter
    if (query.trim()) {
      const q = query.toLowerCase()
      const matchAddress = (p.address || "").toLowerCase().includes(q)
      const matchNbhd    = (p.neighborhood || "").toLowerCase().includes(q)
      const matchOwner   = p.ownerName?.toLowerCase().includes(q) ?? false
      return matchAddress || matchNbhd || matchOwner
    }
    return true
  })

  return (
    <div className="flex flex-col gap-5">
      {/* Search bar, Status Filters & Pexels Credit Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-1 flex-col sm:flex-row items-stretch sm:items-center gap-3">
          <div className="relative flex-1">
            <Search
              className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
              strokeWidth={2.5}
            />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search by robot model, target environment, or company..."
              className="w-full border border-neutral-200 bg-white py-2.5 pl-10 pr-4 font-sans text-sm font-bold placeholder:font-sans placeholder:font-bold placeholder:text-muted-foreground shadow-[0px_2px_8px_rgba(0,0,0,0.08)] outline-none transition-all focus:shadow-none focus:translate-x-0.5 focus:translate-y-0.5"
            />
          </div>

          {/* Status Filter Tabs */}
          <div className="flex items-center border border-neutral-200 bg-muted/40 p-0.5 rounded-[6px]">
            <button
              type="button"
              onClick={() => setStatusFilter("ALL")}
              className={`px-3 py-1.5 text-xs font-bold transition-all rounded-[4px] ${statusFilter === "ALL" ? "bg-white text-black shadow-sm" : "text-muted-foreground hover:text-foreground"}`}
            >
              All ({properties.length})
            </button>
            <button
              type="button"
              onClick={() => setStatusFilter("ACTIVE")}
              className={`px-3 py-1.5 text-xs font-bold transition-all rounded-[4px] ${statusFilter === "ACTIVE" ? "bg-white text-black shadow-sm" : "text-muted-foreground hover:text-foreground"}`}
            >
              Active ({activeCount})
            </button>
            <button
              type="button"
              onClick={() => setStatusFilter("CLOSED")}
              className={`px-3 py-1.5 text-xs font-bold transition-all rounded-[4px] ${statusFilter === "CLOSED" ? "bg-amber-100 text-amber-900 shadow-sm" : "text-muted-foreground hover:text-foreground"}`}
            >
              Deployed Units ({closedCount})
            </button>
          </div>
        </div>

        <span className="shrink-0 text-[11px] font-black uppercase tracking-wider text-muted-foreground">
          Photos via{" "}
          <a
            href="https://www.pexels.com"
            target="_blank"
            rel="noopener noreferrer"
            className="text-black underline transition-colors hover:bg-primary hover:px-1"
          >
            Pexels
          </a>
        </span>
      </div>

      {/* Property grid */}
      {visibleProperties.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-3 border border-neutral-200 bg-white py-16 shadow-[0px_4px_16px_rgba(0,0,0,0.10)]">
          <Search className="h-8 w-8 text-muted-foreground" strokeWidth={2} />
          <p className="text-xs font-black uppercase tracking-wider text-muted-foreground">
            No robot units match this filter
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:gap-6 md:grid-cols-2 lg:grid-cols-3">
          {visibleProperties.map((property) => (
            <ScrollConnect key={property.id}>
              <PropertyCard
                property={property}
                onSelect={() => onSelect(property)}
                onFindBuyers={() => onFindBuyers(property)}
              />
            </ScrollConnect>
          ))}
        </div>
      )}
    </div>
  )
}

