"use client"

import { useRef, useState } from "react"

type Msg = { role: "user" | "ai"; text: string }

const ERRORS: Record<number, string> = {
  401: "Your session expired. Please sign in again.",
  422: "That message isn't valid. Keep it under 1000 characters.",
  429: "Copilot limit reached. Try again later.",
  502: "Copilot is unavailable right now.",
  504: "Copilot took too long. Try a simpler question.",
}

// Rep-console only. Replies are plain text (never rendered as HTML).
export function CopilotPanel() {
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState<Msg[]>([])
  const [input, setInput] = useState("")
  const [busy, setBusy] = useState(false)
  const conversationId = useRef("")

  async function send() {
    const text = input.trim()
    if (!text || busy) return
    if (!conversationId.current) conversationId.current = crypto.randomUUID()
    setMessages((m) => [...m, { role: "user", text }])
    setInput("")
    setBusy(true)
    try {
      const res = await fetch("/api/console/copilot", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" }, // add the project's CSRF header here if its other console calls use one
        body: JSON.stringify({ message: text, conversation_id: conversationId.current }),
      })
      if (!res.ok) {
        setMessages((m) => [...m, { role: "ai", text: ERRORS[res.status] ?? "Something went wrong." }])
        return
      }
      const data = await res.json()
      const reply = typeof data?.reply === "string" ? data.reply : "No answer."
      setMessages((m) => [...m, { role: "ai", text: reply }])
    } catch {
      setMessages((m) => [...m, { role: "ai", text: "Network error. Please try again." }])
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="fixed bottom-4 right-24 z-50 rounded-full bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-lg"
        aria-expanded={open}
      >
        {open ? "Close Copilot" : "Ask Copilot"}
      </button>

      {open && (
        <div className="fixed bottom-16 right-24 z-50 flex h-[28rem] w-[22rem] max-w-[calc(100vw-2rem)] flex-col rounded-lg border bg-background text-foreground shadow-xl">
          <div className="border-b px-3 py-2 text-sm font-medium">
            Rep Copilot
            <span className="block text-xs font-normal text-muted-foreground">
              AI draft: review before sending. It can read your data but cannot send or change anything.
            </span>
          </div>

          <div className="flex-1 space-y-2 overflow-y-auto px-3 py-2 text-sm" aria-live="polite">
            {messages.length === 0 && (
              <p className="text-muted-foreground">
                Try: &ldquo;Who are my top priority clients?&rdquo; or &ldquo;Draft a follow-up for the first one.&rdquo;
              </p>
            )}
            {messages.map((m, i) => (
              <div
                key={i}
                className={
                  m.role === "user"
                    ? "ml-8 rounded-md bg-primary px-2 py-1 text-primary-foreground"
                    : "mr-8 whitespace-pre-wrap rounded-md bg-muted px-2 py-1"
                }
              >
                {m.text}
              </div>
            ))}
            {busy && <p className="text-muted-foreground">Thinking…</p>}
          </div>

          <div className="flex gap-2 border-t p-2">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault()
                  send()
                }
              }}
              maxLength={1000}
              rows={2}
              placeholder="Ask about your clients…"
              className="flex-1 resize-none rounded-md border bg-background px-2 py-1 text-sm"
            />
            <button
              type="button"
              onClick={send}
              disabled={busy || !input.trim()}
              className="rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground disabled:opacity-50"
            >
              Send
            </button>
          </div>
        </div>
      )}
    </>
  )
}

export default CopilotPanel
