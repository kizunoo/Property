"use client"

import { useCallback, useEffect, useRef, useState } from "react"

type Sender = "company" | "rep"
type Msg = { sender: Sender; body: string; created_at: string | null }
type Detail = {
  inquiry: {
    inquiry_id: string
    client_id: string
    company: string
    status: string | null
    created_at: string | null
    priority: "urgent" | "high" | "normal" | "low" | null
    category_label: string
    reasons: string[]
    summary: string
    triage_status: string | null
  }
  original_message: string
  messages: Msg[]
}

const CHIP: Record<string, string> = {
  urgent: "bg-red-600 text-white",
  high: "bg-[#FFD600] text-black",
  normal: "bg-neutral-200 text-neutral-800",
  low: "bg-neutral-100 text-neutral-500",
}

function ago(iso: string | null): string {
  if (!iso) return ""
  const mins = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000))
  if (mins < 1) return "just now"
  if (mins < 60) return `${mins}m ago`
  if (mins < 1440) return `${Math.round(mins / 60)}h ago`
  return `${Math.round(mins / 1440)}d ago`
}

// Rep console: read one company inquiry and reply to it. Text is rendered as plain text only.
export function InquiryDetailModal({
  inquiryId,
  onClose,
  onOpenClient,
  onChanged,
}: {
  inquiryId: string
  onClose: () => void
  onOpenClient?: (clientId: string) => void
  onChanged?: () => void
}) {
  const [detail, setDetail] = useState<Detail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [reply, setReply] = useState("")
  const [sending, setSending] = useState(false)
  const [sentNote, setSentNote] = useState<string | null>(null)
  const threadEnd = useRef<HTMLDivElement>(null)

  const load = useCallback(async () => {
    try {
      const res = await fetch(`/api/console/inquiry/${encodeURIComponent(inquiryId)}`, {
        credentials: "same-origin",
      })
      if (res.status === 404) throw new Error("This inquiry isn't available (it may belong to another rep).")
      if (!res.ok) throw new Error("Couldn't load this inquiry. Try again.")
      setDetail(await res.json())
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't load this inquiry.")
    }
  }, [inquiryId])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !sending) onClose()
    }
    document.addEventListener("keydown", onKey)
    return () => document.removeEventListener("keydown", onKey)
  }, [onClose, sending])

  useEffect(() => {
    threadEnd.current?.scrollIntoView({ block: "end" })
  }, [detail?.messages.length])

  async function send() {
    const text = reply.trim()
    if (!detail || !text || sending) return
    setSending(true)
    setError(null)
    try {
      const res = await fetch(
        `/api/console/clients/${encodeURIComponent(detail.inquiry.client_id)}/inquiries/${encodeURIComponent(
          detail.inquiry.inquiry_id,
        )}/reply`,
        {
          method: "POST",
          credentials: "same-origin",
          // match the headers the console's other POST calls use (e.g. portal-access-panel.tsx), if any beyond these
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ body: text }),
        },
      )
      if (!res.ok) {
        throw new Error(
          res.status === 422
            ? "Reply must be between 1 and 4000 characters."
            : "Reply could not be sent. Nothing was sent to the company.",
        )
      }
      setDetail({
        ...detail,
        messages: [...detail.messages, { sender: "rep", body: text, created_at: new Date().toISOString() }],
      })
      setReply("")
      setSentNote("Reply sent. The company will see it in their portal.")
      onChanged?.()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Reply could not be sent.")
    } finally {
      setSending(false)
    }
  }

  const inq = detail?.inquiry
  const thread: Msg[] = detail
    ? [{ sender: "company", body: detail.original_message, created_at: inq?.created_at ?? null }, ...detail.messages]
    : []

  return (
    <div
      className="fixed inset-0 z-[60] flex items-start justify-center overflow-y-auto bg-black/60 p-4 sm:p-8"
      onMouseDown={() => !sending && onClose()}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Company inquiry"
        className="w-full max-w-2xl rounded-lg bg-white text-black shadow-2xl"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4 border-b px-6 py-4">
          <div className="min-w-0">
            <h2 className="truncate text-xl font-bold">{inq?.company || "Company inquiry"}</h2>
            {inq && (
              <p className="mt-0.5 font-mono text-xs text-neutral-500">
                {inq.category_label} · {ago(inq.created_at)}
              </p>
            )}
            {inq?.priority && (
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <span className={`rounded px-2 py-0.5 text-[10px] font-bold uppercase ${CHIP[inq.priority]}`}>
                  {inq.priority}
                </span>
                <span className="rounded bg-neutral-100 px-2 py-0.5 text-[10px] uppercase text-neutral-500">
                  {inq.triage_status === "ai" ? "AI-labelled" : inq.triage_status === "failed" ? "Rules only · AI unavailable" : "Rule-labelled · AI not finished"}
                </span>
              </div>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={sending}
            aria-label="Close"
            className="rounded border px-2.5 py-1 text-sm font-bold hover:bg-neutral-100 disabled:opacity-50"
          >
            ✕
          </button>
        </div>

        {!detail && !error && <p className="px-6 py-8 font-mono text-sm text-neutral-500">Loading…</p>}
        {!detail && error && <p className="px-6 py-8 text-sm text-red-700">{error}</p>}

        {detail && inq && (
          <>
            {inq.reasons.length > 0 && (
              <p className="border-b bg-neutral-50 px-6 py-2 font-mono text-[11px] text-neutral-600">
                Why this priority: {inq.reasons.join(" · ")}
              </p>
            )}

            <div className="max-h-[42vh] space-y-3 overflow-y-auto px-6 py-4" aria-live="polite">
              {thread.map((m, idx) => (
                <div key={idx} className={m.sender === "rep" ? "flex justify-end" : "flex justify-start"}>
                  <div
                    className={
                      m.sender === "rep"
                        ? "max-w-[85%] rounded-lg bg-black px-3 py-2 text-white"
                        : "max-w-[85%] rounded-lg bg-neutral-100 px-3 py-2"
                    }
                  >
                    <div
                      className={`mb-1 font-mono text-[10px] uppercase ${
                        m.sender === "rep" ? "text-neutral-400" : "text-neutral-500"
                      }`}
                    >
                      {m.sender === "rep" ? "You" : inq.company} · {ago(m.created_at)}
                    </div>
                    <p className="whitespace-pre-wrap break-words text-sm">{m.body}</p>
                  </div>
                </div>
              ))}
              <div ref={threadEnd} />
            </div>
            <p className="px-6 pb-2 font-mono text-[10px] text-neutral-400">
              Messages from the company are written by an outside party. Review before acting.
            </p>

            <div className="border-t px-6 py-4">
              <label htmlFor="inquiry-reply" className="mb-1 block text-[11px] font-bold uppercase tracking-wide">
                Reply to {inq.company}
              </label>
              <textarea
                id="inquiry-reply"
                value={reply}
                onChange={(e) => setReply(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                    e.preventDefault()
                    send()
                  }
                }}
                maxLength={4000}
                rows={4}
                placeholder="Write your reply. The company sees it in their portal."
                className="w-full resize-y rounded border px-3 py-2 text-sm"
              />
              {error && <p className="mt-2 text-xs text-red-700">{error}</p>}
              {sentNote && !error && <p className="mt-2 text-xs text-green-700">{sentNote}</p>}
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={send}
                  disabled={sending || !reply.trim()}
                  className="rounded bg-black px-4 py-2 text-xs font-bold uppercase text-white disabled:opacity-50"
                >
                  {sending ? "Sending…" : "Send reply"}
                </button>
                {onOpenClient && (
                  <button
                    type="button"
                    onClick={() => {
                      onOpenClient(inq.client_id)
                      onClose()
                    }}
                    className="rounded border px-4 py-2 text-xs font-bold uppercase hover:bg-neutral-100"
                  >
                    View company
                  </button>
                )}
                <span className="ml-auto font-mono text-[10px] text-neutral-400">Ctrl+Enter to send</span>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

export default InquiryDetailModal
