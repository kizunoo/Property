"use client"

import { useEffect, useState } from "react"
import {
  Bath,
  Bed,
  Building2,
  DollarSign,
  MapPin,
  Maximize2,
  Users,
  X,
} from "lucide-react"
import { currency, type Property } from "@/lib/pipeline-data"
import { PixelatedImageCanvas } from "./pixelated-image-canvas"

// ─── Deterministic mock specs ─────────────────────────────────────────────────
function mockSpecs(value: number) {
  const base = Math.floor(value / 100_000)
  return {
    sqft:         800 + (base % 20) * 100,
    bedrooms:     2 + (base % 3),
    bathrooms:    2 + (base % 2),
    pricePerSqft: Math.round(value / (800 + (base % 20) * 100)),
  }
}

// ─── Sub-components ───────────────────────────────────────────────────────────
const STATUS_STYLES: Record<Property["status"], string> = {
  LISTED:        "bg-white text-black",
  PENDING:       "bg-black text-white",
  "UNDER OFFER": "bg-primary text-black",
}

function StatusBadge({ status }: { status: Property["status"] }) {
  return (
    <span className={`inline-block border-2 border-black px-3 py-1 text-xs font-black uppercase tracking-wider ${STATUS_STYLES[status]}`}>
      {status}
    </span>
  )
}

function SpecTile({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="flex flex-col gap-1.5 border-2 border-black p-3">
      <div className="flex items-center gap-1.5 text-[10px] font-black uppercase tracking-wider text-muted-foreground">
        {icon}
        {label}
      </div>
      <div className="font-mono text-lg font-black leading-none">{value}</div>
    </div>
  )
}

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2 border-b-2 border-black pb-2">
      <span className="text-[10px] font-black uppercase tracking-widest text-muted-foreground">{children}</span>
    </div>
  )
}

// ─── Main modal ───────────────────────────────────────────────────────────────
interface PropertyDetailModalProps {
  property: Property | null
  open: boolean
  onClose: () => void
  onFindBuyers?: () => void
}

export function PropertyDetailModal({ property, open, onClose, onFindBuyers }: PropertyDetailModalProps) {
  useEffect(() => {
    if (!open) return
    function onKey(e: KeyboardEvent) { if (e.key === "Escape") onClose() }
    document.addEventListener("keydown", onKey)
    return () => document.removeEventListener("keydown", onKey)
  }, [open, onClose])

  useEffect(() => {
    if (open) { document.body.style.overflow = "hidden" }
    else       { document.body.style.overflow = "" }
    return () => { document.body.style.overflow = "" }
  }, [open])

  if (!open || !property) return null

  const specs = mockSpecs(property.value)

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 lg:p-10"
      style={{ backgroundColor: "rgba(0,0,0,0.75)" }}
      onClick={onClose}
    >
      <div
        className="relative flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden border-4 border-black bg-white shadow-[12px_12px_0px_0px_rgba(0,0,0,1)]"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={`Property Detail — ${property.address}`}
      >
        {/* ── Header ── */}
        <div className="relative shrink-0 border-b-4 border-black">
          <div className="stripes-diagonal absolute inset-0" />
          <div className="relative z-10 flex items-start justify-between gap-4 p-5 sm:p-6">
            <div className="flex items-center gap-4">
              <div className="flex h-14 w-14 shrink-0 items-center justify-center border-4 border-black bg-black">
                <Building2 className="h-6 w-6 text-primary" strokeWidth={2.5} />
              </div>
              <div>
                <div className="text-lg font-black leading-tight sm:text-xl">{property.name}</div>
                <div className="mt-1 flex items-center gap-1 text-xs font-bold text-muted-foreground">
                  <MapPin className="h-3 w-3 shrink-0" strokeWidth={2.5} />
                  {property.address}
                </div>
                <div className="mt-2">
                  <StatusBadge status={property.status} />
                </div>
              </div>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="shrink-0 border-2 border-black p-2 transition-colors hover:bg-black hover:text-white"
              aria-label="Close"
            >
              <X className="h-5 w-5" strokeWidth={2.5} />
            </button>
          </div>
        </div>

        {/* ── Scrollable body ── */}
        <div className="overflow-y-auto p-5 sm:p-6">
          <div className="flex flex-col gap-6">
            {/* Property Image Hero Banner */}
            <PixelatedImageCanvas
              src={property.imageUrl}
              alt={property.address}
              containerHeightClass="h-60 sm:h-72"
              borderBottomOnly={false}
              showCreditBadge={true}
              disablePixelation={true}
            />

            {/* Listing value hero */}
            <div className="border-4 border-black bg-black p-5 shadow-[6px_6px_0px_0px_rgba(0,0,0,1)]">
              <div className="text-[10px] font-black uppercase tracking-widest text-white/60">Listing Value</div>
              <div className="mt-2 font-mono text-2xl sm:text-3xl lg:text-4xl font-black leading-none text-primary whitespace-nowrap overflow-x-auto scrollbar-none py-1">
                {currency(property.value)}
              </div>
              <div className="mt-3 flex items-center gap-2 text-[11px] font-bold text-white/60">
                <MapPin className="h-3 w-3" strokeWidth={2.5} />
                {property.neighborhood}
              </div>
            </div>

            {/* Specs grid */}
            <div>
              <SectionHeading>
                <Building2 className="inline h-3 w-3 mr-1" strokeWidth={2.5} />
                Property Specifications
              </SectionHeading>
              <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
                <SpecTile icon={<Maximize2 className="h-3 w-3" strokeWidth={2.5} />} label="Sq Ft"   value={specs.sqft.toLocaleString()} />
                <SpecTile icon={<Bed       className="h-3 w-3" strokeWidth={2.5} />} label="Beds"    value={String(specs.bedrooms)} />
                <SpecTile icon={<Bath      className="h-3 w-3" strokeWidth={2.5} />} label="Baths"   value={String(specs.bathrooms)} />
                <SpecTile icon={<DollarSign className="h-3 w-3" strokeWidth={2.5} />} label="RM/Sq Ft" value={`RM ${specs.pricePerSqft.toLocaleString()}`} />
              </div>
            </div>
          </div>
        </div>

        {/* ── Footer ── */}
        <div className="shrink-0 border-t-4 border-black p-5 sm:p-6 bg-card">
          <div className="flex flex-col gap-3 sm:flex-row">
            {onFindBuyers && (
              <button
                type="button"
                onClick={() => { onFindBuyers(); onClose() }}
                className="flex flex-1 items-center justify-center gap-2 border-4 border-black bg-primary py-3.5 text-sm font-black uppercase tracking-wider text-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] transition-all hover:translate-x-0.5 hover:translate-y-0.5 hover:shadow-none"
              >
                <Users className="h-4 w-4 text-black" strokeWidth={2.5} />
                Find Likely Buyers
              </button>
            )}
            <button
              type="button"
              onClick={onClose}
              className="flex flex-1 items-center justify-center gap-2 border-4 border-black bg-black py-3.5 text-sm font-black uppercase tracking-wider text-white shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] transition-all hover:translate-x-0.5 hover:translate-y-0.5 hover:shadow-none"
            >
              <Building2 className="h-4 w-4 text-primary" strokeWidth={2.5} />
              Arrange Viewing
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
