"use client"

import React, { useState, useRef, useEffect, useCallback } from "react"
import {
  X,
  Send,
  Minimize2,
  Maximize2,
  GripHorizontal,
  Phone,
  Sparkles,
  CheckCheck,
  RefreshCw,
  MessageSquare,
} from "lucide-react"
import type { DeduplicatedClient } from "@/lib/pipeline-data"
import { fetchInvite } from "@/lib/generate-invite"
import { WhatsAppRepPanel } from "./whatsapp-rep-panel"

interface Message {
  id: string
  sender: "user" | "agent" | "client" | "system"
  text: string
  timestamp: string
  status?: "sending" | "delivered" | "received" | "failed"
  messageId?: string
  to?: string
  client_name?: string
}

interface WhatsAppFloatingPanelProps {
  clients?: DeduplicatedClient[]
  agentId?: string | null
}

const DEFAULT_PHONE = "+60109722730"
const MIN_WIDTH = 320
const MIN_HEIGHT = 420
const DEFAULT_WIDTH = 400
const DEFAULT_HEIGHT = 560

export function WhatsAppFloatingPanel({ clients = [], agentId }: WhatsAppFloatingPanelProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [isMinimized, setIsMinimized] = useState(false)
  const [isRepPanelOpen, setIsRepPanelOpen] = useState(false)

  // Position & size
  const [position, setPosition] = useState<{ x: number; y: number } | null>(null)
  const [size, setSize] = useState({ width: DEFAULT_WIDTH, height: DEFAULT_HEIGHT })

  // Drag state
  const isDraggingRef = useRef(false)
  const dragStartRef = useRef({ mouseX: 0, mouseY: 0, startX: 0, startY: 0 })

  // Resize state
  const isResizingRef = useRef(false)
  const resizeEdgeRef = useRef<string>("")
  const resizeStartRef = useRef({ mouseX: 0, mouseY: 0, startW: 0, startH: 0, startX: 0, startY: 0 })

  const panelRef = useRef<HTMLDivElement>(null)

  // Client / recipient state
  const [recipientNumber, setRecipientNumber] = useState(DEFAULT_PHONE)
  const [selectedClientId, setSelectedClientId] = useState<string | null>(null)
  const [selectedClientName, setSelectedClientName] = useState("Direct Test Contact")
  const [selectedPropertyId, setSelectedPropertyId] = useState<string | null>(null)
  const [selectedPropertyName, setSelectedPropertyName] = useState<string | null>(null)

  const [clientPitchDraft, setClientPitchDraft] = useState<string | null>(null)
  const [pitchLoading, setPitchLoading] = useState(false)
  const [inputMessage, setInputMessage] = useState("")
  const [isSending, setIsSending] = useState(false)
  const [isSimulating, setIsSimulating] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  // Message history — keyed by id to deduplicate perfectly
  const [messages, setMessages] = useState<Message[]>([])
  const messageMapRef = useRef<Map<string, Message>>(new Map())
  const lastFetchedCountRef = useRef(0)
  const pollingRef = useRef<NodeJS.Timeout | null>(null)

  const chatScrollRef = useRef<HTMLDivElement>(null)

  // Initialize position bottom-right on mount and adjust on window resize
  useEffect(() => {
    if (typeof window !== "undefined") {
      setPosition({
        x: Math.max(16, window.innerWidth - DEFAULT_WIDTH - 24),
        y: Math.max(20, window.innerHeight - DEFAULT_HEIGHT - 92),
      })
    }

    const handleWindowResize = () => {
      setPosition((prev) => {
        if (!prev) return prev
        const maxX = Math.max(16, window.innerWidth - size.width - 24)
        const maxY = Math.max(20, window.innerHeight - (isMinimized ? 52 : size.height) - 24)
        return {
          x: Math.max(16, Math.min(prev.x, maxX)),
          y: Math.max(20, Math.min(prev.y, maxY)),
        }
      })
    }

    window.addEventListener("resize", handleWindowResize)
    return () => window.removeEventListener("resize", handleWindowResize)
  }, [size.width, size.height, isMinimized])

  // Auto-scroll to latest message
  useEffect(() => {
    if (isOpen && !isMinimized && chatScrollRef.current) {
      chatScrollRef.current.scrollTop = chatScrollRef.current.scrollHeight
    }
  }, [messages, isOpen, isMinimized])

  // ─── Merge incoming messages with dedup ───────────────────────────────────
  const mergeMessages = useCallback((incoming: Message[]) => {
    let changed = false
    incoming.forEach((m) => {
      if (!messageMapRef.current.has(m.id)) {
        messageMapRef.current.set(m.id, m)
        changed = true
      }
    })
    if (changed) {
      const sorted = Array.from(messageMapRef.current.values()).sort(
        (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
      )
      lastFetchedCountRef.current = sorted.length
      setMessages(sorted)
    }
  }, [])

  // ─── Fetch history from backend ───────────────────────────────────────────
  const fetchMessageHistory = useCallback(
    async (cleanNum: string) => {
      try {
        const params = new URLSearchParams({ to_number: cleanNum })
        if (agentId) params.set("agent_id", agentId)
        const res = await fetch(`/api/whatsapp/messages?${params}`)
        if (!res.ok) return
        const data = await res.json()
        if (!data.messages || !Array.isArray(data.messages)) return

        const incoming: Message[] = data.messages.map((m: any) => ({
          id: m.id || `msg-${m.timestamp}-${Math.random()}`,
          sender:
            m.sender === "client"
              ? "client"
              : m.sender === "system"
              ? "system"
              : m.sender === "agent" || m.sender === "user"
              ? "user"
              : "user",
          text: m.text || "",
          timestamp: m.timestamp || new Date().toISOString(),
          status: m.status || (m.sender === "client" ? "received" : "delivered"),
          client_name: m.client_name,
        }))

        mergeMessages(incoming)
      } catch {
        // silent — don't break UI on network hiccup
      }
    },
    [mergeMessages, agentId]
  )

  // ─── Adaptive polling: 2s when open, stop when closed ────────────────────
  useEffect(() => {
    if (pollingRef.current) clearInterval(pollingRef.current)

    if (!isOpen) return

    const cleanNum = recipientNumber.replace(/\D/g, "")
    fetchMessageHistory(cleanNum) // immediate on open

    pollingRef.current = setInterval(() => {
      fetchMessageHistory(cleanNum)
    }, 2000)

    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current)
    }
  }, [isOpen, recipientNumber, fetchMessageHistory])

  // ─── Re-fetch when active agent switches ─────────────────────────────────
  useEffect(() => {
    if (!isOpen) return
    messageMapRef.current = new Map()
    setMessages([])
    lastFetchedCountRef.current = 0
    const cleanNum = recipientNumber.replace(/\D/g, "")
    if (cleanNum) fetchMessageHistory(cleanNum)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentId])

  // ─── Reset message map when switching contact ─────────────────────────────
  const resetForNumber = useCallback(
    (num: string) => {
      messageMapRef.current = new Map()
      setMessages([])
      lastFetchedCountRef.current = 0
      const cleanNum = num.replace(/\D/g, "")
      fetchMessageHistory(cleanNum)
    },
    [fetchMessageHistory]
  )

  // ─── Global pointer events for drag & resize ─────────────────────────────
  useEffect(() => {
    const onMove = (e: PointerEvent) => {
      if (isDraggingRef.current) {
        const dx = e.clientX - dragStartRef.current.mouseX
        const dy = e.clientY - dragStartRef.current.mouseY
        const newX = Math.max(0, Math.min(window.innerWidth - size.width, dragStartRef.current.startX + dx))
        const newY = Math.max(0, Math.min(window.innerHeight - (isMinimized ? 52 : size.height) - 10, dragStartRef.current.startY + dy))
        setPosition({ x: newX, y: newY })
      }

      if (isResizingRef.current) {
        const edge = resizeEdgeRef.current
        const { mouseX, mouseY, startW, startH, startX, startY } = resizeStartRef.current
        const dx = e.clientX - mouseX
        const dy = e.clientY - mouseY

        let newW = startW
        let newH = startH
        let newX = startX
        let newY = startY

        if (edge.includes("e")) newW = Math.max(MIN_WIDTH, startW + dx)
        if (edge.includes("w")) {
          newW = Math.max(MIN_WIDTH, startW - dx)
          newX = startX + (startW - newW)
        }
        if (edge.includes("s")) newH = Math.max(MIN_HEIGHT, startH + dy)
        if (edge.includes("n")) {
          newH = Math.max(MIN_HEIGHT, startH - dy)
          newY = startY + (startH - newH)
        }

        setSize({ width: newW, height: newH })
        setPosition({ x: newX, y: newY })
      }
    }

    const onUp = () => {
      isDraggingRef.current = false
      isResizingRef.current = false
      resizeEdgeRef.current = ""
      document.body.style.userSelect = ""
      document.body.style.cursor = ""
    }

    window.addEventListener("pointermove", onMove)
    window.addEventListener("pointerup", onUp)
    return () => {
      window.removeEventListener("pointermove", onMove)
      window.removeEventListener("pointerup", onUp)
    }
  }, [size.width, size.height, isMinimized])

  // ─── Drag header ──────────────────────────────────────────────────────────
  const handleDragStart = (e: React.PointerEvent) => {
    const target = e.target as HTMLElement
    if (target.closest("button") || target.closest("input") || target.closest("select")) return
    isDraggingRef.current = true
    dragStartRef.current = {
      mouseX: e.clientX,
      mouseY: e.clientY,
      startX: position?.x ?? 0,
      startY: position?.y ?? 0,
    }
    document.body.style.userSelect = "none"
    e.preventDefault()
  }

  // ─── Resize handle ────────────────────────────────────────────────────────
  const startResize = (e: React.PointerEvent, edge: string) => {
    e.stopPropagation()
    e.preventDefault()
    isResizingRef.current = true
    resizeEdgeRef.current = edge
    resizeStartRef.current = {
      mouseX: e.clientX,
      mouseY: e.clientY,
      startW: size.width,
      startH: size.height,
      startX: position?.x ?? 0,
      startY: position?.y ?? 0,
    }
    document.body.style.userSelect = "none"
    const cursors: Record<string, string> = {
      n: "n-resize", s: "s-resize", e: "e-resize", w: "w-resize",
      ne: "ne-resize", nw: "nw-resize", se: "se-resize", sw: "sw-resize",
    }
    document.body.style.cursor = cursors[edge] || "default"
  }

  // ─── Client selection ─────────────────────────────────────────────────────
  const handleSelectClient = async (client: DeduplicatedClient) => {
    const num = client.whatsappNumber || DEFAULT_PHONE
    setRecipientNumber(num)
    setSelectedClientId(client.clientId)
    setSelectedClientName(client.name)
    setSelectedPropertyId(client.bestMatch.propertyId)
    setSelectedPropertyName(client.bestMatch.property)
    setErrorMessage(null)
    resetForNumber(num)

    setPitchLoading(true)
    try {
      const draft = await fetchInvite(client.clientId, client.bestMatch.propertyId, "R. Delgado", agentId)
      setClientPitchDraft(draft)
      setInputMessage(draft)
    } catch {
      const fallback = `Hello ${client.name}, following up from PIPELINE.EV regarding ${client.bestMatch.property}. Would you like to schedule a demonstration?`
      setClientPitchDraft(fallback)
      setInputMessage(fallback)
    } finally {
      setPitchLoading(false)
    }
  }

  // ─── Send message ─────────────────────────────────────────────────────────
  const handleSendMessage = async (customText?: string, templateName?: string) => {
    const textToSend = (customText ?? inputMessage).trim()
    if ((!textToSend && !templateName) || isSending) return

    const cleanNumber = recipientNumber.replace(/\D/g, "")
    if (!cleanNumber) {
      setErrorMessage("Please enter a valid recipient phone number")
      return
    }

    setErrorMessage(null)
    const now = new Date()
    const msgId = `optimistic-${Date.now()}`
    const displayText = templateName
      ? `[Meta Template: ${templateName}] ${textToSend || "Initial contact greeting"}`
      : textToSend

    const optimistic: Message = {
      id: msgId,
      sender: "user",
      text: displayText,
      timestamp: now.toISOString(),
      status: "sending",
      to: cleanNumber,
    }

    messageMapRef.current.set(msgId, optimistic)
    setMessages(Array.from(messageMapRef.current.values()))
    if (!customText) setInputMessage("")
    setIsSending(true)

    try {
      const res = await fetch("/api/whatsapp/send_message", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          to_number: cleanNumber,
          message: textToSend || `Template ${templateName}`,
          client_id: selectedClientId,
          client_name: selectedClientName,
          template_name: templateName,
          agent_id: agentId ?? null,
        }),
      })

      const data = await res.json().catch(() => ({}))

      if (!res.ok) throw new Error(data.detail || data.error || "Message delivery failed")

      const waId = data.message?.id || data.whatsapp_response?.messages?.[0]?.id || msgId
      // Replace optimistic with confirmed server entry
      messageMapRef.current.delete(msgId)
      if (data.message) {
        messageMapRef.current.set(waId, {
          id: waId,
          sender: "user",
          text: data.message.text || displayText,
          timestamp: data.message.timestamp || now.toISOString(),
          status: data.message.status || "delivered",
        })
      }
      setMessages(Array.from(messageMapRef.current.values()))

      if (customText === clientPitchDraft) setClientPitchDraft(null)
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to send message")
      const updated = { ...optimistic, status: "failed" as const }
      messageMapRef.current.set(msgId, updated)
      setMessages(Array.from(messageMapRef.current.values()))
    } finally {
      setIsSending(false)
    }
  }

  // ─── Simulate incoming ────────────────────────────────────────────────────
  const handleSimulateIncoming = async (customMessage?: string) => {
    setIsSimulating(true)
    try {
      const cleanNum = recipientNumber.replace(/\D/g, "")
      const msgText = customMessage || "1"
      const res = await fetch("/api/whatsapp/simulate_incoming", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          from_number: cleanNum,
          client_id: selectedClientId,
          client_name: selectedClientName,
          message: msgText,
        }),
      })
      if (res.ok) {
        const data = await res.json()
        if (data.message) {
          const m = data.message
          const msg: Message = {
            id: m.id,
            sender: "client",
            text: m.text,
            timestamp: m.timestamp || new Date().toISOString(),
            status: "received",
            client_name: selectedClientName,
          }
          messageMapRef.current.set(m.id, msg)
          setMessages(Array.from(messageMapRef.current.values()))
        }
        // Immediate fetch to catch any auto-booked confirmation message from agent
        fetchMessageHistory(cleanNum)
      }
    } catch {
      // silent
    } finally {
      setIsSimulating(false)
    }
  }

  // ─── Format timestamp for display ────────────────────────────────────────
  const fmt = (ts: string) => {
    try {
      return new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    } catch {
      return ts
    }
  }

  const chatAreaHeight = isMinimized ? 0 : size.height - 168 // subtract header + controls + composer

  // ─── Resize handle nodes ──────────────────────────────────────────────────
  const ResizeHandle = ({ edge, style }: { edge: string; style: React.CSSProperties }) => (
    <div
      onPointerDown={(e) => startResize(e, edge)}
      style={{
        position: "absolute",
        zIndex: 10,
        ...style,
      }}
    />
  )

  return (
    <>
      {/* ── Floating WhatsApp FAB ────────────────────────────────────────── */}
      <button
        type="button"
        id="whatsapp-floating-trigger"
        onClick={() => {
          setIsOpen((prev) => !prev)
          if (isMinimized) setIsMinimized(false)
        }}
        aria-label="Toggle WhatsApp Outreach Panel"
        style={{
          position: "fixed",
          bottom: "24px",
          right: "24px",
          width: "58px",
          height: "58px",
          borderRadius: "50%",
          background: "linear-gradient(135deg, #25D366, #128C7E)",
          border: "none",
          boxShadow: "0 8px 28px rgba(37, 211, 102, 0.45)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          cursor: "pointer",
          zIndex: 9999,
          transition: "transform 0.18s cubic-bezier(0.34,1.56,0.64,1), box-shadow 0.18s ease",
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.transform = "scale(1.1)"
          e.currentTarget.style.boxShadow = "0 12px 32px rgba(37,211,102,0.6)"
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.transform = "scale(1)"
          e.currentTarget.style.boxShadow = "0 8px 28px rgba(37,211,102,0.45)"
        }}
      >
        {/* Unread pulse dot */}
        <span
          style={{
            position: "absolute",
            top: "3px",
            right: "3px",
            width: "13px",
            height: "13px",
            borderRadius: "50%",
            background: "#10b981",
            border: "2.5px solid #fff",
          }}
        />
        <svg width="30" height="30" viewBox="0 0 24 24" fill="#fff">
          <path d="M12.04 2C6.58 2 2.13 6.45 2.13 11.91c0 1.75.46 3.45 1.32 4.95L2.05 22l5.25-1.38a9.9 9.9 0 004.74 1.21h.005c5.46 0 9.91-4.45 9.91-9.91 0-2.65-1.03-5.14-2.9-7.01A9.86 9.86 0 0012.04 2zm5.83 14.1c-.24.68-1.4 1.3-1.93 1.38-.5.08-1.12.11-1.8-.11-.42-.13-.95-.31-1.64-.6-2.88-1.24-4.76-4.14-4.9-4.33-.14-.19-1.17-1.56-1.17-2.98 0-1.41.74-2.11 1-2.4.26-.29.57-.36.76-.36h.55c.18 0 .42-.07.65.5.24.58.82 2 .89 2.15.07.15.12.32.02.52-.1.19-.15.31-.3.48-.15.17-.31.38-.44.51-.15.15-.3.31-.13.6.17.29.76 1.25 1.63 2.03 1.12 1 2.06 1.31 2.35 1.46.29.15.46.13.63-.08.17-.2.72-.84.91-1.13.19-.29.39-.24.65-.14.27.1 1.69.8 1.98.94.29.15.48.22.55.34.07.13.07.72-.17 1.4z" />
        </svg>
      </button>

      {/* ── Floating Panel ───────────────────────────────────────────────── */}
      {isOpen && (
        <div
          ref={panelRef}
          style={{
            position: "fixed",
            left: position ? `${position.x}px` : "auto",
            top: position ? `${position.y}px` : "auto",
            right: position ? "auto" : "24px",
            bottom: position ? "auto" : "92px",
            width: `${size.width}px`,
            height: isMinimized ? "52px" : `${size.height}px`,
            minWidth: `${MIN_WIDTH}px`,
            maxWidth: "calc(100vw - 32px)",
            minHeight: isMinimized ? "52px" : `${MIN_HEIGHT}px`,
            maxHeight: isMinimized ? "52px" : "calc(100vh - 40px)",
            borderRadius: "14px",
            background: "#fff",
            boxShadow:
              "0 24px 60px -12px rgba(0,0,0,0.22), 0 0 0 1px rgba(0,0,0,0.06)",
            zIndex: 9998,
            overflow: "hidden",
            display: "flex",
            flexDirection: "column",
            fontFamily:
              "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif",
          }}
        >
          {/* ── Corner & Edge Resize Handles ─────────────────────────────── */}
          {!isMinimized && (
            <>
              {/* Corners */}
              <ResizeHandle edge="nw" style={{ top: 0, left: 0, width: 12, height: 12, cursor: "nw-resize" }} />
              <ResizeHandle edge="ne" style={{ top: 0, right: 0, width: 12, height: 12, cursor: "ne-resize" }} />
              <ResizeHandle edge="sw" style={{ bottom: 0, left: 0, width: 12, height: 12, cursor: "sw-resize" }} />
              <ResizeHandle edge="se" style={{ bottom: 0, right: 0, width: 12, height: 12, cursor: "se-resize" }} />
              {/* Edges */}
              <ResizeHandle edge="n" style={{ top: 0, left: 12, right: 12, height: 5, cursor: "n-resize" }} />
              <ResizeHandle edge="s" style={{ bottom: 0, left: 12, right: 12, height: 5, cursor: "s-resize" }} />
              <ResizeHandle edge="w" style={{ top: 12, bottom: 12, left: 0, width: 5, cursor: "w-resize" }} />
              <ResizeHandle edge="e" style={{ top: 12, bottom: 12, right: 0, width: 5, cursor: "e-resize" }} />
            </>
          )}

          {/* ── Header ───────────────────────────────────────────────────── */}
          <div
            onPointerDown={handleDragStart}
            style={{
              background: "linear-gradient(135deg, #075E54 0%, #128C7E 60%, #25D366 100%)",
              padding: "12px 14px",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              cursor: "grab",
              color: "#fff",
              flexShrink: 0,
              userSelect: "none",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
              <GripHorizontal size={15} style={{ opacity: 0.55, flexShrink: 0 }} />
              <div
                style={{
                  width: "36px",
                  height: "36px",
                  borderRadius: "50%",
                  background: "rgba(255,255,255,0.18)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  flexShrink: 0,
                }}
              >
                <svg width="21" height="21" viewBox="0 0 24 24" fill="#fff">
                  <path d="M12.04 2C6.58 2 2.13 6.45 2.13 11.91c0 1.75.46 3.45 1.32 4.95L2.05 22l5.25-1.38a9.9 9.9 0 004.74 1.21h.005c5.46 0 9.91-4.45 9.91-9.91 0-2.65-1.03-5.14-2.9-7.01A9.86 9.86 0 0012.04 2zm5.83 14.1c-.24.68-1.4 1.3-1.93 1.38-.5.08-1.12.11-1.8-.11-.42-.13-.95-.31-1.64-.6-2.88-1.24-4.76-4.14-4.9-4.33-.14-.19-1.17-1.56-1.17-2.98 0-1.41.74-2.11 1-2.4.26-.29.57-.36.76-.36h.55c.18 0 .42-.07.65.5.24.58.82 2 .89 2.15.07.15.12.32.02.52-.1.19-.15.31-.3.48-.15.17-.31.38-.44.51-.15.15-.3.31-.13.6.17.29.76 1.25 1.63 2.03 1.12 1 2.06 1.31 2.35 1.46.29.15.46.13.63-.08.17-.2.72-.84.91-1.13.19-.29.39-.24.65-.14.27.1 1.69.8 1.98.94.29.15.48.22.55.34.07.13.07.72-.17 1.4z" />
                </svg>
              </div>
              <div style={{ minWidth: 0 }}>
                <div
                  style={{
                    fontWeight: 700,
                    fontSize: "13.5px",
                    lineHeight: "1.2",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                    maxWidth: "180px",
                  }}
                >
                  {selectedClientName}
                </div>
                <div
                  style={{
                    fontSize: "10.5px",
                    opacity: 0.85,
                    display: "flex",
                    alignItems: "center",
                    gap: "5px",
                    marginTop: "1px",
                  }}
                >
                  <span
                    style={{
                      width: "6px",
                      height: "6px",
                      borderRadius: "50%",
                      background: "#a7f3d0",
                      display: "inline-block",
                      flexShrink: 0,
                    }}
                  />
                  <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    Meta Cloud API · {recipientNumber}
                  </span>
                </div>
              </div>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: "5px" }}>
              <button
                type="button"
                onClick={() => setIsRepPanelOpen(true)}
                style={headerBtnStyle}
                title="Open Rep Operations Inbox (Buckets & Compliance)"
              >
                <MessageSquare size={12} />
              </button>
              <button
                type="button"
                onClick={() => setIsMinimized((p) => !p)}
                style={headerBtnStyle}
                title={isMinimized ? "Expand" : "Minimize"}
              >
                {isMinimized ? <Maximize2 size={12} /> : <Minimize2 size={12} />}
              </button>
              <button
                type="button"
                onClick={() => setIsOpen(false)}
                style={headerBtnStyle}
                title="Close"
              >
                <X size={13} />
              </button>
            </div>
          </div>

          {/* ── Expanded Body ─────────────────────────────────────────────── */}
          {!isMinimized && (
            <>
              {/* Recipient / Client Selector */}
              <div
                style={{
                  padding: "8px 12px",
                  background: "#f8fafc",
                  borderBottom: "1px solid #f1f5f9",
                  display: "flex",
                  gap: "6px",
                  flexShrink: 0,
                }}
              >
                <div style={{ position: "relative", flex: 1 }}>
                  <Phone
                    size={12}
                    style={{
                      position: "absolute",
                      left: "9px",
                      top: "50%",
                      transform: "translateY(-50%)",
                      color: "#94a3b8",
                    }}
                  />
                  <input
                    type="text"
                    value={recipientNumber}
                    onChange={(e) => {
                      setRecipientNumber(e.target.value)
                      resetForNumber(e.target.value)
                    }}
                    placeholder="+60109722730"
                    style={{
                      width: "100%",
                      padding: "6px 8px 6px 26px",
                      fontSize: "12px",
                      fontWeight: 600,
                      borderRadius: "8px",
                      border: "1px solid #e2e8f0",
                      outline: "none",
                      boxSizing: "border-box",
                      background: "#fff",
                      color: "#1e293b",
                    }}
                  />
                </div>

                {clients.length > 0 && (
                  <select
                    onChange={(e) => {
                      const c = clients.find((item) => item.clientId === e.target.value)
                      if (c) handleSelectClient(c)
                    }}
                    value={selectedClientId || ""}
                    style={{
                      padding: "6px 8px",
                      fontSize: "11px",
                      fontWeight: 600,
                      borderRadius: "8px",
                      border: "1px solid #e2e8f0",
                      background: "#fff",
                      maxWidth: "130px",
                      cursor: "pointer",
                      color: "#374151",
                    }}
                  >
                    <option value="" disabled>
                      Switch client…
                    </option>
                    {clients.map((c) => (
                      <option key={c.clientId} value={c.clientId}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                )}
              </div>

              {/* ── Chat Message Area — white background ─────────────────── */}
              <div
                ref={chatScrollRef}
                style={{
                  flex: 1,
                  overflowY: "auto",
                  padding: "14px 12px",
                  background: "#ffffff",
                  display: "flex",
                  flexDirection: "column",
                  gap: "8px",
                  minHeight: 0,
                }}
              >
                {/* Header pill */}
                <div style={centerPillStyle}>
                  🔒 End-to-end encrypted · Meta Cloud API v25.0
                </div>

                {/* 24-hour window notification banner */}
                <div
                  style={{
                    background: "#fefce8",
                    border: "1px solid #fef08a",
                    borderRadius: "8px",
                    padding: "7px 10px",
                    fontSize: "11px",
                    color: "#854d0e",
                    lineHeight: 1.4,
                  }}
                >
                  <span style={{ fontWeight: 700 }}>Meta 24h Window:</span> Outside an active 24h conversation, Meta requires sending a <em>Template</em> first, or the client must message <strong>+1 555-138-6714</strong> from their phone.
                </div>

                {/* AI Pitch draft card */}
                {clientPitchDraft && (
                  <div
                    style={{
                      background: "#f0fdf4",
                      borderRadius: "10px",
                      padding: "10px 12px",
                      border: "1.5px solid #86efac",
                      display: "flex",
                      flexDirection: "column",
                      gap: "8px",
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "5px",
                        color: "#15803d",
                        fontSize: "10.5px",
                        fontWeight: 700,
                      }}
                    >
                      <Sparkles size={13} />
                      AI Pitch Draft · {selectedClientName}
                    </div>
                    <div
                      style={{
                        fontSize: "11.5px",
                        lineHeight: "1.5",
                        color: "#1e293b",
                        background: "#fff",
                        padding: "8px 10px",
                        borderRadius: "6px",
                        maxHeight: "90px",
                        overflowY: "auto",
                        border: "1px solid #dcfce7",
                      }}
                    >
                      {pitchLoading ? (
                        <span style={{ color: "#6b7280", display: "flex", alignItems: "center", gap: "5px" }}>
                          <RefreshCw size={11} className="animate-spin" /> Generating…
                        </span>
                      ) : (
                        clientPitchDraft
                      )}
                    </div>
                    <button
                      type="button"
                      onClick={() => handleSendMessage(clientPitchDraft)}
                      disabled={isSending || pitchLoading}
                      style={{
                        padding: "7px 12px",
                        borderRadius: "7px",
                        border: "none",
                        background: "linear-gradient(135deg,#25D366,#128C7E)",
                        color: "#fff",
                        fontSize: "11px",
                        fontWeight: 700,
                        cursor: "pointer",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        gap: "5px",
                      }}
                    >
                      <Send size={11} /> Send This Pitch via WhatsApp
                    </button>
                  </div>
                )}

                {/* Messages */}
                {messages.map((msg) => {
                  if (msg.sender === "system") {
                    return (
                      <div key={msg.id} style={centerPillStyle}>
                        {msg.text}
                      </div>
                    )
                  }

                  const isUser = msg.sender === "user" || msg.sender === "agent"
                  const isClient = msg.sender === "client"

                  return (
                    <div
                      key={msg.id}
                      style={{
                        alignSelf: isUser ? "flex-end" : "flex-start",
                        maxWidth: "80%",
                        display: "flex",
                        flexDirection: "column",
                        gap: "2px",
                      }}
                    >
                      {isClient && (
                        <span
                          style={{
                            fontSize: "10px",
                            fontWeight: 700,
                            color: "#128C7E",
                            paddingLeft: "4px",
                          }}
                        >
                          {msg.client_name || selectedClientName}
                        </span>
                      )}
                      <div
                        style={{
                          background: isUser ? "#d9fdd3" : "#f1f5f9",
                          borderRadius: isUser
                            ? "14px 14px 3px 14px"
                            : "14px 14px 14px 3px",
                          padding: "8px 11px",
                          boxShadow: "0 1px 2px rgba(0,0,0,0.06)",
                          fontSize: "12.5px",
                          color: "#111827",
                          lineHeight: "1.45",
                          wordBreak: "break-word",
                        }}
                      >
                        {msg.text}
                        <div
                          style={{
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "flex-end",
                            gap: "3px",
                            marginTop: "4px",
                            fontSize: "9.5px",
                            color: "#94a3b8",
                          }}
                        >
                          {fmt(msg.timestamp)}
                          {isUser && (
                            <>
                              {msg.status === "sending" && (
                                <RefreshCw size={9} style={{ animation: "spin 1s linear infinite" }} />
                              )}
                              {msg.status === "delivered" && (
                                <CheckCheck size={12} color="#53bdeb" />
                              )}
                              {msg.status === "failed" && (
                                <span style={{ color: "#ef4444", fontSize: "9px" }}>✕ failed</span>
                              )}
                            </>
                          )}
                          {isClient && (
                            <span style={{ color: "#10b981", fontWeight: 700, fontSize: "8.5px" }}>
                              RECV
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>

              {/* ── Quick Action Bar ──────────────────────────────────────── */}
              <div
                style={{
                  padding: "6px 10px",
                  background: "#f8fafc",
                  borderTop: "1px solid #f1f5f9",
                  display: "flex",
                  gap: "5px",
                  overflowX: "auto",
                  flexShrink: 0,
                }}
              >
                <button
                  type="button"
                  onClick={() => handleSimulateIncoming("1")}
                  disabled={isSimulating}
                  style={{
                    ...quickBtnStyle,
                    background: "#ecfdf5",
                    borderColor: "#6ee7b7",
                    color: "#065f46",
                    fontWeight: 700,
                  }}
                  title="Simulate client replying '1' to book Slot 1"
                >
                  <MessageSquare size={10} />
                  {isSimulating ? "Simulating…" : "Reply '1' (Auto-Book)"}
                </button>
                <button
                  type="button"
                  onClick={() => handleSimulateIncoming("Can we do next Monday at 2:00 PM instead?")}
                  disabled={isSimulating}
                  style={quickBtnStyle}
                  title="Simulate client requesting custom time"
                >
                  🕒 Custom Time
                </button>
                <button
                  type="button"
                  onClick={() => handleSimulateIncoming("Can you send technical documentation first?")}
                  disabled={isSimulating}
                  style={quickBtnStyle}
                  title="Simulate client inquiry needing rep handoff"
                >
                  ❓ Inquiry
                </button>
                <button
                  type="button"
                  onClick={() => handleSendMessage("Initial outreach via Meta Cloud API", "hello_world")}
                  disabled={isSending}
                  style={{
                    ...quickBtnStyle,
                    background: "#ecfdf5",
                    borderColor: "#a7f3d0",
                    color: "#065f46",
                    fontWeight: 700,
                  }}
                  title="Send Meta hello_world template to open the 24h messaging window"
                >
                  ⚡ Start Session (Template)
                </button>
                <button
                  type="button"
                  onClick={() =>
                    setInputMessage(
                      "Would your operations team be open to a 20-minute physical unit demo this week?"
                    )
                  }
                  style={quickBtnStyle}
                >
                  📅 Demo Invite
                </button>
                <button
                  type="button"
                  onClick={() =>
                    setInputMessage(
                      "Our simulation indicates an estimated 8.4-month payback ROI on this unit."
                    )
                  }
                  style={quickBtnStyle}
                >
                  📈 ROI Stats
                </button>
              </div>

              {/* Error banner */}
              {errorMessage && (
                <div
                  style={{
                    padding: "5px 12px",
                    background: "#fef2f2",
                    color: "#b91c1c",
                    fontSize: "11px",
                    borderTop: "1px solid #fee2e2",
                    flexShrink: 0,
                  }}
                >
                  ⚠ {errorMessage}
                </div>
              )}

              {/* ── Composer Footer ───────────────────────────────────────── */}
              <div
                style={{
                  padding: "10px 12px",
                  background: "#f8fafc",
                  borderTop: "1px solid #f1f5f9",
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  flexShrink: 0,
                }}
              >
                <input
                  type="text"
                  value={inputMessage}
                  onChange={(e) => setInputMessage(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault()
                      handleSendMessage()
                    }
                  }}
                  placeholder={`Message ${selectedClientName}…`}
                  disabled={isSending}
                  style={{
                    flex: 1,
                    minWidth: 0,
                    padding: "9px 14px",
                    borderRadius: "22px",
                    border: "1px solid #e2e8f0",
                    background: "#fff",
                    fontSize: "12.5px",
                    outline: "none",
                    color: "#1e293b",
                    boxShadow: "inset 0 1px 3px rgba(0,0,0,0.04)",
                  }}
                />
                <button
                  type="button"
                  onClick={() => handleSendMessage()}
                  disabled={isSending || !inputMessage.trim()}
                  style={{
                    width: "38px",
                    height: "38px",
                    borderRadius: "50%",
                    background:
                      inputMessage.trim() && !isSending
                        ? "linear-gradient(135deg,#25D366,#128C7E)"
                        : "#e2e8f0",
                    border: "none",
                    color: "#fff",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    cursor: inputMessage.trim() && !isSending ? "pointer" : "default",
                    transition: "background 0.15s ease",
                    flexShrink: 0,
                  }}
                >
                  {isSending ? (
                    <RefreshCw size={14} style={{ animation: "spin 1s linear infinite" }} />
                  ) : (
                    <Send size={15} style={{ transform: "translateX(1px)" }} />
                  )}
                </button>
              </div>
            </>
          )}
        </div>
      )}

      {/* ── Rep Operations Panel Modal ─────────────────────────────────────── */}
      <WhatsAppRepPanel
        isOpen={isRepPanelOpen}
        onClose={() => setIsRepPanelOpen(false)}
        agentId={agentId}
        initialPhoneNumber={recipientNumber}
      />

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
      `}</style>
    </>
  )
}

// ─── Shared micro-styles ────────────────────────────────────────────────────
const headerBtnStyle: React.CSSProperties = {
  background: "rgba(255,255,255,0.15)",
  border: "none",
  borderRadius: "6px",
  color: "#fff",
  width: "26px",
  height: "26px",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  cursor: "pointer",
  flexShrink: 0,
}

const centerPillStyle: React.CSSProperties = {
  alignSelf: "center",
  background: "#f1f5f9",
  borderRadius: "8px",
  padding: "4px 11px",
  fontSize: "10px",
  color: "#64748b",
  textAlign: "center",
  maxWidth: "90%",
}

const quickBtnStyle: React.CSSProperties = {
  padding: "4px 9px",
  borderRadius: "6px",
  border: "1px solid #e2e8f0",
  background: "#fff",
  fontSize: "10px",
  fontWeight: 600,
  color: "#374151",
  cursor: "pointer",
  display: "flex",
  alignItems: "center",
  gap: "4px",
  whiteSpace: "nowrap",
  flexShrink: 0,
}
