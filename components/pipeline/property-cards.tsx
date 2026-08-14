"use client"

import { useState } from "react"
import { Building2, MapPin, Search, Users } from "lucide-react"
import { currency, type Property } from "@/lib/pipeline-data"
import { PixelatedImageCanvas } from "./pixelated-image-canvas"
import { ScrollConnect } from "@/components/animation/scroll-connect"


const STATUS_STYLES: Record<Property["status"], string> = {
  LISTED: "bg-white text-black",
  PENDING: "bg-black text-white",
  "UNDER OFFER": "bg-primary text-black",
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
      className="group flex w-full flex-col rounded-none border-4 border-black bg-card shadow-[8px_8px_0px_0px_rgba(0,0,0,1)] cursor-pointer text-left transition-all hover:-translate-x-0.5 hover:-translate-y-0.5 hover:shadow-[10px_10px_0px_0px_rgba(0,0,0,1)] active:translate-x-0.5 active:translate-y-0.5 active:shadow-[4px_4px_0px_0px_rgba(0,0,0,1)]"
    >
      <PixelatedImageCanvas
        src={property.imageUrl}
        alt={property.address}
        containerHeightClass="h-48 sm:h-52"
        borderBottomOnly={true}
      />

      <div className="flex flex-1 flex-col gap-3 p-5 sm:p-6">
        <div className="flex items-start justify-between gap-3">
          <h3 className="text-lg font-bold leading-tight tracking-tight sm:text-xl">{property.name}</h3>
          <span
            className={`shrink-0 border-2 border-black px-2 py-1 text-[10px] font-black uppercase tracking-wider ${STATUS_STYLES[property.status]}`}
          >
            {property.status}
          </span>
        </div>
        <div className="flex items-center gap-1.5 text-xs font-bold text-muted-foreground sm:text-sm">
          <MapPin className="h-3.5 w-3.5 shrink-0" strokeWidth={2.5} />
          {property.address}
        </div>
        <div className="mt-auto flex flex-col gap-2 border-t-2 border-black pt-3">
          <div>
            <div className="text-[10px] font-black uppercase tracking-wider text-muted-foreground">Property Value</div>
            <div className="font-mono text-2xl font-black leading-none sm:text-3xl">{currency(property.value)}</div>
          </div>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation()
              onFindBuyers()
            }}
            className="flex w-full items-center justify-center gap-1.5 border-2 border-black bg-primary py-2 text-[10px] font-black uppercase tracking-wider text-black transition-all hover:-translate-x-0.5 hover:-translate-y-0.5 hover:shadow-[3px_3px_0px_0px_rgba(0,0,0,1)] active:translate-x-0 active:translate-y-0"
          >
            <Users className="h-3 w-3" strokeWidth={2.5} />
            Find Likely Buyers
          </button>
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

  const visibleProperties = query.trim()
    ? properties.filter((p) => {
        const q = query.toLowerCase()
        return (
          p.address.toLowerCase().includes(q) ||
          p.neighborhood.toLowerCase().includes(q)
        )
      })
    : properties

  return (
    <div className="flex flex-col gap-5">
      {/* Search bar & Pexels Credit Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative flex-1">
          <Search
            className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
            strokeWidth={2.5}
          />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by address or neighborhood (e.g., Mont Kiara)..."
            className="w-full border-4 border-black bg-white py-3 pl-10 pr-4 font-mono text-sm font-bold placeholder:font-sans placeholder:font-bold placeholder:text-muted-foreground shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] outline-none transition-all focus:shadow-none focus:translate-x-0.5 focus:translate-y-0.5"
          />
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
        <div className="flex flex-col items-center justify-center gap-3 border-4 border-black bg-white py-16 shadow-[8px_8px_0px_0px_rgba(0,0,0,1)]">
          <Search className="h-8 w-8 text-muted-foreground" strokeWidth={2} />
          <p className="text-xs font-black uppercase tracking-wider text-muted-foreground">
            No properties match &ldquo;{query}&rdquo;
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
