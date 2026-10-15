"use client"

import { useCallback, useEffect, useState } from "react"
import {
  ArrowRight,
  Bot,
  CheckCircle2,
  Clock,
  FileCheck,
  FileText,
  FileX,
  HelpCircle,
  Plus,
  Send,
  Sparkles,
  X,
  XCircle,
} from "lucide-react"
import type { CatalogUnit, Quote } from "@/lib/portal-types"
import { fetchQuotes, requestQuote, respondQuote, fetchCatalog } from "@/lib/portal-api"
import { useToast } from "@/hooks/use-toast"
import { Skeleton } from "@/components/ui/skeleton"

function formatAmount(amount: number | null | undefined, currency = "MYR"): string {
  if (amount == null) return "—"
  return `${currency} ${amount.toLocaleString("en-MY", { maximumFractionDigits: 2 })}`
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—"
  try {
    return new Date(iso).toLocaleDateString("en-MY", {
      day: "numeric",
      month: "short",
      year: "numeric",
    })
  } catch {
    return iso
  }
}

const STATUS_BADGE: Record<string, { label: string; icon: React.ReactNode; className: string }> = {
  requested: {
    label: "Under review by rep",
    icon: <Clock className="h-3.5 w-3.5" />,
    className: "bg-amber-50 border border-amber-200 text-amber-700",
  },
  sent: {
    label: "Quote ready — action needed",
    icon: <FileText className="h-3.5 w-3.5 text-primary" />,
    className: "bg-primary/20 border border-primary text-foreground font-black",
  },
  accepted: {
    label: "Accepted",
    icon: <CheckCircle2 className="h-3.5 w-3.5" />,
    className: "bg-emerald-50 border border-emerald-300 text-emerald-700",
  },
  declined: {
    label: "Declined",
    icon: <FileX className="h-3.5 w-3.5" />,
    className: "bg-muted border border-border text-muted-foreground",
  },
}

// ─── New Quote Modal ─────────────────────────────────────────────────────────

