"use client"

import { useEffect, useState, useCallback } from "react"
import { ArrowRight, CheckCircle2, HelpCircle, MessageSquare, XCircle } from "lucide-react"
import type { DashboardData, Inquiry, MatchUnit } from "@/lib/portal-types"
import { fetchInquiries, submitInquiry } from "@/lib/portal-api"
import { useToast } from "@/hooks/use-toast"
import { Skeleton } from "@/components/ui/skeleton"

// ─── Status config ────────────────────────────────────────────────────────────

const STATUS_BADGE: Record<string, { label: string; className: string }> = {
  open:    { label: "Open — awaiting reply", className: "bg-amber-50 border border-amber-200 text-amber-700" },
  replied: { label: "Replied",               className: "bg-primary border border-primary/30 text-primary-foreground" },
  closed:  { label: "Closed",               className: "bg-muted border border-border text-muted-foreground" },
}

function formatDate(s: string): string {
  return new Date(s).toLocaleDateString("en-MY", {
    day: "numeric", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  })
}

// ─── Inquiry card ─────────────────────────────────────────────────────────────

function InquiryCard({ inquiry }: { inquiry: Inquiry }) {
  const badge = STATUS_BADGE[inquiry.status] ?? STATUS_BADGE.open

  return (
    <div className="border border-border bg-card shadow-[var(--shadow-sm)] p-5 flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          {inquiry.property_name && (
            <p className="text-[10px] font-black uppercase tracking-wider text-muted-foreground mb-1">
              {inquiry.property_name}
            </p>
          )}
          <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 text-[10px] font-black uppercase tracking-wider ${badge.className}`}>
            {inquiry.status === "replied" ? <CheckCircle2 className="h-3 w-3" /> : <HelpCircle className="h-3 w-3" />}
            {badge.label}
          </span>
        </div>
        <span className="text-[10px] text-muted-foreground/70 shrink-0">
          {formatDate(inquiry.created_at)}
        </span>
      </div>

      {/* Message */}
      <div className="border border-border bg-muted/40 px-4 py-3">
        <p className="text-[10px] font-black uppercase tracking-wider text-muted-foreground mb-1.5">Your question</p>
        <p className="text-sm leading-relaxed">{inquiry.message}</p>
      </div>

      {/* Agent reply (only shown when status === 'replied') */}
      {inquiry.agent_reply && (
        <div className="border border-border bg-secondary/60 px-4 py-3">
          <p className="text-[10px] font-black uppercase tracking-wider text-muted-foreground mb-1.5">Reply from PIPELINE.EV</p>
          <p className="text-sm leading-relaxed">{inquiry.agent_reply}</p>
        </div>
      )}
    </div>
  )
}

// ─── New inquiry form ─────────────────────────────────────────────────────────

function NewInquiryForm({
  clientId,
  units,
  onSuccess,
}: {
  clientId: string
  units: MatchUnit[]
  onSuccess: () => void
}) {
  const { toast } = useToast()
  const [selectedPropertyId, setSelectedPropertyId] = useState(units[0]?.property_id ?? "")
  const [message, setMessage] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!message.trim() || !selectedPropertyId) return
    setLoading(true); setError(null)
    try {
      await submitInquiry(clientId, {
        property_id: selectedPropertyId,
        message: message.trim(),
      })
      setMessage("")
      toast({ title: "Question sent!", description: "Our team will respond shortly." })
      onSuccess()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send question.")
    } finally {
      setLoading(false)
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="border border-border bg-card shadow-[var(--shadow-sm)] p-5 flex flex-col gap-4"
    >
      <div className="border-b border-border pb-4">
        <span className="inline-flex items-center gap-1.5 border border-border bg-secondary px-2.5 py-0.5 text-[10px] font-black uppercase tracking-wider mb-2">
          <HelpCircle className="h-3 w-3" strokeWidth={3} /> Ask a Question
        </span>
        <h2 className="text-base font-bold tracking-tight mt-1">Send us a message</h2>
        <p className="text-sm text-muted-foreground mt-0.5">
          Questions about a specific unit? Our team will reply within one business day.
        </p>
      </div>

      {/* Unit selector */}
      {units.length > 0 && (
        <label className="flex flex-col gap-2">
          <span className="text-xs font-black uppercase tracking-wider">About which unit?</span>
          <select
            id="inquiry-property-select"
            value={selectedPropertyId}
            onChange={e => setSelectedPropertyId(e.target.value)}
            className="border border-border bg-white px-3 py-2.5 text-sm text-black focus:outline-none focus-visible:border-primary"
          >
            {units.map(u => (
              <option key={u.property_id} value={u.property_id}>{u.name}</option>
            ))}
          </select>
        </label>
      )}

      <label className="flex flex-col gap-2">
        <span className="text-xs font-black uppercase tracking-wider">Your question</span>
        <textarea
          id="inquiry-message"
          value={message}
          onChange={e => setMessage(e.target.value)}
          placeholder="e.g. What is the minimum floor load bearing requirement for this unit?"
          rows={4}
          className="resize-none border border-border bg-white px-3 py-2.5 text-sm text-black placeholder:text-muted-foreground focus:outline-none focus-visible:border-primary"
        />
      </label>

      {error && <p className="text-xs font-semibold text-destructive">{error}</p>}

      <button
        type="submit"
        disabled={loading || !message.trim() || !selectedPropertyId}
        id="send-inquiry-btn"
        className="group flex items-center justify-center gap-2 border border-border bg-black py-3 text-sm font-black uppercase tracking-wider text-white hover:shadow-[var(--shadow-sm)] transition-shadow disabled:opacity-40"
      >
        {loading ? "Sending…" : "Send question"}
        {!loading && <ArrowRight className="h-4 w-4 text-primary transition-transform group-hover:translate-x-0.5" strokeWidth={3} />}
      </button>
    </form>
  )
}

// ─── Messages Tab ─────────────────────────────────────────────────────────────

export function MessagesTab({
  clientId,
  data,
}: {
  clientId: string
  data: DashboardData | null
}) {
  const [inquiries, setInquiries] = useState<Inquiry[]>([])
  const [loading, setLoading]     = useState(true)
  const [error, setError]         = useState<string | null>(null)

  const units = data?.matches ?? []

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const d = await fetchInquiries(clientId)
      setInquiries(d.inquiries)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load messages.")
    } finally {
      setLoading(false)
    }
  }, [clientId])

  useEffect(() => { load() }, [load])

  return (
    <div className="mx-auto max-w-3xl px-4 sm:px-6 py-10 flex flex-col gap-8">

      {/* New inquiry form */}
      {units.length > 0 && (
        <NewInquiryForm clientId={clientId} units={units} onSuccess={load} />
      )}

      {/* History */}
      <section aria-label="Message history">
        <h2 className="text-[10px] font-black uppercase tracking-wider text-muted-foreground mb-3 flex items-center gap-2">
          <MessageSquare className="h-3.5 w-3.5" />
          Previous messages
        </h2>

        {loading ? (
          <div className="flex flex-col gap-3">
            {[...Array(2)].map((_, i) => <Skeleton key={i} className="h-32" />)}
          </div>
        ) : error ? (
          <div className="border border-border bg-card p-6 text-center">
            <XCircle className="mx-auto h-5 w-5 text-destructive mb-2" />
            <p className="text-sm text-destructive font-semibold mb-3">{error}</p>
            <button onClick={load}
              className="border border-border bg-black px-4 py-2 text-xs font-black uppercase tracking-wider text-white hover:shadow-[var(--shadow-sm)] transition-shadow">
              Retry
            </button>
          </div>
        ) : inquiries.length === 0 ? (
          <div className="border border-border bg-card p-10 text-center">
            <MessageSquare className="mx-auto h-6 w-6 text-muted-foreground opacity-40 mb-2" />
            <p className="text-sm text-muted-foreground">No messages yet. Send your first question above.</p>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            {inquiries.map(inq => <InquiryCard key={inq.id} inquiry={inq} />)}
          </div>
        )}
      </section>
    </div>
  )
}
