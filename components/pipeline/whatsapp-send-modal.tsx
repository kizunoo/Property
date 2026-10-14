"use client";
import { useState, useEffect, useMemo } from "react";
import {
  PitchSlot,
  formatSlotLabel,
  parseSlotsFromDraft,
  splitPitchDraft,
  assemblePitchDraft,
  slotToIso,
  renderViewingSlotsPitchTemplate,
} from "@/lib/slot-utils";

interface WhatsAppSendModalProps {
  isOpen: boolean;
  onClose: () => void;
  clientId: string;
  propertyId: string;
  propertyName?: string;
  clientName: string;
  whatsappNumber: string | null;
  agentId?: string | null;
  draftText: string;
  initialSlots?: PitchSlot[];
  onSentSuccess?: () => void;
}

export function WhatsAppSendModal({
  isOpen,
  onClose,
  clientId,
  propertyId,
  propertyName,
  clientName,
  whatsappNumber,
  agentId,
  draftText,
  initialSlots,
  onSentSuccess,
}: WhatsAppSendModalProps) {
  const [status, setStatus] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [errorMsg, setErrorMsg] = useState("");
  const [targetNumber, setTargetNumber] = useState(whatsappNumber || "60109722730");
  const [messageText, setMessageText] = useState(draftText);
  const [slots, setSlots] = useState<PitchSlot[]>([]);
  const [showSlotEditor, setShowSlotEditor] = useState(false);
  const [useTemplate, setUseTemplate] = useState(false);
  const [attachImage, setAttachImage] = useState(false);
  const [imageWarning, setImageWarning] = useState<string | null>(null);
  const [isWindowOpen, setIsWindowOpen] = useState<boolean | null>(null);
  const [lastInboundTime, setLastInboundTime] = useState<string | null>(null);
  const [isAutomationPaused, setIsAutomationPaused] = useState<boolean>(false);
  const [resumingAutomation, setResumingAutomation] = useState<boolean>(false);

  const todayStr = useMemo(() => {
    return new Date().toISOString().split("T")[0];
  }, []);

  const renderedTemplateText = useMemo(() => {
    return renderViewingSlotsPitchTemplate({
      clientName: clientName || "Valued Partner",
      unitName: propertyName || "Robotics Unit",
      slot1: slots[0]?.label || "Option 1",
      slot2: slots[1]?.label || "Option 2",
      slot3: slots[2]?.label || "Option 3",
    });
  }, [clientName, propertyName, slots]);

  useEffect(() => {
    if (isOpen) {
      setStatus("idle");
      setErrorMsg("");
      setImageWarning(null);
      const initialNum = whatsappNumber || "";
      setTargetNumber(initialNum || "60109722730");
      setMessageText(draftText);
      const resolvedSlots =
        initialSlots && initialSlots.length > 0
          ? initialSlots
          : parseSlotsFromDraft(draftText);
      setSlots(resolvedSlots);

      // Check 24-hour customer service window status and resolve phone number if not supplied
      const clean = initialNum.replace(/\D/g, "");
      fetch(`/api/whatsapp/window_status?phone_number=${clean}&client_id=${clientId}`)
        .then((r) => r.json())
        .then((data) => {
          setIsWindowOpen(data.is_window_open ?? false);
          setLastInboundTime(data.last_inbound_timestamp ?? null);
          setIsAutomationPaused(data.automation_paused ?? false);
          if (data.phone_number && !initialNum) {
            setTargetNumber(data.phone_number);
          }
          if (!data.is_window_open) {
            setUseTemplate(true);
          } else {
            setUseTemplate(false);
          }
        })
        .catch(() => {
          // Default to safe template assumption if status query fails
          setIsWindowOpen(false);
          setUseTemplate(true);
        });
    }
  }, [isOpen, whatsappNumber, draftText, initialSlots, clientId]);

  if (!isOpen) return null;

  const handleResumeAutomation = async () => {
    setResumingAutomation(true);
    try {
      const cleanNum = targetNumber.replace(/\D/g, "");
      const res = await fetch("/api/whatsapp/resume_automation", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone_number: cleanNum, client_id: clientId }),
      });
      if (res.ok) {
        setIsAutomationPaused(false);
      }
    } catch (e) {
      console.error("Failed to resume automation", e);
    } finally {
      setResumingAutomation(false);
    }
  };

  const handleSlotDateChange = (slotIndex: number, newDate: string) => {
    setSlots((prev) => {
      const updated = prev.map((s) => {
        if (s.index !== slotIndex) return s;
        const newLabel = formatSlotLabel(newDate, s.time);
        return { ...s, date: newDate, label: newLabel, slot_iso: slotToIso(newDate, s.time) };
      });
      const { body, cta } = splitPitchDraft(messageText || draftText);
      setMessageText(assemblePitchDraft(body, updated, cta));
      return updated;
    });
  };

  const handleSlotTimeChange = (slotIndex: number, newTime: string) => {
    setSlots((prev) => {
      const updated = prev.map((s) => {
        if (s.index !== slotIndex) return s;
        const newLabel = formatSlotLabel(s.date, newTime);
        return { ...s, time: newTime, label: newLabel, slot_iso: slotToIso(s.date, newTime) };
      });
      const { body, cta } = splitPitchDraft(messageText || draftText);
      setMessageText(assemblePitchDraft(body, updated, cta));
      return updated;
    });
  };

  const handleSend = async () => {
    const cleanNum = targetNumber.replace(/\D/g, "");
    if (!cleanNum) {
      setErrorMsg("Please enter a valid WhatsApp phone number with country code.");
      setStatus("error");
      return;
    }

    setStatus("sending");
    try {
      const sendViaTemplate = isWindowOpen === false || useTemplate;
      const res = await fetch("/api/whatsapp/send_pitch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          client_id: clientId,
          property_id: propertyId,
          to_number: cleanNum,
          message_text: sendViaTemplate ? renderedTemplateText : (messageText || draftText),
          slots: slots.length > 0 ? slots : undefined,
          template_name: sendViaTemplate ? "viewing_slots_pitch" : undefined,
          force_template: sendViaTemplate,
          sender_agent_id: agentId ?? null,
          agent_id: agentId ?? null,
          attach_image: !sendViaTemplate && attachImage,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.detail || data.error || "Send failed");
      }
      if (data.image_warning) {
        setImageWarning(data.image_warning);
      }
      setStatus("sent");
      onSentSuccess?.();
    } catch (e: any) {
      setErrorMsg(e.message || "Something went wrong");
      setStatus("error");
    }
  };

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.5)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
      }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "#fff",
          borderRadius: "16px",
          boxShadow: "0px 12px 40px rgba(0,0,0,0.18)",
          width: "520px",
          maxWidth: "94vw",
          maxHeight: "92vh",
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        }}
      >
        {/* Header — WhatsApp green */}
        <div
          style={{
            background: "#25D366",
            padding: "16px 20px",
            display: "flex",
            alignItems: "center",
            gap: "10px",
          }}
        >
          <svg width="22" height="22" viewBox="0 0 24 24" fill="#fff">
            <path d="M12.04 2C6.58 2 2.13 6.45 2.13 11.91c0 1.75.46 3.45 1.32 4.95L2.05 22l5.25-1.38a9.9 9.9 0 004.74 1.21h.005c5.46 0 9.91-4.45 9.91-9.91 0-2.65-1.03-5.14-2.9-7.01A9.86 9.86 0 0012.04 2zm5.83 14.1c-.24.68-1.4 1.3-1.93 1.38-.5.08-1.12.11-1.8-.11-.42-.13-.95-.31-1.64-.6-2.88-1.24-4.76-4.14-4.9-4.33-.14-.19-1.17-1.56-1.17-2.98 0-1.41.74-2.11 1-2.4.26-.29.57-.36.76-.36h.55c.18 0 .42-.07.65.5.24.58.82 2 .89 2.15.07.15.12.32.02.52-.1.19-.15.31-.3.48-.15.17-.31.38-.44.51-.15.15-.3.31-.13.6.17.29.76 1.25 1.63 2.03 1.12 1 2.06 1.31 2.35 1.46.29.15.46.13.63-.08.17-.2.72-.84.91-1.13.19-.29.39-.24.65-.14.27.1 1.69.8 1.98.94.29.15.48.22.55.34.07.13.07.72-.17 1.4z" />
          </svg>
          <div>
            <span style={{ color: "#fff", fontWeight: 700, fontSize: "15px", display: "block" }}>
              Send Pitch via WhatsApp
            </span>
            <span style={{ color: "rgba(255,255,255,0.85)", fontSize: "11px" }}>
              Meta Cloud API v25.0 · Auto-Scheduling Enabled
            </span>
          </div>
          <button
            onClick={onClose}
            style={{
              marginLeft: "auto",
              background: "transparent",
              border: "none",
              color: "#fff",
              fontSize: "18px",
              cursor: "pointer",
              lineHeight: 1,
              opacity: 0.9,
            }}
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        <div style={{ padding: "20px", overflowY: "auto", flex: 1, minHeight: 0 }}>
          {status === "idle" && (
            <>
              <div style={{ fontSize: "13px", color: "#666", marginBottom: "12px", display: "flex", justifyContent: "space-between" }}>
                <span>Prospect: <strong style={{ color: "#000" }}>{clientName}</strong></span>
                {slots.length > 0 && (
                  <button
                    type="button"
                    onClick={() => setShowSlotEditor(!showSlotEditor)}
                    style={{
                      background: "none",
                      border: "none",
                      color: "#166534",
                      fontSize: "11px",
                      fontWeight: 700,
                      cursor: "pointer",
                      textDecoration: "underline",
                    }}
                  >
                    {showSlotEditor ? "Hide Slot Editor" : "📅 Edit Schedule Slots"}
                  </button>
                )}
              </div>

              {/* Editable Slots Section */}
              {showSlotEditor && slots.length > 0 && (
                <div
                  style={{
                    background: "#f9fafb",
                    border: "1px solid #e5e7eb",
                    borderRadius: "10px",
                    padding: "12px",
                    marginBottom: "14px",
                  }}
                >
                  <div style={{ fontSize: "11px", fontWeight: 700, color: "#111", textTransform: "uppercase", marginBottom: "8px" }}>
                    Proposed Demo Slots (Auto-Synced)
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                    {slots.map((slot) => (
                      <div
                        key={slot.index}
                        style={{
                          background: "#fff",
                          border: "1px solid #e5e7eb",
                          borderRadius: "8px",
                          padding: "8px 10px",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "space-between",
                          gap: "8px",
                        }}
                      >
                        <span
                          style={{
                            background: "#000",
                            color: "#fff",
                            fontSize: "10px",
                            fontWeight: 800,
                            padding: "2px 6px",
                            borderRadius: "4px",
                          }}
                        >
                          Slot {slot.index}
                        </span>

                        <div style={{ display: "flex", alignItems: "center", gap: "6px", flex: 1 }}>
                          <input
                            type="date"
                            value={slot.date}
                            min={todayStr}
                            onChange={(e) => handleSlotDateChange(slot.index, e.target.value)}
                            style={{
                              border: "1px solid #ccc",
                              borderRadius: "6px",
                              padding: "4px 6px",
                              fontSize: "11px",
                              fontWeight: 600,
                              flex: 1,
                            }}
                          />
                          <input
                            type="time"
                            value={slot.time}
                            onChange={(e) => handleSlotTimeChange(slot.index, e.target.value)}
                            style={{
                              border: "1px solid #ccc",
                              borderRadius: "6px",
                              padding: "4px 6px",
                              fontSize: "11px",
                              fontWeight: 600,
                              width: "80px",
                            }}
                          />
                        </div>

                        <span style={{ fontSize: "11px", fontWeight: 700, color: "#333", whiteSpace: "nowrap" }}>
                          {slot.label}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {isAutomationPaused && (
                <div style={{ background: "#fef3c7", border: "1px solid #f59e0b", borderRadius: "8px", padding: "10px 12px", marginBottom: "12px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <div style={{ fontSize: "11px", color: "#92400e" }}>
                    <strong>⚠️ Conversation is Human-Handled</strong>
                    <div style={{ fontSize: "10px", marginTop: "2px" }}>Automation is paused for this client. Automatic replies are currently suppressed.</div>
                  </div>
                  <button
                    type="button"
                    onClick={handleResumeAutomation}
                    disabled={resumingAutomation}
                    style={{
                      background: "#d97706",
                      color: "#fff",
                      border: "none",
                      borderRadius: "6px",
                      padding: "5px 10px",
                      fontSize: "11px",
                      fontWeight: 700,
                      cursor: "pointer",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {resumingAutomation ? "Resuming…" : "Resume Automation"}
                  </button>
                </div>
              )}

              {isWindowOpen === false && (
                <div style={{ background: "#eff6ff", border: "1px solid #3b82f6", borderRadius: "10px", padding: "12px", marginBottom: "14px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "6px", marginBottom: "6px" }}>
                    <span style={{ fontSize: "13px" }}>🔒</span>
                    <strong style={{ fontSize: "12px", color: "#1e40af" }}>24-Hour WhatsApp Window Closed</strong>
                  </div>
                  <p style={{ fontSize: "11px", color: "#1e3a8a", margin: 0, lineHeight: 1.4 }}>
                    Meta requires the approved template (<strong>viewing_slots_pitch</strong>). <strong>Free-text edits will not apply</strong> to outbound delivery. Adjust slot dates/times above to update the dynamic template variables.
                  </p>
                  <div style={{ marginTop: "10px", background: "#fff", border: "1px dashed #93c5fd", borderRadius: "8px", padding: "10px", fontSize: "11px", color: "#333", lineHeight: 1.4 }}>
                    <div style={{ fontWeight: 700, color: "#1d4ed8", fontSize: "10px", textTransform: "uppercase", marginBottom: "4px" }}>Exact Rendered Template Delivery Preview:</div>
                    {renderedTemplateText}
                  </div>
                </div>
              )}

              <div style={{ marginBottom: "14px" }}>
                <label style={{ fontSize: "11px", fontWeight: 700, color: "#666", textTransform: "uppercase", display: "block", marginBottom: "4px" }}>
                  Recipient WhatsApp Number
                </label>
                <input
                  type="text"
                  value={targetNumber}
                  onChange={(e) => setTargetNumber(e.target.value)}
                  placeholder="e.g. 60109722730"
                  style={{
                    width: "100%",
                    padding: "10px 12px",
                    borderRadius: "8px",
                    border: "1px solid #e5e5e5",
                    fontSize: "13px",
                    boxSizing: "border-box",
                  }}
                />
                <span style={{ fontSize: "11px", color: "#888", marginTop: "4px", display: "block" }}>
                  Registered test numbers must be in country code format (no +).
                </span>
              </div>

              <div style={{ marginBottom: "14px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "4px" }}>
                  <label style={{ fontSize: "11px", fontWeight: 700, color: "#666", textTransform: "uppercase" }}>
                    {isWindowOpen === false ? "Draft Message Reference (Template Mode Active)" : "Outreach Pitch Message"}
                  </label>
                  {isWindowOpen === false && (
                    <span style={{ fontSize: "10px", color: "#dc2626", fontWeight: 700 }}>
                      Template enforced: edits won't apply
                    </span>
                  )}
                </div>
                <textarea
                  value={isWindowOpen === false ? renderedTemplateText : messageText}
                  onChange={(e) => setMessageText(e.target.value)}
                  disabled={isWindowOpen === false}
                  rows={5}
                  style={{
                    width: "100%",
                    background: isWindowOpen === false ? "#f1f5f9" : "#f8f8f8",
                    borderRadius: "10px",
                    padding: "12px 14px",
                    fontSize: "12px",
                    lineHeight: 1.5,
                    color: isWindowOpen === false ? "#64748b" : "#333",
                    maxHeight: "160px",
                    minHeight: "100px",
                    resize: isWindowOpen === false ? "none" : "vertical",
                    overflowY: "auto",
                    border: "1px solid #eee",
                    boxSizing: "border-box",
                    fontFamily: "inherit",
                    outline: "none",
                  }}
                />
              </div>

              {isWindowOpen !== false && !useTemplate ? (
                <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "14px" }}>
                  <input
                    type="checkbox"
                    id="attachImageToggle"
                    checked={attachImage}
                    onChange={(e) => setAttachImage(e.target.checked)}
                    style={{ cursor: "pointer", width: "16px", height: "16px" }}
                  />
                  <label htmlFor="attachImageToggle" style={{ fontSize: "12px", color: "#374151", cursor: "pointer", fontWeight: 500 }}>
                    🖼️ Attach unit image (sent prior to interactive demo slots)
                  </label>
                </div>
              ) : isWindowOpen === false ? (
                <div style={{ fontSize: "11px", color: "#6b7280", marginBottom: "14px", fontStyle: "italic" }}>
                  ℹ️ Unit image attachment requires an active 24h conversation window.
                </div>
              ) : null}

              {isWindowOpen !== false && (
                <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "18px" }}>
                  <input
                    type="checkbox"
                    id="useTemplateToggle"
                    checked={useTemplate}
                    onChange={(e) => {
                      setUseTemplate(e.target.checked);
                      if (e.target.checked) setAttachImage(false);
                    }}
                    style={{ cursor: "pointer", width: "16px", height: "16px" }}
                  />
                  <label htmlFor="useTemplateToggle" style={{ fontSize: "12px", color: "#444", cursor: "pointer" }}>
                    Force template delivery (<strong>viewing_slots_pitch</strong>)
                  </label>
                </div>
              )}

              <button
                onClick={handleSend}
                disabled={!targetNumber.trim()}
                style={{
                  width: "100%",
                  padding: "12px",
                  borderRadius: "10px",
                  border: "none",
                  background: targetNumber.trim() ? "#25D366" : "#ccc",
                  color: "#fff",
                  fontWeight: 700,
                  fontSize: "13px",
                  cursor: targetNumber.trim() ? "pointer" : "not-allowed",
                  transition: "background 0.2s",
                }}
              >
                {isWindowOpen === false || useTemplate ? "Send Approved Template Message" : "Send Pitch Message"}
              </button>
            </>
          )}

          {status === "sending" && (
            <div style={{ textAlign: "center", padding: "24px 0", color: "#666", fontSize: "13px" }}>
              <div style={{ fontSize: "14px", fontWeight: 600, color: "#000", marginBottom: "4px" }}>
                Connecting to Meta Graph API…
              </div>
              <div>Dispatching message to {targetNumber}</div>
            </div>
          )}

          {status === "sent" && (
            <div style={{ textAlign: "center", padding: "16px 0" }}>
              <div style={{ fontSize: "32px", marginBottom: "8px", color: "#166534" }}>✓</div>
              <div style={{ fontWeight: 700, fontSize: "15px", color: "#166534", marginBottom: "4px" }}>
                Message Delivered
              </div>
              <div style={{ fontSize: "12px", color: "#666", marginBottom: "6px" }}>
                Dispatched via Meta Graph API v25.0 to <strong>{targetNumber}</strong>
              </div>
              <div style={{ fontSize: "12px", color: "#888", marginBottom: "18px" }}>
                Relationship stage updated to <strong>Contacted</strong>
              </div>
              {imageWarning && (
                <div style={{ background: "#fffbeb", border: "1px solid #fef3c7", borderRadius: "8px", padding: "8px 12px", color: "#b45309", fontSize: "11px", marginBottom: "16px", textAlign: "left" }}>
                  ⚠️ {imageWarning}
                </div>
              )}
              <button
                onClick={onClose}
                style={{
                  padding: "8px 24px",
                  borderRadius: "8px",
                  border: "1px solid #ccc",
                  background: "#fff",
                  fontSize: "12px",
                  fontWeight: 700,
                  cursor: "pointer",
                }}
              >
                Close
              </button>
            </div>
          )}

          {status === "error" && (
            <div style={{ textAlign: "center", padding: "16px 0" }}>
              <div style={{ fontSize: "13px", color: "#b91c1c", marginBottom: "16px", background: "#fef2f2", padding: "12px", borderRadius: "8px", border: "1px solid #fecaca", textAlign: "left", wordBreak: "break-word" }}>
                {errorMsg}
              </div>
              <button
                onClick={() => setStatus("idle")}
                style={{
                  padding: "8px 20px",
                  borderRadius: "8px",
                  border: "1px solid #ccc",
                  background: "#fff",
                  fontSize: "12px",
                  fontWeight: 700,
                  cursor: "pointer",
                }}
              >
                Try Again
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