function RequestQuoteModal({
  clientId,
  onClose,
  onSuccess,
}: {
  clientId: string
  onClose: () => void
  onSuccess: () => void
}) {
  const { toast } = useToast()
  const [units, setUnits] = useState<CatalogUnit[]>([])
  const [loadingUnits, setLoadingUnits] = useState(true)
  const [selectedPropertyId, setSelectedPropertyId] = useState("")
  const [quantity, setQuantity] = useState(1)
  const [notes, setNotes] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    fetchCatalog(clientId)
      .then((res) => {
        if (!active) return
        setUnits(res.units || [])
        if (res.units && res.units.length > 0) {
          setSelectedPropertyId(res.units[0].property_id)
        }
      })
      .catch(() => {
        if (active) setError("Failed to load catalog units.")
      })
      .finally(() => {
        if (active) setLoadingUnits(false)
      })
    return () => {
      active = false
    }
  }, [clientId])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!selectedPropertyId) {
      setError("Please select a robot unit.")
      return
    }
    if (quantity < 1 || quantity > 1000) {
      setError("Quantity must be between 1 and 1,000.")
      return
    }

    setSubmitting(true)
    setError(null)
    try {
      await requestQuote(clientId, {
        property_id: selectedPropertyId,
        quantity,
        notes: notes.trim() || undefined,
      })
      toast({
        title: "Quote requested",
        description: "Your sales representative will review deployment specs and provide pricing.",
      })
      onSuccess()
    } catch (err: any) {
      setError(err?.message || "Failed to submit quote request.")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm px-4">
      <div className="w-full max-w-lg border border-border bg-card shadow-[var(--shadow-xl)]">
        <div className="flex items-start justify-between gap-4 border-b border-border px-6 py-5">
          <div>
            <span className="inline-flex items-center gap-1.5 border border-border bg-primary px-2.5 py-0.5 text-[10px] font-black uppercase tracking-wider mb-2">
              <FileCheck className="h-3 w-3" strokeWidth={3} /> Request Formal Quote
            </span>
            <h2 className="text-lg font-bold tracking-tight">Enterprise Pricing Request</h2>
            <p className="text-sm text-muted-foreground mt-0.5">
              Receive a binding commercial quote including deployment support and warranty options.
            </p>
          </div>
          <button
            onClick={onClose}
            className="shrink-0 border border-border p-1.5 text-muted-foreground hover:bg-muted transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-5 px-6 py-5">
          {loadingUnits ? (
            <div className="flex flex-col gap-2">
              <Skeleton className="h-4 w-28" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : (
            <label className="flex flex-col gap-2">
              <span className="text-xs font-black uppercase tracking-wider">Robot unit</span>
              <select
                id="quote-unit-select"
                value={selectedPropertyId}
                onChange={(e) => setSelectedPropertyId(e.target.value)}
                className="border border-border bg-white px-3 py-2.5 text-sm text-black focus:outline-none focus-visible:border-primary"
              >
                {units.map((u) => (
                  <option key={u.property_id} value={u.property_id}>
                    {u.name} {u.property_type ? `(${u.property_type})` : ""}
                  </option>
                ))}
              </select>
            </label>
          )}

          <label className="flex flex-col gap-2">
            <span className="text-xs font-black uppercase tracking-wider">Quantity (units)</span>
            <input
              id="quote-quantity-input"
              type="number"
              min={1}
              max={1000}
              value={quantity}
              onChange={(e) => setQuantity(Math.max(1, parseInt(e.target.value, 10) || 1))}
              className="border border-border bg-white px-3 py-2.5 text-sm text-black focus:outline-none focus-visible:border-primary"
            />
          </label>

          <label className="flex flex-col gap-2">
            <span className="text-xs font-black uppercase tracking-wider">Deployment notes / Requirements</span>
            <textarea
              id="quote-notes-input"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="e.g. Target deployment at Subang Jaya warehouse; requires charging dock integration..."
              rows={3}
              className="resize-none border border-border bg-white px-3 py-2.5 text-sm text-black placeholder:text-muted-foreground focus:outline-none focus-visible:border-primary"
            />
          </label>

          {error && <p className="text-xs font-semibold text-destructive">{error}</p>}

          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 border border-border bg-muted py-3 text-sm font-black uppercase tracking-wider text-muted-foreground hover:bg-secondary transition-colors"
            >
              Cancel
            </button>
            <button
              id="quote-submit-btn"
              type="submit"
              disabled={submitting || loadingUnits}
              className="flex-1 group flex items-center justify-center gap-2 border border-border bg-black py-3 text-sm font-black uppercase tracking-wider text-white hover:shadow-[var(--shadow-sm)] transition-shadow disabled:opacity-40"
            >
              {submitting ? "Submitting…" : "Submit Request"}
              {!submitting && (
                <ArrowRight
                  className="h-4 w-4 text-primary transition-transform group-hover:translate-x-0.5"
                  strokeWidth={3}
                />
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ─── Respond Modal ───────────────────────────────────────────────────────────

function RespondModal({
  quote,
  action,
  clientId,
  onClose,
  onSuccess,
}: {
  quote: Quote
  action: "accepted" | "declined"
  clientId: string
  onClose: () => void
  onSuccess: () => void
}) {
  const { toast } = useToast()
  const [note, setNote] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleConfirm() {
    setSubmitting(true)
    setError(null)
    try {
      await respondQuote(clientId, quote.id, {
        status: action,
        note: note.trim() || undefined,
      })
      toast({
        title: action === "accepted" ? "Quote accepted" : "Quote declined",
        description:
          action === "accepted"
            ? "Your sales representative has been notified and will issue the purchase agreement."
            : "Feedback shared with your representative.",
      })
      onSuccess()
    } catch (err: any) {
      setError(err?.message || "Failed to respond to quote.")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm px-4">
      <div className="w-full max-w-md border border-border bg-card shadow-[var(--shadow-xl)] p-6 flex flex-col gap-4">
        <div className="flex items-start justify-between">
          <h3 className="text-base font-bold">
            {action === "accepted" ? "Accept this Quote?" : "Decline this Quote?"}
          </h3>
          <button onClick={onClose} className="border border-border p-1 hover:bg-muted">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="border border-border bg-secondary/50 p-3 text-xs flex flex-col gap-1">
          <span className="font-bold">{quote.property_name}</span>
          <span>Quantity: {quote.quantity}</span>
          <span className="font-black text-sm">
            Total: {formatAmount(quote.quoted_amount, quote.currency)}
          </span>
        </div>

        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-black uppercase tracking-wider">
            {action === "accepted" ? "Purchase order notes (optional)" : "Reason for declining (optional)"}
          </span>
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={3}
            placeholder={
              action === "accepted"
                ? "e.g. PO-8891 approved, target delivery Q4..."
                : "e.g. Budget constraints, selected alternative unit..."
            }
            className="border border-border bg-white p-2.5 text-xs focus:outline-none focus-visible:border-primary"
          />
        </label>

        {error && <p className="text-xs font-semibold text-destructive">{error}</p>}

        <div className="flex gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="flex-1 border border-border bg-muted py-2.5 text-xs font-black uppercase tracking-wider"
          >
            Cancel
          </button>
          <button
            id={`confirm-${action}-btn`}
            type="button"
            onClick={handleConfirm}
            disabled={submitting}
            className={`flex-1 py-2.5 text-xs font-black uppercase tracking-wider text-white border border-border ${
              action === "accepted" ? "bg-black" : "bg-destructive text-destructive-foreground"
            }`}
          >
            {submitting ? "Processing…" : action === "accepted" ? "Confirm Acceptance" : "Decline Quote"}
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Quotes Tab Component ───────────────────────────────────────────────────

export function QuotesTab({ clientId }: { clientId: string }) {
  const [quotes, setQuotes] = useState<Quote[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showRequestModal, setShowRequestModal] = useState(false)
  const [respondingQuote, setRespondingQuote] = useState<{
    quote: Quote
    action: "accepted" | "declined"
  } | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetchQuotes(clientId)
      setQuotes(res.quotes || [])
    } catch (err: any) {
      setError(err?.message || "Failed to load quotes.")
    } finally {
      setLoading(false)
    }
  }, [clientId])

  useEffect(() => {
    load()
  }, [load])

  return (
    <div className="mx-auto max-w-6xl px-4 sm:px-6 py-8 flex flex-col gap-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-border pb-5">
        <div>
          <h1 className="text-[10px] font-black uppercase tracking-wider text-muted-foreground flex items-center gap-2">
            <FileText className="h-3.5 w-3.5" /> Commercial Quotations
          </h1>
          <p className="text-sm font-semibold mt-1">
            Official equipment proposals and procurement pricing
          </p>
        </div>
        <button
          id="open-request-quote-modal-btn"
          onClick={() => setShowRequestModal(true)}
          className="group inline-flex items-center gap-2 border border-border bg-black px-4 py-2.5 text-xs font-black uppercase tracking-wider text-white hover:shadow-[var(--shadow-sm)] transition-shadow"
        >
          <Plus className="h-3.5 w-3.5 text-primary" strokeWidth={3} />
          Request new quote
        </button>
      </div>

      {/* Content */}
      {loading ? (
        <div className="flex flex-col gap-4">
          {[...Array(3)].map((_, i) => (
            <Skeleton key={i} className="h-28 w-full" />
          ))}
        </div>
      ) : error ? (
        <div className="border border-border bg-card p-8 text-center">
          <XCircle className="mx-auto h-6 w-6 text-destructive mb-2" />
          <p className="text-sm font-semibold text-destructive mb-4">{error}</p>
          <button
            onClick={load}
            className="border border-border bg-black px-4 py-2 text-xs font-black uppercase tracking-wider text-white"
          >
            Retry
          </button>
        </div>
      ) : quotes.length === 0 ? (
        <div className="border border-border bg-card p-12 text-center shadow-[var(--shadow-xs)]">
          <FileText className="mx-auto h-10 w-10 text-muted-foreground opacity-40 mb-3" />
          <h3 className="font-bold text-base mb-1">No quotation requests yet</h3>
          <p className="text-sm text-muted-foreground max-w-md mx-auto mb-5">
            Request formal volume pricing, leasing packages, or custom hardware modifications for any
            unit in the catalog.
          </p>
          <button
            onClick={() => setShowRequestModal(true)}
            className="border border-border bg-black px-4 py-2.5 text-xs font-black uppercase tracking-wider text-white hover:shadow-[var(--shadow-sm)]"
          >
            Request quote now
          </button>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          {quotes.map((q) => {
            const badge = STATUS_BADGE[q.status] ?? STATUS_BADGE.requested
            return (
              <div
                key={q.id}
                className={`border bg-card p-5 shadow-[var(--shadow-xs)] flex flex-col gap-4 ${
                  q.status === "sent" ? "border-primary" : "border-border"
                }`}
              >
                <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <h3 className="font-bold text-base">{q.property_name}</h3>
                      <span
                        className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 text-[10px] font-black uppercase tracking-wider ${badge.className}`}
                      >
                        {badge.icon}
                        {badge.label}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">
                      Requested on {formatDate(q.requested_at)} · Quantity:{" "}
                      <span className="font-bold text-foreground">{q.quantity} units</span>
                    </p>
                  </div>

                  {q.quoted_amount != null && (
                    <div className="text-left sm:text-right">
                      <p className="text-[10px] font-black uppercase tracking-wider text-muted-foreground">
                        Total Quoted
                      </p>
                      <p className="text-xl font-black text-foreground">
                        {formatAmount(q.quoted_amount, q.currency)}
                      </p>
                      {q.valid_until && (
                        <p className="text-[10px] text-muted-foreground">
                          Valid until {formatDate(q.valid_until)}
                        </p>
                      )}
                    </div>
                  )}
                </div>

                {/* Notes section */}
                {(q.customer_note || q.notes) && (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs border-t border-border pt-3">
                    {q.notes && (
                      <div className="bg-muted/40 p-3 border border-border">
                        <span className="font-black text-[10px] uppercase text-muted-foreground block mb-1">
                          Your Request Note
                        </span>
                        <p className="text-foreground">{q.notes}</p>
                      </div>
                    )}
                    {q.customer_note && (
                      <div className="bg-secondary/60 p-3 border border-border">
                        <span className="font-black text-[10px] uppercase text-muted-foreground block mb-1">
                          Representative Terms &amp; Scope
                        </span>
                        <p className="text-foreground">{q.customer_note}</p>
                      </div>
                    )}
                  </div>
                )}

                {/* Response / Actions */}
                {q.status === "sent" && (
                  <div className="flex items-center justify-end gap-2 pt-2 border-t border-border">
                    <button
                      id={`decline-quote-${q.id}`}
                      onClick={() => setRespondingQuote({ quote: q, action: "declined" })}
                      className="border border-border bg-secondary px-3 py-2 text-xs font-black uppercase tracking-wider hover:bg-muted transition-colors"
                    >
                      Decline
                    </button>
                    <button
                      id={`accept-quote-${q.id}`}
                      onClick={() => setRespondingQuote({ quote: q, action: "accepted" })}
                      className="border border-border bg-black px-4 py-2 text-xs font-black uppercase tracking-wider text-white hover:shadow-[var(--shadow-sm)] transition-shadow"
                    >
                      Accept Quote
                    </button>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Modals */}
      {showRequestModal && (
        <RequestQuoteModal
          clientId={clientId}
          onClose={() => setShowRequestModal(false)}
          onSuccess={() => {
            setShowRequestModal(false)
            load()
          }}
        />
      )}

      {respondingQuote && (
        <RespondModal
          quote={respondingQuote.quote}
          action={respondingQuote.action}
          clientId={clientId}
          onClose={() => setRespondingQuote(null)}
          onSuccess={() => {
            setRespondingQuote(null)
            load()
          }}
        />
      )}
    </div>
  )
}
