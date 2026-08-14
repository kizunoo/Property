"use client"

import { useEffect, useState } from "react"
import { Check, Copy, Loader2, Mail, Send, X } from "lucide-react"
import { fetchInvite } from "@/lib/generate-invite"

interface InviteModalProps {
  clientId: string | null
  propertyId: string | null
  clientName: string | null
  propertyName: string | null
  open: boolean
  onClose: () => void
}

export function InviteModal({
  clientId,
  propertyId,
  clientName,
  propertyName,
  open,
  onClose,
}: InviteModalProps) {
  const [draft, setDraft] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!open || !clientId || !propertyId) return

    setDraft(null)
    setLoading(true)
    setError(null)
    setCopied(false)

    fetchInvite(clientId, propertyId)
      .then((text) => {
        setDraft(text)
        setLoading(false)
      })
      .catch((err: Error) => {
        setError(err.message ?? "Failed to generate invite")
        setLoading(false)
      })
  }, [open, clientId, propertyId])

  // Close on Escape
  useEffect(() => {
    if (!open) return
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose()
    }
    document.addEventListener("keydown", onKey)
    return () => document.removeEventListener("keydown", onKey)
  }, [open, onClose])

  // Lock scroll
  useEffect(() => {
    if (open) {
      document.body.style.overflow = "hidden"
    } else {
      document.body.style.overflow = ""
    }
    return () => {
      document.body.style.overflow = ""
    }
  }, [open])

  function handleCopy() {
    if (!draft) return
    navigator.clipboard.writeText(draft)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  if (!open || !clientId || !propertyId) return null

  return (
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center p-4 sm:p-6 lg:p-10"
      style={{ backgroundColor: "rgba(0,0,0,0.80)" }}
      onClick={onClose}
    >
      <div
        className="relative flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden border-4 border-black bg-white shadow-[14px_14px_0px_0px_rgba(0,0,0,1)]"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="Generated Client Invite"
      >
        {/* Header */}
        <div className="flex shrink-0 items-start justify-between gap-4 border-b-4 border-black bg-black p-5 sm:p-6">
          <div className="flex items-center gap-3">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center border-4 border-primary bg-primary text-black">
              <Mail className="h-6 w-6" strokeWidth={2.5} />
            </div>
            <div>
              <div className="text-[10px] font-black uppercase tracking-widest text-white/50">
                Personalised Outreach
              </div>
              <div className="text-lg font-black leading-tight text-white sm:text-xl">
                Generated Invite for {clientName ?? "Client"}
              </div>
              {propertyName && (
                <div className="mt-1 font-mono text-[11px] text-white/60">
                  Target: {propertyName}
                </div>
              )}
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="shrink-0 border-2 border-white/40 p-2 text-white transition-colors hover:border-white hover:bg-white hover:text-black"
            aria-label="Close"
          >
            <X className="h-5 w-5" strokeWidth={2.5} />
          </button>
        </div>

        {/* Body */}
        <div className="p-5 sm:p-6">
          {loading && (
            <div className="flex flex-col items-center justify-center gap-4 py-12">
              <Loader2 className="h-8 w-8 animate-spin text-black" strokeWidth={2.5} />
              <p className="font-mono text-xs font-black uppercase tracking-widest text-muted-foreground">
                Drafting personalized invite via AI logic engine…
              </p>
            </div>
          )}

          {!loading && error && (
            <div className="border-4 border-black bg-white p-5 shadow-[4px_4px_0px_0px_rgba(0,0,0,1)]">
              <p className="text-xs font-black uppercase tracking-wider text-black">Generation Error</p>
              <p className="mt-2 text-sm font-bold text-muted-foreground">{error}</p>
            </div>
          )}

          {!loading && !error && draft && (
            <div className="flex flex-col gap-4">
              <div className="border-4 border-black bg-primary/20 p-5 shadow-[6px_6px_0px_0px_rgba(0,0,0,1)]">
                <p className="font-sans text-sm font-bold leading-relaxed whitespace-pre-wrap text-black">
                  {draft}
                </p>
              </div>
              <p className="text-[10px] font-black uppercase tracking-wider text-muted-foreground">
                Review and copy draft into your CRM or WhatsApp communication channel. No auto-send.
              </p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="shrink-0 border-t-4 border-black p-5 sm:p-6 bg-card">
          <div className="flex flex-col gap-3 sm:flex-row sm:justify-end">
            {!loading && !error && draft && (
              <button
                type="button"
                onClick={handleCopy}
                className="flex items-center justify-center gap-2 border-4 border-black bg-primary px-6 py-3 text-xs font-black uppercase tracking-wider text-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] transition-all hover:translate-x-0.5 hover:translate-y-0.5 hover:shadow-none"
              >
                {copied ? (
                  <>
                    <Check className="h-4 w-4 text-black" strokeWidth={2.5} />
                    Copied to Clipboard!
                  </>
                ) : (
                  <>
                    <Copy className="h-4 w-4 text-black" strokeWidth={2.5} />
                    Copy Invite Text
                  </>
                )}
              </button>
            )}
            <button
              type="button"
              onClick={onClose}
              className="flex items-center justify-center gap-2 border-4 border-black bg-black px-6 py-3 text-xs font-black uppercase tracking-wider text-white transition-colors hover:bg-white hover:text-black"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
