"use client"

import { useEffect, useMemo, useState } from "react"
import {
  Calendar,
  Check,
  Clock,
  Copy,
  Edit3,
  Loader2,
  Mail,
  RotateCcw,
  Send,
  Sparkles,
  X,
} from "lucide-react"
import { fetchInviteDetails, PitchSlot } from "@/lib/generate-invite"
import {
  assemblePitchDraft,
  formatSlotLabel,
  slotToIso,
  splitPitchDraft,
} from "@/lib/slot-utils"
import { WhatsAppSendModal } from "@/components/pipeline/whatsapp-send-modal"

interface InviteModalProps {
  clientId: string | null
  propertyId: string | null
  clientName: string | null
  propertyName: string | null
  whatsappNumber?: string | null
  agentId?: string | null
  open: boolean
  onClose: () => void
  onMarkSent?: () => void
}

const PRESET_TIMES = [
  { label: "10:00 AM", value: "10:00" },
  { label: "11:30 AM", value: "11:30" },
  { label: "2:00 PM", value: "14:00" },
  { label: "3:30 PM", value: "15:30" },
]

export function InviteModal({
  clientId,
  propertyId,
  clientName,
  propertyName,
  whatsappNumber,
  agentId,
  open,
  onClose,
  onMarkSent,
}: InviteModalProps) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pitchBody, setPitchBody] = useState<string>("")
  const [cta, setCta] = useState<string>("Reply 1, 2 or 3 to book, or tell me a time that suits you.")
  const [slots, setSlots] = useState<PitchSlot[]>([])
  const [draft, setDraft] = useState<string | null>(null)
  const [originalDraft, setOriginalDraft] = useState<string | null>(null)

  const [copied, setCopied] = useState(false)
  const [sent, setSent] = useState(false)
  const [markingSent, setMarkingSent] = useState(false)
  const [whatsappModalOpen, setWhatsappModalOpen] = useState(false)

  const todayStr = useMemo(() => {
    return new Date().toISOString().split("T")[0]
  }, [])

  useEffect(() => {
    if (!open || !clientId || !propertyId) return

    setDraft(null)
    setOriginalDraft(null)
    setPitchBody("")
    setSlots([])
    setLoading(true)
    setError(null)
    setCopied(false)
    setSent(false)
    setMarkingSent(false)

    fetchInviteDetails(clientId, propertyId, "R. Delgado", agentId)
      .then((details) => {
        const { body, cta: extractedCta } = splitPitchDraft(details.draft)
        setPitchBody(body)
        setCta(extractedCta)
        setSlots(details.slots)
        setDraft(details.draft)
        setOriginalDraft(details.draft)
        setLoading(false)
      })
      .catch((err: Error) => {
        setError(err.message ?? "Failed to generate invite")
        setLoading(false)
      })
  }, [open, clientId, propertyId, agentId])

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

  // Handle date change for a slot — always recomputes slot_iso from structured data
  const handleSlotDateChange = (slotIndex: number, newDate: string) => {
    setSlots((prev) => {
      const nextSlots = prev.map((s) => {
        if (s.index !== slotIndex) return s
        const label = formatSlotLabel(newDate, s.time)
        return { ...s, date: newDate, label, slot_iso: slotToIso(newDate, s.time) }
      })
      const newDraft = assemblePitchDraft(pitchBody, nextSlots, cta)
      setDraft(newDraft)
      return nextSlots
    })
  }

  // Handle time change for a slot — always recomputes slot_iso from structured data
  const handleSlotTimeChange = (slotIndex: number, newTime: string) => {
    setSlots((prev) => {
      const nextSlots = prev.map((s) => {
        if (s.index !== slotIndex) return s
        const label = formatSlotLabel(s.date, newTime)
        return { ...s, time: newTime, label, slot_iso: slotToIso(s.date, newTime) }
      })
      const newDraft = assemblePitchDraft(pitchBody, nextSlots, cta)
      setDraft(newDraft)
      return nextSlots
    })
  }

  // Handle pitch body edit
  const handlePitchBodyChange = (newBody: string) => {
    setPitchBody(newBody)
    const newDraft = assemblePitchDraft(newBody, slots, cta)
    setDraft(newDraft)
  }

  // Reset to original generated draft
  const handleResetToOriginal = () => {
    if (!originalDraft) return
    const { body, cta: extractedCta } = splitPitchDraft(originalDraft)
    setPitchBody(body)
    setCta(extractedCta)
    setDraft(originalDraft)
    if (clientId && propertyId) {
      fetchInviteDetails(clientId, propertyId, "R. Delgado", agentId).then((d) => {
        setSlots(d.slots)
      })
    }
  }

  function handleCopy() {
    if (!draft) return
    navigator.clipboard.writeText(draft)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  async function handleMarkSent() {
    if (!clientId || !propertyId || markingSent) return
    setMarkingSent(true)
    try {
      const res = await fetch("/api/invite/mark_sent", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ client_id: clientId, property_id: propertyId }),
      })
      if (res.ok) {
        setSent(true)
        onMarkSent?.()
      }
    } catch {
      // silent
    } finally {
      setMarkingSent(false)
    }
  }

  const wordCount = useMemo(() => {
    if (!draft) return 0
    return draft.trim().split(/\s+/).filter(Boolean).length
  }, [draft])

  if (!open || !clientId || !propertyId) return null

  return (
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center p-3 sm:p-6 lg:p-8"
      style={{ backgroundColor: "rgba(0,0,0,0.80)" }}
      onClick={onClose}
    >
      <div
        className="relative flex max-h-[92vh] w-full max-w-4xl flex-col overflow-hidden border border-neutral-200 bg-white shadow-[0px_8px_32px_rgba(0,0,0,0.14)]"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="Generated Outreach Pitch"
      >
        {/* Header */}
        <div className="flex shrink-0 items-start justify-between gap-4 border-b border-neutral-200 bg-black p-4 sm:p-5">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 shrink-0 items-center justify-center border-2 border-primary bg-primary text-black">
              <Mail className="h-5 w-5" strokeWidth={2.5} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-black uppercase tracking-widest text-primary">
                  Personalised Outreach
                </span>
                <span className="bg-white/10 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider text-white/70">
                  Auto-Scheduling Ready
                </span>
              </div>
              <div className="text-base font-black leading-tight text-white sm:text-lg">
                Generated Outreach Pitch for {clientName ?? "Company"}
              </div>
              {propertyName && (
                <div className="mt-0.5 font-mono text-[11px] text-white/60">
                  Target Robotics Unit: <strong className="text-white/90">{propertyName}</strong>
                </div>
              )}
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="shrink-0 border border-white/40 p-1.5 text-white transition-colors hover:border-white hover:bg-white hover:text-black"
            aria-label="Close"
          >
            <X className="h-5 w-5" strokeWidth={2.5} />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-6">
          {loading && (
            <div className="flex flex-col items-center justify-center gap-4 py-16">
              <Loader2 className="h-8 w-8 animate-spin text-black" strokeWidth={2.5} />
              <p className="font-mono text-xs font-black uppercase tracking-widest text-muted-foreground">
                Drafting personalized outreach pitch &amp; checking rep availability…
              </p>
            </div>
          )}

          {!loading && error && (
            <div className="border border-neutral-200 bg-white p-5 shadow-[0px_2px_8px_rgba(0,0,0,0.08)]">
              <p className="text-xs font-black uppercase tracking-wider text-black">Generation Error</p>
              <p className="mt-2 text-sm font-bold text-muted-foreground">{error}</p>
            </div>
          )}

          {!loading && !error && draft && (
            <div className="flex flex-col gap-5">
              {/* SCHEDULE EDITOR: 3 Interactive Editable Slots */}
              <div className="border border-neutral-200 bg-neutral-50/80 p-4 shadow-[0px_2px_8px_rgba(0,0,0,0.04)]">
                <div className="mb-3 flex flex-wrap items-center justify-between gap-2 border-b border-neutral-200 pb-2.5">
                  <div className="flex items-center gap-2">
                    <div className="flex h-6 w-6 items-center justify-center bg-black text-white">
                      <Calendar className="h-3.5 w-3.5" />
                    </div>
                    <div>
                      <h4 className="text-xs font-black uppercase tracking-wider text-black">
                        Proposed Demo Schedule (Editable)
                      </h4>
                      <p className="text-[11px] font-medium text-muted-foreground">
                        Prospects can reply 1, 2, or 3 to instantly book. Edit date and time below to customize availability.
                      </p>
                    </div>
                  </div>
                  <span className="flex items-center gap-1.5 rounded-full border border-emerald-600/30 bg-emerald-50 px-2.5 py-0.5 text-[10px] font-bold text-emerald-700">
                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
                    Auto-Books on Reply
                  </span>
                </div>

                <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                  {slots.map((slot) => {
                    return (
                      <div
                        key={slot.index}
                        className="flex flex-col justify-between border border-neutral-200 bg-white p-3.5 shadow-sm transition-all hover:border-black/40"
                      >
                        <div>
                          {/* Slot Header */}
                          <div className="mb-2 flex items-center justify-between">
                            <span className="border border-black bg-black px-2 py-0.5 text-[10px] font-black uppercase tracking-wider text-white">
                              Slot {slot.index}
                            </span>
                            <span className="font-mono text-[11px] font-bold text-neutral-800">
                              {slot.label}
                            </span>
                          </div>

                          {/* Date Field */}
                          <div className="mb-2.5">
                            <label className="mb-1 flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider text-neutral-500">
                              <Calendar className="h-3 w-3 text-neutral-400" />
                              Date
                            </label>
                            <input
                              type="date"
                              value={slot.date}
                              min={todayStr}
                              onChange={(e) => handleSlotDateChange(slot.index, e.target.value)}
                              className="w-full border border-neutral-300 bg-white px-2 py-1.5 text-xs font-semibold text-neutral-900 focus:border-black focus:outline-none"
                            />
                          </div>

                          {/* Time Field */}
                          <div className="mb-2">
                            <label className="mb-1 flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider text-neutral-500">
                              <Clock className="h-3 w-3 text-neutral-400" />
                              Time
                            </label>
                            <input
                              type="time"
                              value={slot.time}
                              onChange={(e) => handleSlotTimeChange(slot.index, e.target.value)}
                              className="w-full border border-neutral-300 bg-white px-2 py-1.5 text-xs font-semibold text-neutral-900 focus:border-black focus:outline-none"
                            />
                          </div>

                          {/* Quick Preset Buttons */}
                          <div className="mt-1 flex flex-wrap gap-1">
                            {PRESET_TIMES.map((preset) => {
                              const isSelected = slot.time === preset.value
                              return (
                                <button
                                  key={preset.value}
                                  type="button"
                                  onClick={() => handleSlotTimeChange(slot.index, preset.value)}
                                  className={`px-1.5 py-0.5 text-[10px] font-bold transition-colors ${
                                    isSelected
                                      ? "bg-black text-white"
                                      : "border border-neutral-200 bg-neutral-100 text-neutral-700 hover:border-neutral-400"
                                  }`}
                                >
                                  {preset.label}
                                </button>
                              )
                            })}
                          </div>
                        </div>

                        <div className="mt-2.5 border-t border-neutral-100 pt-1.5 text-[10px] font-medium text-neutral-400">
                          Reply &ldquo;{slot.index}&rdquo; books this slot
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>

              {/* EDITABLE PITCH BODY */}
              <div className="border border-neutral-200 bg-white p-4 shadow-[0px_2px_8px_rgba(0,0,0,0.04)]">
                <div className="mb-2 flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <Edit3 className="h-3.5 w-3.5 text-black" />
                    <label className="text-xs font-black uppercase tracking-wider text-black">
                      Pitch Message Body (Editable)
                    </label>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="font-mono text-[11px] text-neutral-500">
                      {wordCount} words
                    </span>
                    {originalDraft && (
                      <button
                        type="button"
                        onClick={handleResetToOriginal}
                        className="flex items-center gap-1 text-[11px] font-bold text-neutral-500 transition-colors hover:text-black"
                        title="Reset to initial AI draft"
                      >
                        <RotateCcw className="h-3 w-3" />
                        Reset
                      </button>
                    )}
                  </div>
                </div>
                <textarea
                  value={pitchBody}
                  onChange={(e) => handlePitchBodyChange(e.target.value)}
                  rows={4}
                  className="w-full resize-y border border-neutral-300 bg-neutral-50/50 p-3 font-sans text-xs font-medium leading-relaxed text-black focus:border-black focus:bg-white focus:outline-none"
                  placeholder="Enter pitch message body..."
                />
              </div>

              {/* LIVE WHATSAPP MESSAGE PREVIEW */}
              <div className="border border-neutral-200 bg-primary/10 p-4 shadow-[0px_2px_8px_rgba(0,0,0,0.04)]">
                <div className="mb-2 flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <Sparkles className="h-3.5 w-3.5 text-black" />
                    <span className="text-xs font-black uppercase tracking-wider text-black">
                      Live WhatsApp Outreach Preview
                    </span>
                  </div>
                  <span className="font-mono text-[10px] font-bold uppercase tracking-wider text-neutral-600">
                    Exact Message Dispatched
                  </span>
                </div>
                <div className="border border-neutral-300 bg-white p-4 font-sans text-xs font-medium leading-relaxed whitespace-pre-wrap text-black">
                  {draft}
                </div>
                <p className="mt-2 text-[10px] font-bold uppercase tracking-wider text-neutral-500">
                  Review and dispatch via WhatsApp, or copy directly into your sales communication channel.
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="shrink-0 border-t border-neutral-200 bg-neutral-50 p-4 sm:p-5">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="text-[11px] font-medium text-neutral-500">
              {slots.length > 0 && (
                <span>
                  3 slots configured: <strong>{slots.map((s) => s.label).join(" · ")}</strong>
                </span>
              )}
            </div>

            <div className="flex flex-wrap items-center justify-end gap-2.5">
              {!loading && !error && draft && (
                <>
                  {!sent ? (
                    <button
                      type="button"
                      onClick={handleMarkSent}
                      disabled={markingSent}
                      className="flex items-center justify-center gap-2 border border-neutral-200 bg-neutral-200 px-4 py-2.5 text-xs font-black uppercase tracking-wider text-black transition-all hover:bg-neutral-300 disabled:opacity-60"
                    >
                      {markingSent ? (
                        <>
                          <Loader2 className="h-3.5 w-3.5 animate-spin text-black" strokeWidth={2.5} />
                          Updating Stage…
                        </>
                      ) : (
                        <>
                          <Send className="h-3.5 w-3.5 text-black" strokeWidth={2.5} />
                          Mark Sent
                        </>
                      )}
                    </button>
                  ) : (
                    <div className="flex items-center gap-1.5 border border-[#f3e292] bg-[#FFF8DC] px-3 py-2 text-xs font-black uppercase tracking-wider text-[#8a6d00]">
                      <Check className="h-3.5 w-3.5 text-[#8a6d00]" strokeWidth={2.5} />
                      ✓ Contacted
                    </div>
                  )}

                  <button
                    type="button"
                    onClick={handleCopy}
                    className="flex items-center justify-center gap-2 border border-neutral-300 bg-white px-4 py-2.5 text-xs font-black uppercase tracking-wider text-black shadow-sm transition-all hover:bg-neutral-100"
                  >
                    {copied ? (
                      <>
                        <Check className="h-3.5 w-3.5 text-emerald-600" strokeWidth={2.5} />
                        Copied!
                      </>
                    ) : (
                      <>
                        <Copy className="h-3.5 w-3.5 text-neutral-600" strokeWidth={2.5} />
                        Copy Pitch
                      </>
                    )}
                  </button>

                  <button
                    type="button"
                    onClick={() => setWhatsappModalOpen(true)}
                    className="flex items-center justify-center gap-2 border border-emerald-600 bg-emerald-600 px-5 py-2.5 text-xs font-black uppercase tracking-wider text-white shadow-sm transition-all hover:bg-emerald-700"
                  >
                    <Send className="h-3.5 w-3.5 text-white" strokeWidth={2.5} />
                    Send via WhatsApp
                  </button>
                </>
              )}

              <button
                type="button"
                onClick={onClose}
                className="flex items-center justify-center border border-neutral-300 bg-white px-4 py-2.5 text-xs font-black uppercase tracking-wider text-black transition-colors hover:bg-neutral-100"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      </div>

      <WhatsAppSendModal
        isOpen={whatsappModalOpen}
        onClose={() => setWhatsappModalOpen(false)}
        clientId={clientId}
        propertyId={propertyId}
        clientName={clientName ?? "Company"}
        whatsappNumber={whatsappNumber ?? null}
        agentId={agentId ?? null}
        draftText={draft ?? ""}
        initialSlots={slots}
        onSentSuccess={() => {
          setSent(true)
          onMarkSent?.()
        }}
      />
    </div>
  )
}

