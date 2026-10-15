"use client"

import { useEffect, useState, useCallback } from "react"
import {
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  HelpCircle,
  MessageSquare,
  Send,
  XCircle,
} from "lucide-react"
import type { DashboardData, Inquiry, InquiryMessage, MatchUnit } from "@/lib/portal-types"
import { fetchInquiries, submitInquiry, postInquiryMessage, markInquiryRead } from "@/lib/portal-api"
import { useToast } from "@/hooks/use-toast"
import { Skeleton } from "@/components/ui/skeleton"

// ─── Status config ────────────────────────────────────────────────────────────

const STATUS_BADGE: Record<string, { label: string; className: string }> = {
  open: { label: "Open — awaiting reply", className: "bg-amber-50 border border-amber-200 text-amber-700" },
  replied: { label: "Replied", className: "bg-primary border border-primary/30 text-primary-foreground" },
  closed: { label: "Closed", className: "bg-muted border border-border text-muted-foreground" },
}

function formatDate(s: string): string {
  try {
    return new Date(s).toLocaleDateString("en-MY", {
      day: "numeric",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    })
  } catch {
    return s
  }
}

// ─── Threaded Inquiry Card ───────────────────────────────────────────────────

function InquiryCard({
  inquiry,
  clientId,
  onReplySuccess,
}: {
  inquiry: Inquiry
  clientId: string
  onReplySuccess: () => void
}) {
  const { toast } = useToast()
  const badge = STATUS_BADGE[inquiry.status] ?? STATUS_BADGE.open
  const [expanded, setExpanded] = useState(false)
  const [replyText, setReplyText] = useState("")
  const [sending, setSending] = useState(false)
  const [unreadCount, setUnreadCount] = useState(inquiry.unread_count || 0)

  // When expanding an inquiry with unread messages, mark them as read
  async function handleToggleExpand() {
    const nextState = !expanded
    setExpanded(nextState)
    if (nextState && unreadCount > 0) {
      try {
        await markInquiryRead(clientId, inquiry.id)
        setUnreadCount(0)
      } catch {
        // Silently ignore
      }
    }
  }

  async function handleSendReply(e: React.FormEvent) {
    e.preventDefault()
    if (!replyText.trim() || sending) return
    setSending(true)
    try {
      await postInquiryMessage(clientId, inquiry.id, replyText.trim())
      setReplyText("")
      toast({ title: "Reply sent", description: "Your message was sent to your sales representative." })
      onReplySuccess()
    } catch (err: any) {
      toast({
        title: "Failed to send message",
        description: err?.message || "Please check your network connection.",
        variant: "destructive",
      })
    } finally {
      setSending(false)
    }
  }

  const threadMessages: InquiryMessage[] = inquiry.messages || []

  return (
    <div className="border border-border bg-card shadow-[var(--shadow-sm)] flex flex-col">
      {/* Header */}
      <div
        onClick={handleToggleExpand}
        className="p-5 flex items-start justify-between gap-3 cursor-pointer hover:bg-secondary/40 transition-colors select-none"
      >
        <div className="flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            {inquiry.property_name && (
              <p className="text-[10px] font-black uppercase tracking-wider text-muted-foreground">
                {inquiry.property_name}
              </p>
            )}
            <span
              className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 text-[10px] font-black uppercase tracking-wider ${badge.className}`}
            >
              {inquiry.status === "replied" ? (
                <CheckCircle2 className="h-3 w-3" />
              ) : (
                <HelpCircle className="h-3 w-3" />
              )}
              {badge.label}
            </span>

            {unreadCount > 0 && (
              <span className="inline-flex items-center px-2 py-0.5 text-[9px] font-black uppercase bg-primary text-primary-foreground">
                {unreadCount} new
              </span>
            )}
          </div>

          <p className="text-sm font-semibold mt-2 line-clamp-1">{inquiry.message}</p>
        </div>

        <div className="flex items-center gap-3 shrink-0">
          <span className="text-[10px] text-muted-foreground/70">{formatDate(inquiry.created_at)}</span>
          <button
            type="button"
            className="p-1 text-muted-foreground hover:text-foreground"
            aria-label={expanded ? "Collapse conversation" : "Expand conversation"}
          >
            {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </button>
        </div>
      </div>

      {/* Expanded Thread */}
      {expanded && (
        <div className="border-t border-border p-5 flex flex-col gap-4 bg-secondary/10">
          {/* Messages stream */}
          <div className="flex flex-col gap-3">
            {threadMessages.length > 0 ? (
              threadMessages.map((m) => {
                const isCompany = m.sender === "company"
                return (
                  <div
                    key={m.id}
                    className={`flex flex-col gap-1 max-w-[85%] ${
                      isCompany ? "self-end items-end" : "self-start items-start"
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-[9px] font-black uppercase tracking-wider text-muted-foreground">
                        {isCompany ? "You" : "Sales Representative"}
                      </span>
                      <span className="text-[9px] text-muted-foreground/60">{formatDate(m.created_at)}</span>
                    </div>
                    <div
                      className={`p-3 text-xs leading-relaxed border ${
                        isCompany
                          ? "bg-black text-white border-black"
                          : "bg-card text-foreground border-border"
                      }`}
                    >
                      {m.body}
                    </div>
                  </div>
                )
              })
            ) : (
              // Fallback to legacy single message + agent_reply
              <>
                <div className="self-end items-end flex flex-col gap-1 max-w-[85%]">
                  <span className="text-[9px] font-black uppercase text-muted-foreground">You</span>
                  <div className="bg-black text-white border border-black p-3 text-xs">
                    {inquiry.message}
                  </div>
                </div>
                {inquiry.agent_reply && (
                  <div className="self-start items-start flex flex-col gap-1 max-w-[85%]">
                    <span className="text-[9px] font-black uppercase text-muted-foreground">
                      Sales Representative
                    </span>
                    <div className="bg-card text-foreground border border-border p-3 text-xs">
                      {inquiry.agent_reply}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>

          {/* Reply input */}
          <form onSubmit={handleSendReply} className="flex gap-2 pt-3 border-t border-border">
            <input
              type="text"
              value={replyText}
              onChange={(e) => setReplyText(e.target.value)}
              placeholder="Type your reply to the sales representative..."
              className="flex-1 border border-border bg-white px-3 py-2 text-xs text-black focus:outline-none focus-visible:border-primary"
            />
            <button
              type="submit"
              disabled={sending || !replyText.trim()}
              className="group flex items-center justify-center gap-1.5 border border-border bg-black px-4 py-2 text-xs font-black uppercase tracking-wider text-white hover:shadow-[var(--shadow-sm)] disabled:opacity-40"
            >
              <span>{sending ? "Sending…" : "Reply"}</span>
              <Send className="h-3 w-3 text-primary" />
            </button>
          </form>
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
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!message.trim() || !selectedPropertyId) return
    setLoading(true)
    setError(null)
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
        <h2 className="text-base font-bold tracking-tight mt-1">Start a new inquiry</h2>
        <p className="text-sm text-muted-foreground mt-0.5">
          Have questions about specific robot specs, deployment footprints, or warranty options?
        </p>
      </div>

      {/* Unit selector */}
      {units.length > 0 && (
        <label className="flex flex-col gap-2">
          <span className="text-xs font-black uppercase tracking-wider">About which unit?</span>
          <select
            id="inquiry-property-select"
            value={selectedPropertyId}
            onChange={(e) => setSelectedPropertyId(e.target.value)}
            className="border border-border bg-white px-3 py-2.5 text-sm text-black focus:outline-none focus-visible:border-primary"
          >
            {units.map((u) => (
              <option key={u.property_id} value={u.property_id}>
                {u.name}
              </option>
            ))}
          </select>
        </label>
      )}

      <label className="flex flex-col gap-2">
        <span className="text-xs font-black uppercase tracking-wider">Your question</span>
        <textarea
          id="inquiry-message"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
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
        {!loading && (
          <ArrowRight
            className="h-4 w-4 text-primary transition-transform group-hover:translate-x-0.5"
            strokeWidth={3}
          />
        )}
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
  const [totalUnread, setTotalUnread] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const units = data?.matches ?? []

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const d = await fetchInquiries(clientId)
      setInquiries(d.inquiries)
      setTotalUnread(d.total_unread || 0)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load messages.")
    } finally {
      setLoading(false)
    }
  }, [clientId])

  useEffect(() => {
    load()
  }, [load])

  return (
    <div className="mx-auto max-w-3xl px-4 sm:px-6 py-10 flex flex-col gap-8">
      {/* New inquiry form */}
      {units.length > 0 && <NewInquiryForm clientId={clientId} units={units} onSuccess={load} />}

      {/* History */}
      <section aria-label="Message history">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-[10px] font-black uppercase tracking-wider text-muted-foreground flex items-center gap-2">
            <MessageSquare className="h-3.5 w-3.5" />
            Previous inquiries ({inquiries.length})
          </h2>
          {totalUnread > 0 && (
            <span className="text-[10px] font-bold text-primary">
              {totalUnread} unread message{totalUnread > 1 ? "s" : ""}
            </span>
          )}
        </div>

        {loading ? (
          <div className="flex flex-col gap-3">
            {[...Array(2)].map((_, i) => (
              <Skeleton key={i} className="h-32" />
            ))}
          </div>
        ) : error ? (
          <div className="border border-border bg-card p-6 text-center">
            <XCircle className="mx-auto h-5 w-5 text-destructive mb-2" />
            <p className="text-sm text-destructive font-semibold mb-3">{error}</p>
            <button
              onClick={load}
              className="border border-border bg-black px-4 py-2 text-xs font-black uppercase tracking-wider text-white hover:shadow-[var(--shadow-sm)] transition-shadow"
            >
              Retry
            </button>
          </div>
        ) : inquiries.length === 0 ? (
          <div className="border border-border bg-card p-10 text-center">
            <MessageSquare className="mx-auto h-6 w-6 text-muted-foreground opacity-40 mb-2" />
            <p className="text-sm text-muted-foreground">
              No inquiries yet. Send your first question above.
            </p>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            {inquiries.map((inq) => (
              <InquiryCard
                key={inq.id}
                inquiry={inq}
                clientId={clientId}
                onReplySuccess={load}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
