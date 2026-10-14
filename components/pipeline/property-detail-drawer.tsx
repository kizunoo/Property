"use client"

import { useEffect, useState } from "react"
import {
  Bath,
  Bed,
  Building2,
  Clock,
  DollarSign,
  MapPin,
  Maximize2,
  Users,
  X,
} from "lucide-react"
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts"
import { currency, type Property } from "@/lib/pipeline-data"
import { PixelatedImageCanvas } from "./pixelated-image-canvas"


// ─── Deterministic mock specs (fallback when DB columns not yet set) ─────────
function mockSpecs(value: number) {
  const base = Math.floor(value / 100_000)
  return {
    sqft:         800 + (base % 20) * 100,
    bedrooms:     2 + (base % 3),
    bathrooms:    2 + (base % 2),
    pricePerSqft: Math.round(value / (800 + (base % 20) * 100)),
  }
}

// ─── Inline spec edit helpers ─────────────────────────────────────────────────
async function patchPropertySpec(propertyId: string, updates: Record<string, unknown>) {
  const res = await fetch(`/api/properties/${propertyId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  })
  if (!res.ok) throw new Error("Failed to save")
}

// ─── Price History Section ────────────────────────────────────────────────────
interface PriceHistoryPoint {
  id: string
  old_value: number
  new_value: number
  change_pct: number
  changed_at: string
}

function PriceHistorySection({
  propertyId,
  onSimulated,
}: {
  propertyId: string
  onSimulated: (newValue: number) => void
}) {
  const [history, setHistory] = useState<PriceHistoryPoint[]>([])
  const [simulating, setSimulating] = useState(false)

  const fetchHistory = () => {
    fetch(`/api/property_price_history/${propertyId}`)
      .then((r) => r.json())
      .then((d) => setHistory(Array.isArray(d) ? d : []))
      .catch(() => {})
  }

  useEffect(() => {
    fetchHistory()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [propertyId])

  const handleSimulate = async () => {
    setSimulating(true)
    try {
      const res = await fetch(`/api/simulate_price_change/${propertyId}`, { method: "POST" })
      const data = await res.json()
      if (data?.new_value) onSimulated(data.new_value)
      await fetchHistory()
    } finally {
      setSimulating(false)
    }
  }

  const chartData = history.map((h) => {
    const d = new Date(h.changed_at)
    return {
      date: isNaN(d.getTime()) ? "Recent" : d.toLocaleDateString(undefined, { month: "short", day: "numeric" }),
      time: isNaN(d.getTime()) ? "" : d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit", hour12: true }),
      fullTime: isNaN(d.getTime())
        ? "Recorded"
        : d.toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", hour12: true }),
      value: h.new_value,
      oldValue: h.old_value,
      changePct: h.change_pct,
    }
  })

  const latest = history[history.length - 1]
  const isUp = latest ? latest.change_pct > 0 : null

  return (
    <div
      style={{
        marginTop: "4px",
        padding: "18px",
        background: "#fff",
        border: "1px solid #e5e5e5",
        borderRadius: "12px",
        boxShadow: "0px 2px 8px rgba(0,0,0,0.05)",
      }}
    >
      {/* Section header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
        <span style={{ fontWeight: 700, fontSize: "11px", textTransform: "uppercase", letterSpacing: "0.08em", color: "#666" }}>
          Price History
        </span>
        {latest && (
          <span
            style={{
              fontWeight: 700,
              fontSize: "12px",
              padding: "3px 10px",
              borderRadius: "6px",
              background: isUp ? "#FFF8DC" : "#f0f0f0",
              color: isUp ? "#8a6d00" : "#555",
            }}
          >
            {isUp ? "▲" : "▼"} {Math.abs(latest.change_pct * 100).toFixed(1)}%
          </span>
        )}
      </div>

      {/* Chart or empty state */}
      {chartData.length > 0 ? (
        <ResponsiveContainer width="100%" height={150}>
          <LineChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" vertical={false} />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 10, fill: "#999" }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tick={{ fontSize: 10, fill: "#999" }}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v: number) => `RM${(v / 1_000_000).toFixed(1)}M`}
              width={58}
            />
            <Tooltip
              content={({ active, payload }) => {
                if (!active || !payload || !payload.length) return null
                const d = payload[0].payload
                const isPositive = d.changePct > 0
                return (
                  <div className="rounded-lg border border-neutral-200 bg-white p-2.5 shadow-lg text-xs font-sans">
                    <div className="flex items-center gap-1.5 text-[11px] font-bold text-neutral-600 pb-1 mb-1 border-b border-neutral-100">
                      <Clock className="h-3 w-3 text-neutral-400" />
                      <span>{d.fullTime}</span>
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-neutral-500 font-medium">Listing Value:</span>
                      <span className="font-mono font-bold text-neutral-900">
                        RM {d.value?.toLocaleString()}
                      </span>
                    </div>
                    {d.changePct !== undefined && d.changePct !== 0 && (
                      <div className="mt-1 flex items-center justify-between gap-3 text-[11px]">
                        <span className="text-neutral-500 font-medium">Price Shift:</span>
                        <span className={`font-mono font-bold ${isPositive ? "text-amber-600" : "text-neutral-700"}`}>
                          {isPositive ? "+" : ""}{(d.changePct * 100).toFixed(1)}%
                        </span>
                      </div>
                    )}
                  </div>
                )
              }}
            />
            <Line
              type="monotone"
              dataKey="value"
              stroke="#FFD400"
              strokeWidth={2.5}
              dot={{ r: 3.5, fill: "#000" }}
              activeDot={{ r: 5.5, fill: "#FFD400", stroke: "#000", strokeWidth: 2 }}
            />
          </LineChart>
        </ResponsiveContainer>
      ) : (
        <div style={{ padding: "24px 0", textAlign: "center", color: "#999", fontSize: "13px" }}>
          No price changes recorded yet.
        </div>
      )}

      {/* Simulate button */}
      <button
        onClick={handleSimulate}
        disabled={simulating}
        style={{
          marginTop: "14px",
          width: "100%",
          padding: "10px",
          borderRadius: "8px",
          border: "1px solid #000",
          background: simulating ? "#f0f0f0" : "#fff",
          fontWeight: 700,
          fontSize: "11px",
          textTransform: "uppercase",
          letterSpacing: "0.08em",
          cursor: simulating ? "default" : "pointer",
          transition: "background 0.15s",
        }}
      >
        {simulating ? "Simulating…" : "Simulate Market Movement"}
      </button>
    </div>
  )
}


const STATUS_STYLES: Record<Property["status"], string> = {
  LISTED:        "bg-white text-black border-border",
  PENDING:       "bg-black text-white border-black",
  "UNDER OFFER": "bg-primary text-black border-primary",
  CLOSED:        "bg-neutral-900 text-amber-300 border-amber-400/60",
}

function StatusBadge({ status }: { status: Property["status"] }) {
  return (
    <span className={`inline-block rounded-[var(--radius-sm)] border px-2.5 py-0.5 text-xs font-bold uppercase tracking-wider ${STATUS_STYLES[status]}`}>
      {status}
    </span>
  )
}

function SpecTile({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="flex flex-col gap-1.5 rounded-[8px] border border-border bg-muted/20 p-3.5">
      <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
        {icon}
        {label}
      </div>
      <div className="font-display text-lg font-bold leading-none text-foreground">{value}</div>
    </div>
  )
}

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2 border-b border-border pb-2">
      <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">{children}</span>
    </div>
  )
}

// ─── Editable spec tile ───────────────────────────────────────────────────────
function EditableSpecTile({
  icon, label, value, fieldKey, propertyId, onSaved, isEstimated,
}: {
  icon: React.ReactNode
  label: string
  value: string
  fieldKey: string
  propertyId: string
  onSaved: (key: string, val: string | number) => void
  isEstimated?: boolean
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft]     = useState("")
  const [saving, setSaving]   = useState(false)

  const open = () => { setDraft(value.replace(/[^0-9.a-z-]/gi, "")); setEditing(true) }

  const save = async () => {
    const parsed = isNaN(Number(draft)) ? draft : Number(draft)
    setSaving(true)
    try {
      await patchPropertySpec(propertyId, { [fieldKey]: parsed })
      onSaved(fieldKey, parsed)
      setEditing(false)
    } catch {
      // silently fail — value stays
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="group relative flex flex-col gap-1.5 rounded-[8px] border border-border bg-muted/20 p-3.5 cursor-pointer hover:border-neutral-400 transition-colors" onClick={!editing ? open : undefined}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
          {icon}
          {label}
          {isEstimated && (
            <span className="ml-1 text-[8px] font-bold text-amber-500 uppercase tracking-wide">⚠ est.</span>
          )}
        </div>
        {!editing && (
          <span className="hidden group-hover:block text-[9px] font-bold text-muted-foreground uppercase tracking-wide">edit</span>
        )}
      </div>
      {editing ? (
        <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
          <input
            autoFocus
            type="text"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") save(); if (e.key === "Escape") setEditing(false) }}
            className="flex-1 rounded-[4px] border border-border bg-card px-2 py-1 text-sm font-bold text-foreground outline-none focus:ring-1 focus:ring-foreground"
          />
          <button onClick={save} disabled={saving} className="rounded-[4px] bg-black px-2 py-1 text-[10px] font-bold text-white disabled:opacity-50">
            {saving ? "…" : "✓"}
          </button>
          <button onClick={() => setEditing(false)} className="rounded-[4px] border border-border px-2 py-1 text-[10px] font-bold text-muted-foreground">
            ✕
          </button>
        </div>
      ) : (
        <div className="font-display text-lg font-bold leading-none text-foreground">{value}</div>
      )}
    </div>
  )
}

// ─── Main modal ───────────────────────────────────────────────────────────────
interface PropertyDetailModalProps {
  property: Property | null
  open: boolean
  onClose: () => void
  onFindBuyers?: () => void
  onPriceChanged?: (propertyId: string, newValue: number) => void
}

export function PropertyDetailModal({ property, open, onClose, onFindBuyers, onPriceChanged }: PropertyDetailModalProps) {
  // liveValue tracks the current property price inside the modal so it updates
  // immediately after a price simulation without needing to close and reopen.
  const [liveValue, setLiveValue] = useState<number | null>(null)

  // Live spec overrides: updated when an agent edits a tile inline
  const [liveSpecs, setLiveSpecs] = useState<Record<string, string | number>>({})

  // Reset live state whenever the modal opens for a different property
  useEffect(() => {
    setLiveValue(null)
    setLiveSpecs({})
  }, [property?.id])

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

  const displayValue = liveValue ?? property.value
  const mocked       = mockSpecs(displayValue)

  // Resolve each spec: prefer DB value, then live override, then mock
  const getSpec = (dbVal: number | null | undefined, mockVal: number, liveKey: string) => {
    const live = liveSpecs[liveKey]
    if (live !== undefined) return { value: Number(live), estimated: false }
    if (dbVal != null)      return { value: dbVal, estimated: false }
    return { value: mockVal, estimated: true }
  }

  const sqftSpec   = getSpec(property.sqft,      mocked.sqft,      "sqft")
  const bedsSpec   = getSpec(property.bedrooms,  mocked.bedrooms,  "bedrooms")
  const bathsSpec  = getSpec(property.bathrooms, mocked.bathrooms, "bathrooms")
  const psfValue   = sqftSpec.value > 0 ? Math.round(displayValue / sqftSpec.value) : mocked.pricePerSqft
  const estimated  = sqftSpec.estimated || bedsSpec.estimated || bathsSpec.estimated

  const handleSpecSaved = (key: string, val: string | number) => {
    setLiveSpecs((prev) => ({ ...prev, [key]: val }))
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 lg:p-10"
      style={{ backgroundColor: "rgba(0,0,0,0.65)" }}
      onClick={onClose}
    >
      <div
        className="relative flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-[12px] border border-border bg-card shadow-[var(--shadow-xl)]"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={`Unit Detail — ${property.address}`}
      >
        {/* ── Header ── */}
        <div className="relative shrink-0 border-b border-border bg-transparent">
          <div className="flex items-start justify-between gap-4 p-5 sm:p-6">
            <div className="flex items-center gap-3.5">
              <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-[8px] bg-black">
                <Building2 className="h-6 w-6 text-primary" strokeWidth={2.5} />
              </div>
              <div>
                <div className="text-lg font-bold leading-tight text-foreground sm:text-xl">{property.address || property.name}</div>
                <div className="mt-1 flex items-center gap-1 text-xs font-semibold text-muted-foreground">
                  <MapPin className="h-3.5 w-3.5 shrink-0 text-muted-foreground" strokeWidth={2.5} />
                  {property.neighborhood}
                </div>
                <div className="mt-2 flex items-center gap-2 flex-wrap">
                  <StatusBadge status={property.status} />
                  {property.ownerName && (
                    <span className="inline-block rounded-[var(--radius-sm)] border border-amber-300 bg-amber-100 px-2 py-0.5 text-xs font-bold text-amber-900">
                      Deployed to {property.ownerName}
                    </span>
                  )}
                  {property.assignedAgent && (
                    <span
                      title={`Sales Rep: ${property.assignedAgent.name}`}
                      className="inline-flex items-center gap-1.5 rounded-[var(--radius-sm)] border border-neutral-300 bg-neutral-100 px-2 py-0.5 text-xs font-bold text-neutral-700"
                    >
                      <span className="flex h-4 w-4 items-center justify-center rounded-full bg-neutral-900 text-[8px] font-black text-primary shrink-0">
                        {property.assignedAgent.initials}
                      </span>
                      Sales Rep: {property.assignedAgent.name}
                    </span>
                  )}
                </div>
              </div>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="shrink-0 rounded-[var(--radius-sm)] border border-border p-2 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
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
            <div className="rounded-[8px] border border-l-[3px] border-l-primary border-border bg-muted/30 p-5 shadow-[var(--shadow-xs)]">
              <div className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Unit Cost</div>
              <div className="mt-2 font-display text-3xl sm:text-4xl font-bold leading-none text-foreground whitespace-nowrap overflow-x-auto scrollbar-none py-1">
                {currency(displayValue)}
              </div>
              <div className="mt-2 flex items-center gap-1.5 text-xs font-semibold text-muted-foreground">
                <MapPin className="h-3.5 w-3.5 text-muted-foreground" strokeWidth={2.5} />
                {property.neighborhood}
              </div>
            </div>

            {/* Price History */}
            <PriceHistorySection
              propertyId={property.id}
              onSimulated={(newVal) => {
                setLiveValue(newVal)
                onPriceChanged?.(property.id, newVal)
              }}
            />

            {/* Specs grid */}
            <div>
              <SectionHeading>
                <Building2 className="inline h-3 w-3 mr-1" strokeWidth={2.5} />
                Unit Specifications
                {estimated && (
                  <span className="ml-2 text-[9px] font-bold text-amber-500 uppercase tracking-wide">(click any tile to set real values)</span>
                )}
              </SectionHeading>
              <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
                <EditableSpecTile
                  icon={<Maximize2 className="h-3 w-3" strokeWidth={2.5} />}
                  label="Coverage (sq ft)"
                  value={sqftSpec.value.toLocaleString()}
                  fieldKey="sqft"
                  propertyId={property.id}
                  onSaved={handleSpecSaved}
                  isEstimated={sqftSpec.estimated}
                />
                <EditableSpecTile
                  icon={<Bed className="h-3 w-3" strokeWidth={2.5} />}
                  label="Payload Tier"
                  value={String(bedsSpec.value)}
                  fieldKey="bedrooms"
                  propertyId={property.id}
                  onSaved={handleSpecSaved}
                  isEstimated={bedsSpec.estimated}
                />
                <EditableSpecTile
                  icon={<Bath className="h-3 w-3" strokeWidth={2.5} />}
                  label="Nav. Redundancy"
                  value={String(bathsSpec.value)}
                  fieldKey="bathrooms"
                  propertyId={property.id}
                  onSaved={handleSpecSaved}
                  isEstimated={bathsSpec.estimated}
                />
                <div className="flex flex-col gap-1.5 rounded-[8px] border border-border bg-muted/20 p-3.5">
                  <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                    <DollarSign className="h-3 w-3" strokeWidth={2.5} />
                    RM/Coverage Unit
                  </div>
                  <div className="font-display text-lg font-bold leading-none text-foreground">
                    RM {psfValue.toLocaleString()}
                  </div>
                </div>
              </div>

              {/* Property type / furnishing / tenure row (when DB data available) */}
              {(property.propertyType || property.furnishing || property.tenure) && (
                <div className="mt-3 grid grid-cols-3 gap-3">
                  {property.propertyType && (
                    <EditableSpecTile
                      icon={<Building2 className="h-3 w-3" strokeWidth={2.5} />}
                      label="Type"
                      value={property.propertyType}
                      fieldKey="property_type"
                      propertyId={property.id}
                      onSaved={handleSpecSaved}
                    />
                  )}
                  {property.furnishing && (
                    <EditableSpecTile
                      icon={<Building2 className="h-3 w-3" strokeWidth={2.5} />}
                      label="Furnishing"
                      value={property.furnishing}
                      fieldKey="furnishing"
                      propertyId={property.id}
                      onSaved={handleSpecSaved}
                    />
                  )}
                  {property.tenure && (
                    <EditableSpecTile
                      icon={<Building2 className="h-3 w-3" strokeWidth={2.5} />}
                      label="Tenure"
                      value={property.tenure}
                      fieldKey="tenure"
                      propertyId={property.id}
                      onSaved={handleSpecSaved}
                    />
                  )}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* ── Footer ── */}
        <div className="shrink-0 border-t border-border p-5 sm:p-6 bg-card">
          <div className="flex flex-col gap-3 sm:flex-row">
            {onFindBuyers && (
              <button
                type="button"
                onClick={() => { onFindBuyers(); onClose() }}
                className="flex flex-1 items-center justify-center gap-2 rounded-[8px] border border-border bg-primary py-3 text-sm font-bold uppercase tracking-wider text-black shadow-[var(--shadow-xs)] transition-all hover:shadow-[var(--shadow-sm)]"
              >
                <Users className="h-4 w-4 text-black" strokeWidth={2.5} />
                Find Likely Adopters
              </button>
            )}
            <button
              type="button"
              onClick={onClose}
              className="flex flex-1 items-center justify-center gap-2 rounded-[8px] border border-border bg-black py-3 text-sm font-bold uppercase tracking-wider text-white shadow-[var(--shadow-xs)] transition-all hover:bg-neutral-800 hover:shadow-[var(--shadow-sm)]"
            >
              <Building2 className="h-4 w-4 text-primary" strokeWidth={2.5} />
              Schedule Demo
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
