"use client"

import { useState, useEffect, useCallback } from "react"
import {
  KeyRound,
  ShieldAlert,
  UserPlus,
  RefreshCw,
  Ban,
  History,
  CheckCircle2,
  AlertTriangle,
  Loader2,
  Copy,
  Check,
  FileText,
  Send,
} from "lucide-react"

interface Contact {
  id: string
  client_id: string
  name: string
  role_title?: string | null
  email?: string | null
  whatsapp_number?: string | null
  is_primary: boolean
  portal_role: "admin" | "evaluator" | "finance_viewer"
  status: "active" | "deactivated" | "invited"
  failed_login_attempts?: number
  locked_until?: string | null
  rep_code_expires_at?: string | null
  invite_token_expires_at?: string | null
  last_login_at?: string | null
  created_at: string
}

interface AuditEntry {
  id: string
  action: string
  object_type: string
  created_at: string
  details?: Record<string, any>
  portal_contacts?: { name?: string; email?: string } | null
}

// Rep console calls route via Next.js BFF (/api/console/...) with agent auth headers
const FASTAPI_URL = ""

export function PortalAccessPanel({ clientId, clientName }: { clientId: string; clientName: string }) {
  const [contacts, setContacts] = useState<Contact[]>([])
  const [auditLog, setAuditLog] = useState<AuditEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [successMsg, setSuccessMsg] = useState<string | null>(null)
  const [copiedCode, setCopiedCode] = useState<string | null>(null)
  const [issuedInviteUrl, setIssuedInviteUrl] = useState<string | null>(null)

  // Modals / forms state
  const [showAddContact, setShowAddContact] = useState(false)
  const [showAuditLog, setShowAuditLog] = useState(false)
  const [newName, setNewName] = useState("")
  const [newTitle, setNewTitle] = useState("")
  const [newEmail, setNewEmail] = useState("")
  const [newPhone, setNewPhone] = useState("")
  const [newRole, setNewRole] = useState<"admin" | "evaluator" | "finance_viewer">("evaluator")
  const [newIsPrimary, setNewIsPrimary] = useState(false)

  // Quotes state
  const [quotes, setQuotes] = useState<any[]>([])
  const [quoteToSend, setQuoteToSend] = useState<any | null>(null)
  const [sendAmount, setSendAmount] = useState("")
  const [sendCustomerNote, setSendCustomerNote] = useState("")
  const [sendRepNotes, setSendRepNotes] = useState("")

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [cRes, aRes, qRes] = await Promise.all([
        fetch(`${FASTAPI_URL}/api/console/clients/${clientId}/portal/contacts`),
        fetch(`${FASTAPI_URL}/api/console/clients/${clientId}/portal/audit-log`),
        fetch(`${FASTAPI_URL}/api/console/clients/${clientId}/quotes`),
      ])
      if (cRes.ok) {
        const cData = await cRes.json()
        setContacts(cData.contacts || [])
      }
      if (aRes.ok) {
        const aData = await aRes.json()
        setAuditLog(aData.audit_log || [])
      }
      if (qRes.ok) {
        const qData = await qRes.json()
        setQuotes(qData.quotes || [])
      }
    } catch (err) {
      setError("Failed to load portal access configuration.")
    } finally {
      setLoading(false)
    }
  }, [clientId])

  useEffect(() => {
    loadData()
  }, [loadData])

  async function handleCreateContact(e: React.FormEvent) {
    e.preventDefault()
    if (!newName.trim()) return
    setActionLoading(true)
    setError(null)
    try {
      const res = await fetch(`${FASTAPI_URL}/api/console/clients/${clientId}/portal/contacts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: newName.trim(),
          role_title: newTitle.trim() || null,
          email: newEmail.trim() || null,
          whatsapp_number: newPhone.trim() || null,
          portal_role: newRole,
          is_primary: newIsPrimary,
        }),
      })
      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || "Failed to create contact")
      }
      setSuccessMsg(`Created contact ${newName}`)
      setShowAddContact(false)
      setNewName("")
      setNewTitle("")
      setNewEmail("")
      setNewPhone("")
      loadData()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error creating contact")
    } finally {
      setActionLoading(false)
    }
  }

  async function handleIssueCode(contactId: string, contactName: string) {
    setActionLoading(true)
    setError(null)
    try {
      const res = await fetch(`${FASTAPI_URL}/api/console/clients/${clientId}/portal/contacts/${contactId}/issue-code`, {
        method: "POST",
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || "Failed to issue code")
      setSuccessMsg(`Issued code for ${contactName}: ${data.code} (Expires in 24h)`)
      setCopiedCode(data.code)
      if (data.invite_url) {
        const fullUrl = `${window.location.origin}${data.invite_url}`
        setIssuedInviteUrl(fullUrl)
      }
      loadData()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error issuing code")
    } finally {
      setActionLoading(false)
    }
  }

  async function handleUnlockContact(contactId: string, contactName: string) {
    setActionLoading(true)
    setError(null)
    try {
      const res = await fetch(`${FASTAPI_URL}/api/console/clients/${clientId}/portal/contacts/${contactId}/unlock`, {
        method: "POST",
      })
      if (!res.ok) throw new Error("Failed to unlock contact")
      setSuccessMsg(`Unlocked ${contactName}. Lockout cleared.`)
      loadData()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error unlocking contact")
    } finally {
      setActionLoading(false)
    }
  }

  async function handleRevokeCode(contactId: string) {
    setActionLoading(true)
    try {
      await fetch(`${FASTAPI_URL}/api/console/clients/${clientId}/portal/contacts/${contactId}/revoke-code`, {
        method: "POST",
      })
      setSuccessMsg("Pending login code revoked.")
      loadData()
    } catch {
      setError("Failed to revoke code.")
    } finally {
      setActionLoading(false)
    }
  }

  async function handleDeactivateContact(contactId: string) {
    if (!confirm("Are you sure you want to deactivate this contact? All their active sessions will be terminated.")) return
    setActionLoading(true)
    try {
      await fetch(`${FASTAPI_URL}/api/console/clients/${clientId}/portal/contacts/${contactId}/deactivate`, {
        method: "PATCH",
      })
      setSuccessMsg("Contact deactivated.")
      loadData()
    } catch {
      setError("Failed to deactivate contact.")
    } finally {
      setActionLoading(false)
    }
  }

  async function handleRevokeAllSessions() {
    if (!confirm("Kill switch: revoke ALL active portal sessions for this company? All users will be logged out.")) return
    setActionLoading(true)
    try {
      await fetch(`${FASTAPI_URL}/api/console/clients/${clientId}/portal/revoke-all-sessions`, {
        method: "POST",
      })
      setSuccessMsg("All company sessions revoked.")
      loadData()
    } catch {
      setError("Failed to revoke sessions.")
    } finally {
      setActionLoading(false)
    }
  }

  async function handleRotateLegacyCode() {
    if (!confirm("Rotate legacy company code? Any bookmarked guest links using the old code will immediately stop working.")) return
    setActionLoading(true)
    try {
      const res = await fetch(`${FASTAPI_URL}/api/console/clients/${clientId}/portal/rotate-legacy-code`, {
        method: "POST",
      })
      const data = await res.json()
      setSuccessMsg(`New legacy access code: ${data.new_access_code}`)
      loadData()
    } catch {
      setError("Failed to rotate legacy access code.")
    } finally {
      setActionLoading(false)
    }
  }

  return (
    <div className="flex flex-col gap-4 border-t border-border pt-4">
      {/* Header strip */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <KeyRound className="h-4 w-4 text-primary" strokeWidth={2.5} />
          <h4 className="text-xs font-black uppercase tracking-wider text-foreground">
            B2B Client Portal Access
          </h4>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setShowAuditLog(!showAuditLog)}
            className="flex items-center gap-1 rounded-[6px] border border-border bg-card px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-muted-foreground hover:bg-muted"
          >
            <History className="h-3 w-3" />
            Audit ({auditLog.length})
          </button>
          <button
            type="button"
            onClick={() => setShowAddContact(!showAddContact)}
            className="flex items-center gap-1 rounded-[6px] border border-border bg-black px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-white hover:bg-zinc-800"
          >
            <UserPlus className="h-3 w-3" />
            Add Contact
          </button>
        </div>
      </div>

      {/* Notifications */}
      {error && (
        <div className="rounded-[6px] border border-destructive/40 bg-destructive/10 p-2 text-xs font-semibold text-destructive">
          {error}
        </div>
      )}
      {successMsg && (
        <div className="flex flex-col gap-1.5 rounded-[6px] border border-emerald-500/40 bg-emerald-50 p-2 text-xs font-semibold text-emerald-800">
          <div className="flex items-center justify-between">
            <span>{successMsg}</span>
            {copiedCode && (
              <button
                type="button"
                onClick={() => {
                  navigator.clipboard.writeText(copiedCode)
                  setSuccessMsg(`Copied code ${copiedCode} to clipboard!`)
                }}
                className="ml-2 flex items-center gap-1 rounded bg-white px-2 py-0.5 text-[10px] font-black uppercase tracking-wider border border-border"
              >
                <Copy className="h-3 w-3" /> Copy Code
              </button>
            )}
          </div>
          {issuedInviteUrl && (
            <div className="flex items-center justify-between gap-2 border-t border-emerald-200/60 pt-1 text-[11px] text-emerald-900">
              <span className="truncate font-mono">{issuedInviteUrl}</span>
              <div className="flex items-center gap-1.5 shrink-0">
                <button
                  type="button"
                  onClick={() => {
                    navigator.clipboard.writeText(issuedInviteUrl)
                    setSuccessMsg("Copied one-time invite link to clipboard!")
                  }}
                  className="flex items-center gap-1 rounded bg-emerald-700 text-white px-2 py-0.5 text-[10px] font-black uppercase tracking-wider"
                >
                  <Copy className="h-3 w-3" /> Copy One-Time Invite Link
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setIssuedInviteUrl(null)
                    setCopiedCode(null)
                  }}
                  className="rounded border border-emerald-300 bg-white px-1.5 py-0.5 text-[10px] font-bold text-emerald-800 hover:bg-emerald-100"
                  title="Dismiss (link cannot be viewed again)"
                >
                  Dismiss
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Add Contact Form (Expandable) */}
      {showAddContact && (
        <form onSubmit={handleCreateContact} className="flex flex-col gap-3 rounded-[8px] border border-border bg-muted/30 p-3">
          <div className="text-[11px] font-black uppercase tracking-wider text-muted-foreground">
            New Company Contact
          </div>
          <div className="grid grid-cols-2 gap-2">
            <input
              type="text"
              required
              placeholder="Full Name *"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              className="rounded border border-border bg-white px-2.5 py-1.5 text-xs text-black"
            />
            <input
              type="text"
              placeholder="Title (e.g. Plant Manager)"
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              className="rounded border border-border bg-white px-2.5 py-1.5 text-xs text-black"
            />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <input
              type="email"
              placeholder="Work Email"
              value={newEmail}
              onChange={(e) => setNewEmail(e.target.value)}
              className="rounded border border-border bg-white px-2.5 py-1.5 text-xs text-black"
            />
            <input
              type="text"
              placeholder="WhatsApp Phone (e.g. 60109722730)"
              value={newPhone}
              onChange={(e) => setNewPhone(e.target.value)}
              className="rounded border border-border bg-white px-2.5 py-1.5 text-xs text-black"
            />
          </div>
          <div className="flex items-center justify-between pt-1">
            <div className="flex items-center gap-3">
              <label className="text-[11px] font-bold text-muted-foreground">Role:</label>
              <select
                value={newRole}
                onChange={(e) => setNewRole(e.target.value as any)}
                className="rounded border border-border bg-white px-2 py-1 text-xs"
              >
                <option value="evaluator">Evaluator (Technical)</option>
                <option value="admin">Admin (Full Team)</option>
                <option value="finance_viewer">Finance Viewer (Pricing only)</option>
              </select>
              <label className="flex items-center gap-1.5 text-[11px] font-bold text-muted-foreground cursor-pointer">
                <input
                  type="checkbox"
                  checked={newIsPrimary}
                  onChange={(e) => setNewIsPrimary(e.target.checked)}
                />
                Primary Contact
              </label>
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setShowAddContact(false)}
                className="rounded border border-border bg-card px-3 py-1 text-xs font-bold text-muted-foreground"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={actionLoading || !newName.trim()}
                className="rounded border border-border bg-black px-3 py-1 text-xs font-bold text-white hover:bg-zinc-800 disabled:opacity-50"
              >
                {actionLoading ? "Saving…" : "Save Contact"}
              </button>
            </div>
          </div>
        </form>
      )}

      {/* Contacts List */}
      {loading ? (
        <div className="flex items-center justify-center p-4">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      ) : contacts.length === 0 ? (
        <div className="rounded-[8px] border border-dashed border-border p-3 text-center text-xs text-muted-foreground">
          No contacts configured for this company yet. Click &quot;Add Contact&quot; to issue personal login codes.
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {contacts.map((c) => (
            <div
              key={c.id}
              className={`flex items-center justify-between rounded-[8px] border p-2.5 transition-colors ${
                c.status === "deactivated"
                  ? "border-border/50 bg-muted/20 opacity-60"
                  : "border-border bg-card shadow-[var(--shadow-xs)]"
              }`}
            >
              <div className="flex flex-col">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-xs font-bold text-foreground">{c.name}</span>
                  {c.is_primary && (
                    <span className="rounded bg-primary/20 px-1.5 py-0.2 text-[9px] font-black uppercase text-foreground">
                      Primary
                    </span>
                  )}
                  <span className="rounded border border-border bg-secondary px-1.5 py-0.2 text-[9px] font-black uppercase text-muted-foreground">
                    {c.portal_role.replace("_", " ")}
                  </span>
                  {c.rep_code_expires_at && new Date(c.rep_code_expires_at) > new Date() && (
                    <span className="rounded border border-amber-300 bg-amber-50 px-1.5 py-0.2 text-[9px] font-bold text-amber-700" title="Active rep-issued login code pending use">
                      Pending Code
                    </span>
                  )}
                  {c.invite_token_expires_at && new Date(c.invite_token_expires_at) > new Date() && (
                    <span className="rounded border border-blue-300 bg-blue-50 px-1.5 py-0.2 text-[9px] font-bold text-blue-700" title="Active 24h one-time invite link">
                      Invite Active
                    </span>
                  )}
                  {c.locked_until && new Date(c.locked_until) > new Date() && (
                    <span className="flex items-center gap-0.5 rounded border border-rose-300 bg-rose-50 px-1.5 py-0.2 text-[9px] font-bold text-rose-700">
                      <AlertTriangle className="h-2.5 w-2.5 text-rose-600" /> Locked ({c.failed_login_attempts ?? 5} attempts)
                    </span>
                  )}
                  {!c.email && (
                    <span className="rounded border border-zinc-200 bg-zinc-100 px-1.5 py-0.2 text-[9px] font-medium text-zinc-600" title="Contact has no email; login requires phone or invite link">
                      No Email
                    </span>
                  )}
                  {c.status === "deactivated" && (
                    <span className="rounded bg-destructive/10 px-1.5 py-0.2 text-[9px] font-bold text-destructive">
                      Deactivated
                    </span>
                  )}
                </div>
                <div className="text-[10px] text-muted-foreground">
                  {c.role_title && <span className="mr-2 font-medium">{c.role_title}</span>}
                  {c.email && <span className="mr-2">{c.email}</span>}
                  {c.whatsapp_number && <span>+{c.whatsapp_number}</span>}
                </div>
              </div>

              {/* Action buttons */}
              {c.status !== "deactivated" ? (
                <div className="flex items-center gap-1.5">
                  {c.locked_until && new Date(c.locked_until) > new Date() ? (
                    <button
                      type="button"
                      onClick={() => handleUnlockContact(c.id, c.name)}
                      disabled={actionLoading}
                      className="flex items-center gap-1 rounded border border-amber-300 bg-amber-100 px-2 py-1 text-[10px] font-black uppercase tracking-wider text-amber-800 hover:bg-amber-200"
                      title="Clear failed attempts and unlock contact"
                    >
                      <AlertTriangle className="h-3 w-3 text-amber-600" /> Unlock
                    </button>
                  ) : null}
                  <button
                    type="button"
                    onClick={() => handleIssueCode(c.id, c.name)}
                    disabled={actionLoading}
                    className="flex items-center gap-1 rounded border border-border bg-muted px-2 py-1 text-[10px] font-black uppercase tracking-wider hover:bg-secondary hover:text-foreground"
                  >
                    <KeyRound className="h-3 w-3" /> Issue Code
                  </button>
                  <button
                    type="button"
                    onClick={() => handleDeactivateContact(c.id)}
                    disabled={actionLoading}
                    className="rounded border border-border bg-muted px-2 py-1 text-[10px] font-bold text-destructive hover:bg-destructive/10"
                    title="Deactivate contact"
                  >
                    <Ban className="h-3 w-3" />
                  </button>
                </div>
              ) : (
                <span className="text-[10px] font-bold text-muted-foreground">Disabled</span>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Quote Requests Section */}
      <div className="rounded-[8px] border border-border bg-card p-3.5 flex flex-col gap-3">
        <div className="flex items-center justify-between border-b border-border pb-2">
          <span className="text-[11px] font-black uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
            <FileText className="h-3.5 w-3.5" /> Client Quotations ({quotes.length})
          </span>
          {quotes.filter((q) => q.status === "requested").length > 0 && (
            <span className="bg-amber-100 text-amber-800 text-[10px] font-bold px-2 py-0.5 rounded">
              {quotes.filter((q) => q.status === "requested").length} awaiting pricing
            </span>
          )}
        </div>

        {quotes.length === 0 ? (
          <p className="text-[11px] text-muted-foreground">No quotation requests from this client.</p>
        ) : (
          <div className="flex flex-col gap-2">
            {quotes.map((q) => (
              <div key={q.id} className="border border-border/80 bg-muted/20 p-2.5 rounded flex flex-col gap-1.5 text-xs">
                <div className="flex items-center justify-between">
                  <span className="font-bold">{q.property_name || "Robot unit"} (Qty: {q.quantity})</span>
                  <span className="text-[10px] uppercase font-black px-1.5 py-0.5 rounded border border-border">
                    {q.status}
                  </span>
                </div>
                {q.notes && <p className="text-[11px] text-muted-foreground">Client note: {q.notes}</p>}
                {q.quoted_amount != null && (
                  <p className="text-[11px] font-bold text-foreground">Quoted: {q.currency || "MYR"} {q.quoted_amount.toLocaleString()}</p>
                )}

                {q.status === "requested" && (
                  <button
                    type="button"
                    onClick={() => {
                      setQuoteToSend(q)
                      setSendAmount("")
                      setSendCustomerNote("")
                      setSendRepNotes("")
                    }}
                    className="self-start mt-1 flex items-center gap-1 rounded border border-border bg-black text-white px-2.5 py-1 text-[10px] font-black uppercase tracking-wider"
                  >
                    <Send className="h-2.5 w-2.5 text-primary" /> Issue Formal Pricing
                  </button>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Modal / form to send quote */}
        {quoteToSend && (
          <div className="border-t border-border pt-3 flex flex-col gap-2">
            <span className="font-bold text-xs">Issue Quote for {quoteToSend.property_name} (Qty: {quoteToSend.quantity})</span>
            <input
              type="number"
              placeholder="Total quoted amount (RM)"
              value={sendAmount}
              onChange={(e) => setSendAmount(e.target.value)}
              className="border border-border p-1.5 text-xs bg-white rounded"
            />
            <input
              type="text"
              placeholder="Client-visible terms / scope note"
              value={sendCustomerNote}
              onChange={(e) => setSendCustomerNote(e.target.value)}
              className="border border-border p-1.5 text-xs bg-white rounded"
            />
            <input
              type="text"
              placeholder="Internal sales notes (never shown to client)"
              value={sendRepNotes}
              onChange={(e) => setSendRepNotes(e.target.value)}
              className="border border-border p-1.5 text-xs bg-white rounded"
            />
            <div className="flex gap-2 pt-1">
              <button
                type="button"
                onClick={() => setQuoteToSend(null)}
                className="rounded border border-border px-2 py-1 text-[10px] font-bold text-muted-foreground"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={actionLoading || !sendAmount}
                onClick={async () => {
                  setActionLoading(true)
                  try {
                    const res = await fetch(`${FASTAPI_URL}/api/console/clients/${clientId}/quotes/${quoteToSend.id}/send`, {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({
                        quoted_amount: parseFloat(sendAmount),
                        customer_note: sendCustomerNote.trim() || null,
                        rep_notes: sendRepNotes.trim() || null,
                        valid_until: new Date(Date.now() + 30 * 86400000).toISOString(),
                      }),
                    })
                    if (res.ok) {
                      setQuoteToSend(null)
                      loadData()
                    }
                  } finally {
                    setActionLoading(false)
                  }
                }}
                className="rounded border border-black bg-black text-white px-3 py-1 text-[10px] font-black uppercase"
              >
                Send Quote
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Security Actions Toolbar */}
      <div className="flex flex-wrap items-center gap-2 pt-2 text-[10px]">
        <button
          type="button"
          onClick={handleRotateLegacyCode}
          disabled={actionLoading}
          className="flex items-center gap-1 rounded border border-border bg-card px-2.5 py-1 font-bold text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          <RefreshCw className="h-3 w-3" /> Rotate Legacy Access Code
        </button>
        <button
          type="button"
          onClick={handleRevokeAllSessions}
          disabled={actionLoading}
          className="flex items-center gap-1 rounded border border-destructive/30 bg-destructive/5 px-2.5 py-1 font-bold text-destructive hover:bg-destructive/10"
        >
          <ShieldAlert className="h-3 w-3" /> Revoke All Active Sessions
        </button>
      </div>

      {/* Audit Log Modal / Drawer View */}
      {showAuditLog && (
        <div className="rounded-[8px] border border-border bg-muted/20 p-3">
          <div className="mb-2 flex items-center justify-between border-b border-border pb-1.5">
            <span className="text-[11px] font-black uppercase tracking-wider text-muted-foreground">
              Recent Portal Audit Log (Last 50)
            </span>
            <button
              type="button"
              onClick={() => setShowAuditLog(false)}
              className="text-[10px] font-bold text-muted-foreground hover:text-foreground"
            >
              Close
            </button>
          </div>
          <div className="max-h-48 overflow-y-auto flex flex-col gap-1.5 text-[11px]">
            {auditLog.length === 0 ? (
              <span className="text-muted-foreground">No audit entries recorded yet.</span>
            ) : (
              auditLog.map((a) => (
                <div key={a.id} className="flex items-start justify-between border-b border-border/40 pb-1">
                  <div>
                    <span className="font-bold text-foreground mr-1.5">{a.action}</span>
                    <span className="text-[10px] text-muted-foreground">({a.object_type})</span>
                    {a.portal_contacts?.name && (
                      <span className="ml-1 text-[10px] text-muted-foreground">by {a.portal_contacts.name}</span>
                    )}
                  </div>
                  <span className="text-[9px] text-muted-foreground shrink-0">
                    {new Date(a.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  )
}
