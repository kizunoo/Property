"use client";

import { useState, useEffect, useMemo, useRef } from "react";
import {
  MessageSquare,
  Check,
  CheckCheck,
  AlertCircle,
  Clock,
  Sparkles,
  Send,
  X,
  Bell,
  Ban,
  UserCheck,
  RefreshCw,
  ChevronRight,
  ShieldAlert,
} from "lucide-react";

export type ConversationBucket =
  | "all"
  | "needs_reply"
  | "booked"
  | "waiting_on_client"
  | "opted_out"
  | "cold";

export interface ConversationThread {
  id: string;
  phone_number: string;
  client_name: string;
  client_id?: string | null;
  agent_id?: string | null;
  status_bucket: ConversationBucket;
  opted_out: boolean;
  automation_paused: boolean;
  snoozed_until?: string | null;
  last_nudged_at?: string | null;
  last_read_at?: string | null;
  unread_count?: number;
  updated_at?: string | null;
  needs_followup_48h?: boolean;
  window_open?: boolean;
  window_remaining_hours?: number;
}

export interface ChatMessage {
  id: string;
  to_number: string;
  sender: "agent" | "client" | "system";
  text: string;
  status: "pending" | "sent" | "delivered" | "read" | "failed" | "received";
  timestamp: string;
  client_name?: string;
  is_ai_draft?: boolean;
  error_code?: number;
  error_message?: string;
  failure_reason?: string;
}


interface WhatsAppRepPanelProps {
  isOpen: boolean;
  onClose: () => void;
  agentId?: string | null;
  initialPhoneNumber?: string | null;
}

