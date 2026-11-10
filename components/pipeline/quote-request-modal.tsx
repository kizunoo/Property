"use client"

import React, { useEffect, useState } from "react"
import { X, AlertCircle, CheckCircle, Loader2 } from "lucide-react"
import {
  createQuoteRequest,
  approveQuoteRequest,
  cancelQuoteRequest,
} from "@/lib/fetch-quotes"
import type { QuoteRequest, RequestKind } from "@/lib/quotes"

export interface QuoteRequestModalProps {
  open: boolean
  onClose: () => void
  clientId: string
  propertyId: string
  marketPriceMyr: number
  kind: RequestKind
  companyName?: string
  robotName?: string
  onApproved?: (req: QuoteRequest) => void
  onCancelled?: () => void
}

export function QuoteRequestModal({
  open,
  onClose,
  clientId,
  propertyId,
  marketPriceMyr,
  kind,
  companyName,
  robotName,
  onApproved,
  onCancelled,
}: QuoteRequestModalProps) {
  const [loading, setLoading] = useState(false)
  const [approving, setApproving] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const [request, setRequest] = useState<QuoteRequest | null>(null)
  const [draftSubject, setDraftSubject] = useState("")
  const [draftBody, setDraftBody] = useState("")
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [approvedMessage, setApprovedMessage] = useState(false)

  useEffect(() => {
    if (!open || !clientId || !propertyId) return
    let active = true
    setLoading(true)
    setErrorMessage(null)
    setApprovedMessage(false)

    createQuoteRequest(clientId, propertyId, marketPriceMyr, kind).then((res) => {
      if (!active) return
      setLoading(false)
      if (!res.ok) {
        if (res.error.includes("422") || res.error.toLowerCase().includes("indicative") || res.error.toLowerCase().includes("bounds")) {
          setErrorMessage("No market price for this robot yet")
        } else {
          setErrorMessage(res.error || "No market price for this robot yet")
        }
        return
      }
      setRequest(res.data)
      setDraftSubject(res.data.draftSubject || "")
      setDraftBody(res.data.draftBody || "")
    })

    return () => {
      active = false
    }
  }, [open, clientId, propertyId, marketPriceMyr, kind])

  if (!open) return null

  const handleApprove = async () => {
    if (!request) return
    setApproving(true)
    const res = await approveQuoteRequest(request.id, draftBody)
    setApproving(false)
    if (!res.ok) {
      setErrorMessage(res.error)
      return
    }
    setApprovedMessage(true)
    if (onApproved) onApproved(res.data)
  }

  const handleCancel = async () => {
    if (request && !approvedMessage && request.status === "draft") {
      setCancelling(true)
      await cancelQuoteRequest(request.id).catch(() => ({}))
      setCancelling(false)
    }
    if (onCancelled) onCancelled()
    onClose()
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
      <div className="relative w-full max-w-2xl rounded-xl border border-neutral-700 bg-neutral-900 p-6 text-white shadow-2xl">
        <button
          onClick={handleCancel}
          disabled={cancelling}
          className="absolute right-4 top-4 text-neutral-400 hover:text-white disabled:opacity-50"
        >
          <X className="h-5 w-5" />
        </button>

        <div className="mb-4">
          <h2 className="text-lg font-bold">
            {kind === "requote" ? "Request Requote (Simulated)" : "Request Supplier Quote (Simulated)"}
          </h2>
          <p className="text-xs text-neutral-400">
            {companyName ? `For ${companyName}` : "Company"} · {robotName ? robotName : "Robot"}
          </p>
        </div>

        {/* Permanent simulation notice */}
        <div className="mb-4 rounded-md border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-300">
          <strong>Notice:</strong> Simulated. Nothing is sent to any manufacturer.
        </div>

        {loading ? (
          <div className="flex h-48 items-center justify-center">
            <Loader2 className="h-6 w-6 animate-spin text-neutral-400" />
            <span className="ml-2 text-sm text-neutral-400">Drafting quote request…</span>
          </div>
        ) : errorMessage ? (
          <div className="my-6 rounded-md border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-300 flex items-start gap-3">
            <AlertCircle className="h-5 w-5 shrink-0 text-red-400 mt-0.5" />
            <div>
              <div className="font-semibold">Unable to request quote</div>
              <div className="mt-1 text-xs text-red-300/80">{errorMessage}</div>
            </div>
          </div>
        ) : approvedMessage ? (
          <div className="my-6 rounded-md border border-emerald-500/30 bg-emerald-500/10 p-5 text-emerald-200">
            <div className="flex items-center gap-2 font-bold text-base text-emerald-300">
              <CheckCircle className="h-5 w-5 text-emerald-400" />
              Supplier quote received (simulated)
            </div>
            <p className="mt-2 text-xs text-emerald-200/90 leading-relaxed">
              The simulated supplier has replied immediately. The quote is now active and locked in.
            </p>
            <div className="mt-4 flex justify-end">
              <button
                onClick={onClose}
                className="rounded-md bg-neutral-800 px-4 py-2 text-xs font-semibold text-white hover:bg-neutral-700"
              >
                Close
              </button>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-neutral-400 mb-1">
                Subject
              </label>
              <input
                type="text"
                value={draftSubject}
                readOnly
                className="w-full rounded-md border border-neutral-700 bg-neutral-800 px-3 py-2 text-xs font-mono text-neutral-200 focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-neutral-400 mb-1">
                Draft Body (editable)
              </label>
              <textarea
                value={draftBody}
                onChange={(e) => setDraftBody(e.target.value)}
                rows={10}
                className="w-full rounded-md border border-neutral-700 bg-neutral-800 px-3 py-2 text-xs font-mono text-neutral-200 focus:border-[#FFD600] focus:outline-none"
              />
            </div>

            <div className="flex items-center justify-between pt-2">
              <button
                type="button"
                onClick={handleCancel}
                disabled={cancelling}
                className="rounded-md border border-neutral-700 bg-transparent px-4 py-2 text-xs font-semibold text-neutral-300 hover:bg-neutral-800 disabled:opacity-50"
              >
                {cancelling ? "Cancelling…" : "Cancel request"}
              </button>

              <button
                type="button"
                onClick={handleApprove}
                disabled={approving || !request}
                className="rounded-md bg-[#FFD600] px-4 py-2 text-xs font-bold text-black hover:bg-[#e6c200] disabled:opacity-50"
              >
                {approving ? "Sending…" : "Approve and send (simulated)"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

