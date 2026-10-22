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
    resolved_at: string | null
    resolved_by: string | null
    resolution_note: string | null
  }
  original_message: string
  messages: Msg[]
}
type Suggestion = {
  draft: string
  product: string | null
  facts_used: { label: string; value: string }[]
  missing: string[]
  warnings: string[]
  uses_demo_data: boolean
}
type HistoryItem = {
  inquiry_id: string
  created_at: string | null
  state: "open" | "resolved"
  resolved_at: string | null
  resolved_by: string | null
  resolution_note: string | null
  priority: "urgent" | "high" | "normal" | "low" | null
  category_label: string
  summary: string
  replies: number
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

const J = { "Content-Type": "application/json" } // add the console's extra POST headers here if it uses any (e.g. CSRF)

// ---------------------------------------------------------------------------
// Company inquiry history: every inquiry (open and resolved) for one company.
// ---------------------------------------------------------------------------
function HistoryList({
  clientId,
  currentId,
  onPick,
  refreshKey,
}: {
  clientId: string
  currentId?: string
  onPick: (inquiryId: string) => void
  refreshKey?: number
}) {
  const [items, setItems] = useState<HistoryItem[] | null>(null)
  const [company, setCompany] = useState("")
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const res = await fetch(`/api/console/clients/${encodeURIComponent(clientId)}/inquiry-history`, {
          credentials: "same-origin",
        })
        if (!res.ok) throw new Error("Couldn't load the history.")
        const data = await res.json()
        if (!cancelled) {
          setItems(Array.isArray(data?.inquiries) ? data.inquiries : [])
          setCompany(typeof data?.company === "string" ? data.company : "")
          setError(null)
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Couldn't load the history.")
      }
    })()
    return () => {
      cancelled = true
    }
  }, [clientId, refreshKey])

  if (error) return <p className="px-6 py-4 text-sm text-red-700">{error}</p>
  if (!items) return <p className="px-6 py-4 font-mono text-sm text-neutral-500">Loading history…</p>
  if (items.length === 0) return <p className="px-6 py-4 font-mono text-sm text-neutral-500">No inquiries yet.</p>

  const open = items.filter((i) => i.state === "open").length
  return (
    <div>
      <p className="px-6 pt-3 font-mono text-[11px] text-neutral-500">
        {company ? `${company} · ` : ""}
        {items.length} inquir{items.length === 1 ? "y" : "ies"} · {open} open · {items.length - open} resolved
      </p>
      <ul className="max-h-[48vh] divide-y overflow-y-auto">
        {items.map((i) => (
          <li key={i.inquiry_id} className={`px-6 py-3 ${i.inquiry_id === currentId ? "bg-neutral-50" : ""}`}>
            <div className="flex flex-wrap items-center gap-2">
              <span
                className={`rounded px-2 py-0.5 text-[10px] font-bold uppercase ${
                  i.state === "open" ? "bg-black text-white" : "bg-green-100 text-green-800"
                }`}
              >
                {i.state}
              </span>
              {i.priority && (
                <span className={`rounded px-2 py-0.5 text-[10px] font-bold uppercase ${CHIP[i.priority]}`}>
                  {i.priority}
                </span>
              )}
              <span className="font-mono text-[11px] text-neutral-500">
                {i.category_label} · {ago(i.created_at)} · {i.replies} repl{i.replies === 1 ? "y" : "ies"}
              </span>
              <button
                type="button"
                onClick={() => onPick(i.inquiry_id)}
                className="ml-auto rounded border px-2 py-0.5 text-[11px] font-bold uppercase hover:bg-neutral-100"
              >
                {i.inquiry_id === currentId ? "Viewing" : "View"}
              </button>
            </div>
            <p className="mt-1 text-sm">{i.summary || "No summary"}</p>
            {i.state === "resolved" && (
              <p className="mt-0.5 font-mono text-[11px] text-neutral-500">
                Resolved {ago(i.resolved_at)}
                {i.resolved_by ? ` by ${i.resolved_by}` : ""}
                {i.resolution_note ? ` — ${i.resolution_note}` : ""}
              </p>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Inquiry window: read, get an AI reply suggestion, reply, resolve, see company history.
// ---------------------------------------------------------------------------
export function InquiryDetailModal({
  inquiryId,
  onClose,
  onOpenClient,
  onChanged,
  startOnHistory = false,
}: {
  inquiryId: string
  onClose: () => void
  onOpenClient?: (clientId: string) => void
  onChanged?: () => void
  startOnHistory?: boolean
}) {
  const [currentId, setCurrentId] = useState(inquiryId)
  const [tab, setTab] = useState<"conversation" | "history">(startOnHistory ? "history" : "conversation")
  const [detail, setDetail] = useState<Detail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [reply, setReply] = useState("")
  const [sending, setSending] = useState(false)
  const [note, setNote] = useState<string | null>(null)
  const [suggestion, setSuggestion] = useState<Suggestion | null>(null)
  const [suggesting, setSuggesting] = useState(false)
  const [suggestError, setSuggestError] = useState<string | null>(null)
  const [resolving, setResolving] = useState(false)
  const [resolveNote, setResolveNote] = useState("")
  const [busy, setBusy] = useState(false)
  const [historyKey, setHistoryKey] = useState(0)
  const threadEnd = useRef<HTMLDivElement>(null)

  const load = useCallback(async () => {
    try {
      const res = await fetch(`/api/console/inquiry/${encodeURIComponent(currentId)}`, { credentials: "same-origin" })
      if (res.status === 404) throw new Error("This inquiry isn't available (it may belong to another rep).")
      if (!res.ok) throw new Error("Couldn't load this inquiry. Try again.")
      setDetail(await res.json())
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't load this inquiry.")
    }
  }, [currentId])

  useEffect(() => {
    setDetail(null)
    setSuggestion(null)
    setSuggestError(null)
    setResolving(false)
    setNote(null)
    load()
  }, [load])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !sending && !busy) onClose()
    }
    document.addEventListener("keydown", onKey)
    return () => document.removeEventListener("keydown", onKey)
  }, [onClose, sending, busy])

  useEffect(() => {
    threadEnd.current?.scrollIntoView({ block: "end" })
  }, [detail?.messages.length, tab])

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
        { method: "POST", credentials: "same-origin", headers: J, body: JSON.stringify({ body: text }) },
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
      setSuggestion(null)
      setNote("Reply sent. The company will see it in their portal.")
      setHistoryKey((k) => k + 1)
      onChanged?.()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Reply could not be sent.")
    } finally {
      setSending(false)
    }
  }

  async function suggest() {
    if (!detail || suggesting) return
    setSuggesting(true)
    setSuggestError(null)
    setSuggestion(null)
    try {
      const res = await fetch(`/api/console/inquiry/${encodeURIComponent(detail.inquiry.inquiry_id)}/suggest-reply`, {
        method: "POST",
        credentials: "same-origin",
        headers: J,
      })
      if (res.status === 429) throw new Error("Suggestion limit reached. Try again later.")
      if (!res.ok) throw new Error("The AI couldn't suggest a reply right now. You can still write one yourself.")
      setSuggestion(await res.json())
    } catch (e) {
      setSuggestError(e instanceof Error ? e.message : "The AI couldn't suggest a reply.")
    } finally {
      setSuggesting(false)
    }
  }

  async function act(kind: "resolve" | "reopen") {
    if (!detail || busy) return
    setBusy(true)
    setError(null)
    try {
      const res = await fetch(`/api/console/inquiry/${encodeURIComponent(detail.inquiry.inquiry_id)}/${kind}`, {
        method: "POST",
        credentials: "same-origin",
        headers: J,
        body: kind === "resolve" ? JSON.stringify({ note: resolveNote.trim() || null }) : undefined,
      })
      if (!res.ok && res.status !== 409) throw new Error(`Couldn't ${kind} this inquiry. Try again.`)
      setResolving(false)
      setResolveNote("")
      setHistoryKey((k) => k + 1)
      onChanged?.()
      if (kind === "resolve") onClose()
      else await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : `Couldn't ${kind} this inquiry.`)
    } finally {
      setBusy(false)
    }
  }

  const inq = detail?.inquiry
  const resolved = !!inq?.resolved_at
  const thread: Msg[] = detail
    ? [{ sender: "company", body: detail.original_message, created_at: inq?.created_at ?? null }, ...detail.messages]
    : []

  return (
    <div
      className="fixed inset-0 z-[60] flex items-start justify-center overflow-y-auto bg-black/60 p-4 sm:p-8"
      onMouseDown={() => !sending && !busy && onClose()}
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
            {inq && (
              <div className="mt-2 flex flex-wrap items-center gap-2">
                {inq.priority && (
                  <span className={`rounded px-2 py-0.5 text-[10px] font-bold uppercase ${CHIP[inq.priority]}`}>
                    {inq.priority}
                  </span>
                )}
                <span className="rounded bg-neutral-100 px-2 py-0.5 text-[10px] uppercase text-neutral-500">
                  {inq.triage_status === "ai"
                    ? "AI-labelled"
                    : inq.triage_status === "failed"
                      ? "Rules only · AI unavailable"
                      : "Rule-labelled · AI not finished"}
                </span>
                {resolved && (
                  <span className="rounded bg-green-100 px-2 py-0.5 text-[10px] font-bold uppercase text-green-800">
                    Resolved
                  </span>
                )}
              </div>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={sending || busy}
            aria-label="Close"
            className="rounded border px-2.5 py-1 text-sm font-bold hover:bg-neutral-100 disabled:opacity-50"
          >
            ✕
          </button>
        </div>

        {inq && (
          <div className="flex gap-1 border-b px-6 pt-2">
            {(["conversation", "history"] as const).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setTab(t)}
                className={`border-b-2 px-3 py-2 text-[11px] font-bold uppercase tracking-wide ${
                  tab === t ? "border-black text-black" : "border-transparent text-neutral-400 hover:text-black"
                }`}
              >
                {t === "conversation" ? "Conversation" : "Company history"}
              </button>
            ))}
          </div>
        )}

        {!detail && !error && <p className="px-6 py-8 font-mono text-sm text-neutral-500">Loading…</p>}
        {!detail && error && <p className="px-6 py-8 text-sm text-red-700">{error}</p>}

        {detail && inq && tab === "history" && (
          <>
            <HistoryList
              clientId={inq.client_id}
              currentId={currentId}
              refreshKey={historyKey}
              onPick={(id) => {
                setCurrentId(id)
                setTab("conversation")
              }}
            />
            <div className="border-t px-6 py-3">
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
            </div>
          </>
        )}

        {detail && inq && tab === "conversation" && (
          <>
            {inq.reasons.length > 0 && (
              <p className="border-b bg-neutral-50 px-6 py-2 font-mono text-[11px] text-neutral-600">
                Why this priority: {inq.reasons.join(" · ")}
              </p>
            )}
            {resolved && (
              <p className="border-b bg-green-50 px-6 py-2 font-mono text-[11px] text-green-900">
                Resolved {ago(inq.resolved_at)}
                {inq.resolved_by ? ` by ${inq.resolved_by}` : ""}
                {inq.resolution_note ? ` — ${inq.resolution_note}` : ""}
              </p>
            )}

            <div className="max-h-[36vh] space-y-3 overflow-y-auto px-6 py-4" aria-live="polite">
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

            {resolved ? (
              <div className="flex flex-wrap items-center gap-2 border-t px-6 py-4">
                <button
                  type="button"
                  onClick={() => act("reopen")}
                  disabled={busy}
                  className="rounded bg-black px-4 py-2 text-xs font-bold uppercase text-white disabled:opacity-50"
                >
                  {busy ? "Reopening…" : "Reopen inquiry"}
                </button>
                {error && <span className="text-xs text-red-700">{error}</span>}
              </div>
            ) : (
              <div className="border-t px-6 py-4">
                <div className="mb-1 flex items-center justify-between gap-2">
                  <label htmlFor="inquiry-reply" className="text-[11px] font-bold uppercase tracking-wide">
                    Reply to {inq.company}
                  </label>
                  <button
                    type="button"
                    onClick={suggest}
                    disabled={suggesting}
                    className="rounded border border-black px-3 py-1 text-[11px] font-bold uppercase hover:bg-black hover:text-white disabled:opacity-50"
                  >
                    {suggesting ? "Thinking…" : "✦ Suggest reply (AI)"}
                  </button>
                </div>

                {suggestError && <p className="mb-2 text-xs text-red-700">{suggestError}</p>}
                {suggestion && (
                  <div className="mb-3 rounded border border-[#FFD600] bg-yellow-50 p-3">
                    <div className="mb-1 flex flex-wrap items-center gap-2 font-mono text-[10px] uppercase text-neutral-600">
                      <span className="font-bold text-black">AI suggestion</span>
                      {suggestion.product && <span>· about {suggestion.product}</span>}
                      {suggestion.uses_demo_data && (
                        <span className="rounded bg-neutral-800 px-1.5 py-px text-white">Demo data</span>
                      )}
                    </div>
                    <p className="whitespace-pre-wrap text-sm">{suggestion.draft}</p>
                    {suggestion.facts_used.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {suggestion.facts_used.map((f, i) => (
                          <span key={i} className="rounded bg-white px-2 py-0.5 font-mono text-[10px] ring-1 ring-neutral-300">
                            {f.label}: {f.value}
                          </span>
                        ))}
                      </div>
                    )}
                    {suggestion.missing.length > 0 && (
                      <p className="mt-2 rounded bg-amber-100 px-2 py-1 text-xs text-amber-900">
                        Not in the catalog (confirm before replying): {suggestion.missing.join(", ")}
                      </p>
                    )}
                    {suggestion.warnings.map((w, i) => (
                      <p key={i} className="mt-2 rounded bg-red-100 px-2 py-1 text-xs text-red-800">
                        ⚠ {w}
                      </p>
                    ))}
                    {suggestion.uses_demo_data && (
                      <p className="mt-2 font-mono text-[10px] text-neutral-500">
                        This product is demo data, not a real catalog item.
                      </p>
                    )}
                    <div className="mt-2 flex gap-2">
                      <button
                        type="button"
                        onClick={() => {
                          setReply(suggestion.draft)
                          setSuggestion(null)
                        }}
                        className="rounded bg-black px-3 py-1 text-[11px] font-bold uppercase text-white"
                      >
                        Use this draft
                      </button>
                      <button
                        type="button"
                        onClick={() => setSuggestion(null)}
                        className="rounded border px-3 py-1 text-[11px] font-bold uppercase hover:bg-white"
                      >
                        Dismiss
                      </button>
                    </div>
                  </div>
                )}

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
                  placeholder="Write your reply, or use the AI suggestion. You review everything before it is sent."
                  className="w-full resize-y rounded border px-3 py-2 text-sm"
                />
                {error && <p className="mt-2 text-xs text-red-700">{error}</p>}
                {note && !error && <p className="mt-2 text-xs text-green-700">{note}</p>}

                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={send}
                    disabled={sending || !reply.trim()}
                    className="rounded bg-black px-4 py-2 text-xs font-bold uppercase text-white disabled:opacity-50"
                  >
                    {sending ? "Sending…" : "Send reply"}
                  </button>
                  {!resolving && (
                    <button
                      type="button"
                      onClick={() => setResolving(true)}
                      className="rounded border border-green-700 px-4 py-2 text-xs font-bold uppercase text-green-800 hover:bg-green-50"
                    >
                      Resolve
                    </button>
                  )}
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

                {resolving && (
                  <div className="mt-3 rounded border border-green-700 bg-green-50 p-3">
                    <label htmlFor="resolve-note" className="mb-1 block text-[11px] font-bold uppercase">
                      Resolution note (optional, saved in the company history)
                    </label>
                    <input
                      id="resolve-note"
                      value={resolveNote}
                      onChange={(e) => setResolveNote(e.target.value)}
                      maxLength={500}
                      placeholder="e.g. Sent datasheet and confirmed weight by phone"
                      className="w-full rounded border bg-white px-3 py-2 text-sm"
                    />
                    <div className="mt-2 flex gap-2">
                      <button
                        type="button"
                        onClick={() => act("resolve")}
                        disabled={busy}
                        className="rounded bg-green-700 px-4 py-2 text-xs font-bold uppercase text-white disabled:opacity-50"
                      >
                        {busy ? "Resolving…" : "Confirm resolve"}
                      </button>
                      <button
                        type="button"
                        onClick={() => setResolving(false)}
                        disabled={busy}
                        className="rounded border bg-white px-4 py-2 text-xs font-bold uppercase"
                      >
                        Cancel
                      </button>
                    </div>
                    <p className="mt-2 font-mono text-[10px] text-neutral-500">
                      Resolving is internal: the company is not notified. Send a reply first if they should hear from you.
                    </p>
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Drop-in section for a company's detail drawer: its full inquiry history. Clicking "View" opens the inquiry window.
// ---------------------------------------------------------------------------
export function CompanyInquiryHistory({
  clientId,
  onOpenClient,
}: {
  clientId: string
  onOpenClient?: (clientId: string) => void
}) {
  const [openId, setOpenId] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  return (
    <section className="rounded-lg border">
      <h3 className="border-b px-6 py-3 text-[11px] font-bold uppercase tracking-wide">Inquiry history</h3>
      <HistoryList clientId={clientId} onPick={setOpenId} refreshKey={refreshKey} />
      {openId && (
        <InquiryDetailModal
          inquiryId={openId}
          onClose={() => setOpenId(null)}
          onOpenClient={onOpenClient}
          onChanged={() => setRefreshKey((k) => k + 1)}
        />
      )}
    </section>
  )
}

export default InquiryDetailModal