export function WhatsAppRepPanel({
  isOpen,
  onClose,
  agentId,
  initialPhoneNumber,
}: WhatsAppRepPanelProps) {
  const [threads, setThreads] = useState<ConversationThread[]>([]);
  const [selectedThread, setSelectedThread] = useState<ConversationThread | null>(null);
  const [activeBucket, setActiveBucket] = useState<ConversationBucket>("all");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoadingThreads, setIsLoadingThreads] = useState(false);
  const [isLoadingMessages, setIsLoadingMessages] = useState(false);
  const [inputText, setInputText] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [isSuggesting, setIsSuggesting] = useState(false);
  const [aiDraftBadge, setAiDraftBadge] = useState<boolean>(false);
  const [showOptOutWarningModal, setShowOptOutWarningModal] = useState(false);
  const [nudgeNotice, setNudgeNotice] = useState<string | null>(null);
  const [actionNotice, setActionNotice] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // 1. Fetch conversation threads
  const loadThreads = async () => {
    setIsLoadingThreads(true);
    try {
      const url = agentId
        ? `/api/whatsapp/conversations?agent_id=${encodeURIComponent(agentId)}`
        : `/api/whatsapp/conversations`;
      const res = await fetch(url);
      if (res.ok) {
        const data = await res.json();
        const list: ConversationThread[] = data.conversations || [];
        setThreads(list);
        if (list.length > 0 && !selectedThread) {
          if (initialPhoneNumber) {
            const found = list.find((t) => t.phone_number.includes(initialPhoneNumber));
            setSelectedThread(found || list[0]);
          } else {
            setSelectedThread(list[0]);
          }
        }
      }
    } catch (e) {
      console.error("[WhatsAppRepPanel] Failed to load threads:", e);
    } finally {
      setIsLoadingThreads(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      loadThreads();
    }
  }, [isOpen, agentId]);

  // 2. Fetch messages for the selected thread
  const loadMessages = async (phoneNumber: string) => {
    if (!phoneNumber) return;
    setIsLoadingMessages(true);
    try {
      const res = await fetch(`/api/whatsapp/messages?to_number=${encodeURIComponent(phoneNumber)}`);
      if (res.ok) {
        const data = await res.json();
        setMessages(data.messages || []);
      }
    } catch (e) {
      console.error("[WhatsAppRepPanel] Failed to load messages:", e);
    } finally {
      setIsLoadingMessages(false);
    }
  };

  useEffect(() => {
    if (selectedThread?.phone_number) {
      loadMessages(selectedThread.phone_number);
    }
  }, [selectedThread?.phone_number]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Filtered threads by bucket
  const filteredThreads = useMemo(() => {
    if (activeBucket === "all") return threads;
    return threads.filter((t) => t.status_bucket === activeBucket);
  }, [threads, activeBucket]);

  // Counts per bucket
  const bucketCounts = useMemo(() => {
    const counts = {
      all: threads.length,
      needs_reply: 0,
      booked: 0,
      waiting_on_client: 0,
      opted_out: 0,
      cold: 0,
    };
    for (const t of threads) {
      if (t.status_bucket in counts) {
        counts[t.status_bucket as keyof typeof counts]++;
      }
    }
    return counts;
  }, [threads]);

  // Handle Mark Conversation as Read
  const handleMarkAsRead = async () => {
    if (!selectedThread) return;
    try {
      await fetch(`/api/whatsapp/conversations/${encodeURIComponent(selectedThread.id)}/read`, {
        method: "POST",
      });
      setThreads((prev) =>
        prev.map((t) => (t.id === selectedThread.id ? { ...t, unread_count: 0 } : t))
      );
      setActionNotice("Thread marked as read.");
      setTimeout(() => setActionNotice(null), 3000);
    } catch (e) {
      console.error("Mark read error:", e);
    }
  };

  // Handle Nudge Dispatch
  const handleSendNudge = async () => {
    if (!selectedThread) return;
    try {
      const res = await fetch(`/api/whatsapp/nudge`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: jsonBody({
          phone_number: selectedThread.phone_number,
          client_name: selectedThread.client_name,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setNudgeNotice(data.detail || "Nudge request failed");
      } else {
        setNudgeNotice("Follow-up nudge dispatched.");
        loadMessages(selectedThread.phone_number);
      }
      setTimeout(() => setNudgeNotice(null), 4000);
    } catch (e) {
      setNudgeNotice("Failed to send nudge");
      setTimeout(() => setNudgeNotice(null), 4000);
    }
  };

  // Handle Clear Opt-Out
  const handleClearOptOut = async () => {
    if (!selectedThread) return;
    try {
      const res = await fetch("/api/whatsapp/clear_opt_out", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: jsonBody({
          phone_number: selectedThread.phone_number,
          agent_name: "Lead Representative",
          agent_id: agentId,
        }),
      });
      if (res.ok) {
        setSelectedThread((prev) => prev ? { ...prev, opted_out: false, automation_paused: false } : null);
        setThreads((prev) =>
          prev.map((t) => (t.id === selectedThread.id ? { ...t, opted_out: false, automation_paused: false } : t))
        );
        setActionNotice("Opt-out cleared and automation resumed.");
        loadMessages(selectedThread.phone_number);
      }
    } catch (e) {
      console.error("Clear opt-out error:", e);
    }
  };

  // Handle Resume Automation
  const handleResumeAutomation = async () => {
    if (!selectedThread) return;
    try {
      const res = await fetch("/api/whatsapp/resume_automation", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: jsonBody({
          phone_number: selectedThread.phone_number,
          agent_name: "Lead Representative",
          agent_id: agentId,
        }),
      });
      if (res.ok) {
        setSelectedThread((prev) => prev ? { ...prev, automation_paused: false } : null);
        setThreads((prev) =>
          prev.map((t) => (t.id === selectedThread.id ? { ...t, automation_paused: false } : t))
        );
        setActionNotice("Automation resumed.");
        loadMessages(selectedThread.phone_number);
      }
    } catch (e) {
      console.error("Resume automation error:", e);
    }
  };

  // Handle Send Slots Pitch Template (when 24h window is closed)
  const handleSendSlotsPitchTemplate = async () => {
    if (!selectedThread) return;
    try {
      const res = await fetch("/api/whatsapp/send_pitch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: jsonBody({
          client_id: selectedThread.client_id || "client-default",
          property_id: "prop-default",
          sender_agent_id: agentId,
          to_number: selectedThread.phone_number,
          template_name: "viewing_slots_pitch",
        }),
      });
      if (res.ok) {
        setActionNotice("Slots pitch template dispatched.");
        loadMessages(selectedThread.phone_number);
      } else {
        const d = await res.json().catch(() => ({}));
        setActionNotice(`Failed to send slots pitch: ${d.detail || "Error"}`);
      }
    } catch (e) {
      console.error("Send slots pitch template error:", e);
    }
  };

  // Handle AI Suggest Reply
  const handleSuggestReply = async () => {
    if (!selectedThread) return;
    setIsSuggesting(true);
    try {
      const lastClientMsg = [...messages].reverse().find((m) => m.sender === "client");
      const res = await fetch(`/api/whatsapp/suggest_reply`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: jsonBody({
          phone_number: selectedThread.phone_number,
          prompt_context: lastClientMsg?.text || "General response",
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setInputText(data.suggested_text || "");
        setAiDraftBadge(true);
      }
    } catch (e) {
      console.error("Suggest reply error:", e);
    } finally {
      setIsSuggesting(false);
    }
  };

  // Helper for JSON payload
  function jsonBody(obj: any) {
    return JSON.stringify(obj);
  }

  // Handle Send Message
  const executeSendMessage = async (manualOverride = false) => {
    if (!selectedThread || !inputText.trim()) return;
    setIsSending(true);
    try {
      const res = await fetch(`/api/whatsapp/send`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: jsonBody({
          to_number: selectedThread.phone_number,
          message: inputText.trim(),
          client_id: selectedThread.client_id,
          client_name: selectedThread.client_name,
          agent_id: agentId,
          manual_override: manualOverride,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        if (data.detail?.includes("opted out")) {
          setShowOptOutWarningModal(true);
        } else {
          setActionNotice(`Error: ${data.detail || "Send failed"}`);
          setTimeout(() => setActionNotice(null), 4000);
        }
      } else {
        setInputText("");
        setAiDraftBadge(false);
        setShowOptOutWarningModal(false);
        loadMessages(selectedThread.phone_number);
        setActionNotice("Message sent.");
        setTimeout(() => setActionNotice(null), 3000);
      }
    } catch (e) {
      setActionNotice("Failed to send message.");
      setTimeout(() => setActionNotice(null), 4000);
    } finally {
      setIsSending(false);
    }
  };

  const handleSendClick = () => {
    if (selectedThread?.opted_out) {
      setShowOptOutWarningModal(true);
    } else {
      executeSendMessage(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="flex h-[90vh] w-full max-w-6xl flex-col overflow-hidden rounded-2xl border border-neutral-200 bg-white shadow-2xl">
        {/* Top Header */}
        <div className="flex items-center justify-between border-b border-neutral-200 bg-neutral-900 px-6 py-4 text-white">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-500 text-black">
              <MessageSquare className="h-5 w-5" strokeWidth={2.5} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold tracking-tight">WhatsApp Rep Operations Panel</h2>
                <span className="rounded bg-emerald-500/20 px-2 py-0.5 font-mono text-[10px] font-bold text-emerald-400 border border-emerald-500/30">
                  LIVE INBOX
                </span>
              </div>
              <p className="text-xs text-neutral-400">
                Automated compliance guards · Multi-agent thread sync · Guarded AI drafting
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-2 text-neutral-400 hover:bg-neutral-800 hover:text-white transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Action notices banner */}
        {actionNotice && (
          <div className="bg-emerald-50 border-b border-emerald-200 px-6 py-2 text-xs font-semibold text-emerald-800 flex items-center justify-between">
            <span>{actionNotice}</span>
            <button onClick={() => setActionNotice(null)} className="text-emerald-600 hover:text-emerald-900">
              ✕
            </button>
          </div>
        )}
        {nudgeNotice && (
          <div className="bg-amber-50 border-b border-amber-200 px-6 py-2 text-xs font-semibold text-amber-900 flex items-center justify-between">
            <span>{nudgeNotice}</span>
            <button onClick={() => setNudgeNotice(null)} className="text-amber-700 hover:text-amber-950">
              ✕
            </button>
          </div>
        )}

        {/* Main Body */}
        <div className="grid flex-1 grid-cols-1 md:grid-cols-12 overflow-hidden">
          {/* Left Column: Bucket Filter & Thread List (4 cols) */}
          <div className="col-span-12 md:col-span-4 flex flex-col border-r border-neutral-200 bg-neutral-50/50">
            {/* Bucket Filter Tabs */}
            <div className="border-b border-neutral-200 bg-white p-3">
              <div className="grid grid-cols-3 gap-1 mb-1">
                <button
                  onClick={() => setActiveBucket("all")}
                  className={`rounded-lg px-2 py-1.5 text-[11px] font-bold uppercase transition-all ${
                    activeBucket === "all"
                      ? "bg-neutral-900 text-white"
                      : "text-neutral-600 hover:bg-neutral-100"
                  }`}
                >
                  All ({bucketCounts.all})
                </button>
                <button
                  onClick={() => setActiveBucket("needs_reply")}
                  className={`rounded-lg px-2 py-1.5 text-[11px] font-bold uppercase transition-all ${
                    activeBucket === "needs_reply"
                      ? "bg-rose-600 text-white"
                      : "text-rose-700 hover:bg-rose-50"
                  }`}
                >
                  Reply ({bucketCounts.needs_reply})
                </button>
                <button
                  onClick={() => setActiveBucket("booked")}
                  className={`rounded-lg px-2 py-1.5 text-[11px] font-bold uppercase transition-all ${
                    activeBucket === "booked"
                      ? "bg-emerald-600 text-white"
                      : "text-emerald-700 hover:bg-emerald-50"
                  }`}
                >
                  Booked ({bucketCounts.booked})
                </button>
              </div>
              <div className="grid grid-cols-3 gap-1">
                <button
                  onClick={() => setActiveBucket("waiting_on_client")}
                  className={`rounded-lg px-2 py-1.5 text-[11px] font-bold uppercase transition-all ${
                    activeBucket === "waiting_on_client"
                      ? "bg-amber-500 text-black"
                      : "text-amber-700 hover:bg-amber-50"
                  }`}
                >
                  Waiting ({bucketCounts.waiting_on_client})
                </button>
                <button
                  onClick={() => setActiveBucket("opted_out")}
                  className={`rounded-lg px-2 py-1.5 text-[11px] font-bold uppercase transition-all ${
                    activeBucket === "opted_out"
                      ? "bg-neutral-800 text-white"
                      : "text-neutral-500 hover:bg-neutral-100"
                  }`}
                >
                  Opt-Out ({bucketCounts.opted_out})
                </button>
                <button
                  onClick={() => setActiveBucket("cold")}
                  className={`rounded-lg px-2 py-1.5 text-[11px] font-bold uppercase transition-all ${
                    activeBucket === "cold"
                      ? "bg-neutral-400 text-black"
                      : "text-neutral-500 hover:bg-neutral-100"
                  }`}
                >
                  Cold ({bucketCounts.cold})
                </button>
              </div>
            </div>

            {/* Conversation Threads List */}
            <div className="flex-1 overflow-y-auto divide-y divide-neutral-200">
              {isLoadingThreads ? (
                <div className="flex items-center justify-center py-12 text-xs font-semibold text-neutral-400">
                  <RefreshCw className="mr-2 h-4 w-4 animate-spin" /> Loading conversations...
                </div>
              ) : filteredThreads.length === 0 ? (
                <div className="py-12 text-center text-xs font-medium text-neutral-400">
                  No conversations in this bucket.
                </div>
              ) : (
                filteredThreads.map((thread) => {
                  const isSelected = selectedThread?.id === thread.id;
                  return (
                    <button
                      key={thread.id}
                      onClick={() => setSelectedThread(thread)}
                      className={`w-full text-left p-3.5 transition-colors flex items-start justify-between gap-2 ${
                        isSelected
                          ? "bg-white border-l-4 border-l-black shadow-sm"
                          : "hover:bg-neutral-100/70"
                      }`}
                    >
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2 mb-1 flex-wrap">
                          <span className="font-bold text-xs text-neutral-900 truncate">
                            {thread.client_name}
                          </span>
                          {thread.opted_out && (
                            <span className="rounded bg-rose-100 px-1.5 py-0.2 text-[9px] font-extrabold text-rose-700">
                              OPTED OUT
                            </span>
                          )}
                          {thread.automation_paused && !thread.opted_out && (
                            <span className="rounded bg-amber-100 px-1.5 py-0.2 text-[9px] font-extrabold text-amber-800">
                              PAUSED
                            </span>
                          )}
                          {thread.needs_followup_48h && (
                            <span className="rounded bg-amber-500/20 border border-amber-500/40 px-1.5 py-0.2 text-[9px] font-extrabold text-amber-900">
                              FOLLOW UP
                            </span>
                          )}
                        </div>
                        <div className="font-mono text-[11px] text-neutral-500">
                          +{thread.phone_number}
                        </div>
                      </div>

                      <div className="flex flex-col items-end gap-1 shrink-0">
                        <span
                          className={`rounded px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider ${
                            thread.status_bucket === "needs_reply"
                              ? "bg-rose-100 text-rose-700"
                              : thread.status_bucket === "booked"
                              ? "bg-emerald-100 text-emerald-800"
                              : thread.status_bucket === "waiting_on_client"
                              ? "bg-amber-100 text-amber-800"
                              : "bg-neutral-200 text-neutral-700"
                          }`}
                        >
                          {thread.status_bucket.replace(/_/g, " ")}
                        </span>
                        {(thread.unread_count || 0) > 0 && (
                          <span className="flex h-4 min-w-4 items-center justify-center rounded-full bg-rose-600 px-1 text-[9px] font-black text-white">
                            {thread.unread_count}
                          </span>
                        )}
                      </div>
                    </button>
                  );
                })
              )}
            </div>
          </div>

          {/* Right Column: Active Thread Feed & Input Box (8 cols) */}
          <div className="col-span-12 md:col-span-8 flex flex-col bg-white">
            {selectedThread ? (
              <>
                {/* Contact Header */}
                <div className="flex items-center justify-between border-b border-neutral-200 bg-neutral-50/50 px-6 py-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-bold text-neutral-900">
                        {selectedThread.client_name}
                      </span>
                      <span className="font-mono text-xs text-neutral-500">
                        +{selectedThread.phone_number}
                      </span>
                      {selectedThread.window_open ? (
                        <span className="rounded bg-emerald-50 border border-emerald-300 px-2 py-0.5 text-[10px] font-bold text-emerald-800">
                          ● 24h Window Open ({selectedThread.window_remaining_hours ?? 24}h remaining)
                        </span>
                      ) : (
                        <span className="rounded bg-amber-50 border border-amber-300 px-2 py-0.5 text-[10px] font-bold text-amber-900">
                          ○ 24h Window Closed
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-[11px] text-neutral-400">
                        Bucket:{" "}
                        <strong className="text-neutral-700 capitalize">
                          {selectedThread.status_bucket.replace(/_/g, " ")}
                        </strong>
                      </span>
                      {selectedThread.last_nudged_at && (
                        <span className="text-[10px] text-neutral-400">
                          · Last nudged: {new Date(selectedThread.last_nudged_at).toLocaleDateString()}
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      onClick={handleMarkAsRead}
                      className="inline-flex items-center gap-1 rounded-lg border border-neutral-300 bg-white px-2.5 py-1.5 text-xs font-semibold text-neutral-700 hover:bg-neutral-50 transition-colors shadow-sm"
                    >
                      <UserCheck className="h-3.5 w-3.5 text-neutral-500" />
                      Mark Read
                    </button>

                    <button
                      onClick={handleSendNudge}
                      className="inline-flex items-center gap-1 rounded-lg border border-amber-300 bg-amber-50 px-2.5 py-1.5 text-xs font-bold text-amber-900 hover:bg-amber-100 transition-colors shadow-sm"
                    >
                      <Bell className="h-3.5 w-3.5 text-amber-600" />
                      Follow-up Nudge
                    </button>
                  </div>
                </div>

                {/* Opt-out or Paused Banner */}
                {selectedThread.opted_out && (
                  <div className="bg-rose-50 border-b border-rose-200 px-6 py-2.5 text-xs text-rose-900 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Ban className="h-4 w-4 text-rose-600" />
                      <span>
                        <strong>Contact Opted Out:</strong> Automated messages are suspended. Manual messages require explicit rep override.
                      </span>
                    </div>
                    <button
                      onClick={handleClearOptOut}
                      className="rounded-lg bg-rose-600 px-3 py-1 text-xs font-bold text-white hover:bg-rose-700 shadow-sm transition-colors"
                    >
                      Clear Opt-Out
                    </button>
                  </div>
                )}
                {!selectedThread.opted_out && selectedThread.automation_paused && (
                  <div className="bg-amber-50 border-b border-amber-200 px-6 py-2.5 text-xs text-amber-900 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <AlertCircle className="h-4 w-4 text-amber-600" />
                      <span>
                        <strong>Automation Paused:</strong> Contact requested human review. Automation is suspended.
                      </span>
                    </div>
                    <button
                      onClick={handleResumeAutomation}
                      className="rounded-lg bg-amber-600 px-3 py-1 text-xs font-bold text-white hover:bg-amber-700 shadow-sm transition-colors"
                    >
                      Resume Automation
                    </button>
                  </div>
                )}

                {/* Chat Feed */}
                <div className="flex-1 overflow-y-auto p-6 space-y-4 bg-neutral-100/30">
                  {isLoadingMessages ? (
                    <div className="flex items-center justify-center py-16 text-xs text-neutral-400 font-semibold">
                      <RefreshCw className="mr-2 h-4 w-4 animate-spin" /> Loading message history...
                    </div>
                  ) : messages.length === 0 ? (
                    <div className="py-16 text-center text-xs text-neutral-400">
                      No messages recorded yet for this contact.
                    </div>
                  ) : (
                    messages.map((m) => {
                      const isAgent = m.sender === "agent";
                      const isSystem = m.sender === "system";

                      return (
                        <div
                          key={m.id}
                          className={`flex flex-col ${
                            isSystem
                              ? "items-center"
                              : isAgent
                              ? "items-end"
                              : "items-start"
                          }`}
                        >
                          <div
                            className={`max-w-[75%] rounded-2xl px-4 py-2.5 text-sm shadow-sm ${
                              isSystem
                                ? "bg-neutral-200/80 text-neutral-700 text-xs text-center rounded-xl font-medium"
                                : isAgent
                                ? "bg-neutral-900 text-white rounded-br-xs"
                                : "bg-white text-neutral-900 border border-neutral-200 rounded-bl-xs"
                            }`}
                          >
                            <p className="whitespace-pre-wrap leading-relaxed">{m.text}</p>
                          </div>

                          {/* Message metadata */}
                          {!isSystem && (
                            <div className="flex items-center gap-1.5 mt-1 px-1 font-mono text-[10px] text-neutral-400">
                              <span>
                                {new Date(m.timestamp).toLocaleTimeString([], {
                                  hour: "numeric",
                                  minute: "2-digit",
                                })}
                              </span>
                              {isAgent && (
                                <span className="inline-flex items-center gap-1">
                                  {m.status === "read" ? (
                                    <CheckCheck className="h-3 w-3 text-cyan-500" strokeWidth={2.5} />
                                  ) : m.status === "delivered" ? (
                                    <CheckCheck className="h-3 w-3 text-neutral-400" strokeWidth={2.5} />
                                  ) : m.status === "sent" ? (
                                    <Check className="h-3 w-3 text-neutral-400" strokeWidth={2.5} />
                                  ) : m.status === "failed" ? (
                                    <span className="inline-flex items-center gap-1 text-rose-600 font-bold">
                                      <AlertCircle className="h-3 w-3 text-rose-500" strokeWidth={2.5} />
                                      <span>{m.failure_reason || m.error_message || "Delivery failed"}</span>
                                    </span>
                                  ) : null}
                                </span>
                              )}
                            </div>
                          )}
                        </div>
                      );
                    })
                  )}
                  <div ref={messagesEndRef} />
                </div>

                {/* Input Area */}
                <div className="border-t border-neutral-200 bg-white p-4">
                  {/* Suggest Reply Action Toolbar */}
                  <div className="flex items-center justify-between mb-2">
                    <button
                      onClick={handleSuggestReply}
                      disabled={isSuggesting || selectedThread.window_open === false}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-purple-200 bg-purple-50 px-2.5 py-1 text-xs font-bold text-purple-900 hover:bg-purple-100 transition-colors shadow-2xs disabled:opacity-50"
                    >
                      <Sparkles className="h-3.5 w-3.5 text-purple-600" />
                      {isSuggesting ? "Drafting..." : "Suggest AI Reply"}
                    </button>

                    {aiDraftBadge && (
                      <span className="rounded bg-purple-100 px-2 py-0.5 text-[10px] font-bold text-purple-800 border border-purple-200">
                        AI Draft · Review & Edit Before Sending
                      </span>
                    )}
                  </div>

                  {/* Composer with 24h Window Gating */}
                  {selectedThread.window_open === false ? (
                    <div className="rounded-xl border border-amber-200 bg-amber-50/80 p-3">
                      <div className="flex items-center gap-2 text-amber-900 text-xs font-bold mb-2">
                        <Clock className="h-4 w-4 text-amber-700" />
                        <span>24h Window Closed — Free-form text cannot be delivered. Send an approved template to reopen window:</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={handleSendSlotsPitchTemplate}
                          className="rounded-lg border border-neutral-300 bg-white px-3 py-1.5 text-xs font-semibold text-neutral-800 hover:bg-neutral-50 shadow-2xs"
                        >
                          Send Slots Pitch (Template)
                        </button>
                        <button
                          onClick={handleSendNudge}
                          className="rounded-lg border border-amber-300 bg-amber-100 px-3 py-1.5 text-xs font-bold text-amber-900 hover:bg-amber-200 shadow-2xs"
                        >
                          Send Follow-up Nudge (Template)
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex items-end gap-2">
                      <textarea
                        value={inputText}
                        onChange={(e) => setInputText(e.target.value)}
                        placeholder="Type your message or click Suggest AI Reply..."
                        rows={2}
                        className="flex-1 resize-none rounded-xl border border-neutral-300 p-2.5 text-xs text-neutral-900 focus:border-black focus:outline-none"
                      />

                      <button
                        onClick={handleSendClick}
                        disabled={isSending || !inputText.trim()}
                        className="flex h-10 items-center justify-center rounded-xl bg-neutral-900 px-4 text-xs font-bold text-white hover:bg-black transition-colors disabled:opacity-50 shadow-sm"
                      >
                        {isSending ? (
                          <RefreshCw className="h-4 w-4 animate-spin" />
                        ) : (
                          <>
                            <Send className="mr-1.5 h-3.5 w-3.5" /> Send
                          </>
                        )}
                      </button>
                    </div>
                  )}
                </div>
              </>
            ) : (
              <div className="flex flex-1 items-center justify-center text-xs text-neutral-400 font-medium">
                Select a conversation thread from the left to view messages.
              </div>
            )}
          </div>
        </div>

        {/* Modal: Opt-Out Warning & Manual Override Confirmation */}
        {showOptOutWarningModal && (
          <div className="fixed inset-0 z-60 flex items-center justify-center bg-black/50 p-4">
            <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl border border-rose-200">
              <div className="flex items-center gap-3 text-rose-600 mb-3">
                <ShieldAlert className="h-6 w-6" />
                <h3 className="text-base font-bold text-neutral-900">
                  Contact Has Opted Out
                </h3>
              </div>
              <p className="text-xs text-neutral-600 leading-relaxed mb-6">
                <strong>{selectedThread?.client_name}</strong> (+{selectedThread?.phone_number}) has strictly opted out of WhatsApp messages.
                Sending an unprompted message may violate Meta WhatsApp Business messaging policies unless this is an urgent response requested directly by the client.
              </p>
              <div className="flex justify-end gap-3">
                <button
                  onClick={() => setShowOptOutWarningModal(false)}
                  className="rounded-lg border border-neutral-300 px-3.5 py-2 text-xs font-semibold text-neutral-700 hover:bg-neutral-50"
                >
                  Cancel
                </button>
                <button
                  onClick={() => executeSendMessage(true)}
                  className="rounded-lg bg-rose-600 px-4 py-2 text-xs font-bold text-white hover:bg-rose-700 shadow-sm"
                >
                  Confirm Manual Send
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
