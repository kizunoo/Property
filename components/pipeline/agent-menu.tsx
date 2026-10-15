"use client"

import { useEffect, useRef, useState } from "react"
import { ChevronDown, LogOut, UserCircle2, X } from "lucide-react"
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet"
import type { Agent } from "@/lib/pipeline-data"

// ─── Profile drawer ───────────────────────────────────────────────────────────
function ProfileDrawer({
  open,
  onClose,
  agent,
}: {
  open: boolean
  onClose: () => void
  agent: Agent | null
}) {
  const displayName     = agent?.name     ?? "All Agents"
  const displayInitials = agent?.initials ?? "EV"
  const displayRole     = agent?.role     ?? "Broker View"
  const displayEmail    = agent ? `${agent.initials.toLowerCase().replace(". ", ".")}.pipeline.ev` : "broker@pipeline.ev"

  return (
    <Sheet open={open} onOpenChange={(o) => { if (!o) onClose() }}>
      <SheetContent
        side="right"
        className="flex w-full flex-col gap-0 overflow-y-auto border-l border-neutral-200 bg-white p-0 shadow-[0px_8px_32px_rgba(0,0,0,0.12)] sm:max-w-[400px]"
      >
        <SheetTitle className="sr-only">Agent Profile</SheetTitle>

        {/* Header */}
        <div className="flex items-start justify-between gap-4 border-b border-neutral-200 bg-black p-5 sm:p-6">
          <div className="flex items-center gap-4">
            <div className="flex h-16 w-16 items-center justify-center border-4 border-primary bg-primary text-2xl font-black text-black">
              {displayInitials}
            </div>
            <div>
              <div className="text-lg font-black leading-tight text-white">{displayName}</div>
              <div className="mt-0.5 text-xs font-black uppercase tracking-wider text-primary">{displayRole}</div>
              <div className="mt-1 font-mono text-[11px] text-white/60">{displayEmail}</div>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="shrink-0 border-2 border-white/40 p-1.5 text-white transition-colors hover:border-white hover:bg-white hover:text-black"
            aria-label="Close"
          >
            <X className="h-4 w-4" strokeWidth={2.5} />
          </button>
        </div>

        {/* Body */}
        <div className="flex flex-col gap-5 p-5 sm:p-6">
          <div className="grid grid-cols-2 gap-3">
            {[
              { label: "Region",       value: "Kuala Lumpur Metro" },
              { label: "View Mode",    value: agent ? "Agent View" : "Broker View" },
            ].map(({ label, value }) => (
              <div key={label} className="border border-neutral-200 p-4 shadow-[0px_2px_8px_rgba(0,0,0,0.08)]">
                <div className="text-[10px] font-black uppercase tracking-wider text-muted-foreground">{label}</div>
                <div className="mt-1 font-mono text-xl font-black leading-tight">{value}</div>
              </div>
            ))}
          </div>

          {/* Agent ID */}
          <div className="border border-neutral-200 bg-black p-4">
            <div className="text-[10px] font-black uppercase tracking-wider text-white/60">View Context</div>
            <div className="mt-1 font-mono text-sm font-black text-primary">
              {agent ? `AGENT — ${agent.initials}` : "BROKER — ALL AGENTS"}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="mt-auto border-t border-neutral-200 p-5 sm:p-6">
          <button
            type="button"
            onClick={onClose}
            className="w-full border border-neutral-200 bg-white py-3 text-sm font-black uppercase tracking-wider transition-colors hover:bg-black hover:text-white"
          >
            Close Profile
          </button>
        </div>
      </SheetContent>
    </Sheet>
  )
}

// ─── Logout confirmation modal ────────────────────────────────────────────────
function LogoutModal({
  open,
  onClose,
  onConfirm,
  agent,
}: {
  open: boolean
  onClose: () => void
  onConfirm: () => void
  agent: Agent | null
}) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center">
      {/* Overlay */}
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      {/* Dialog */}
      <div className="relative border border-neutral-200 bg-white shadow-[0px_4px_16px_rgba(0,0,0,0.10)] w-full max-w-sm mx-4">
        <div className="border-b border-neutral-200 bg-black px-5 py-4">
          <div className="flex items-center gap-2">
            <LogOut className="h-4 w-4 text-primary" strokeWidth={2.5} />
            <span className="text-sm font-black uppercase tracking-wider text-white">Confirm Log Out</span>
          </div>
        </div>
        <div className="p-5">
          <p className="text-sm font-bold text-muted-foreground leading-relaxed">
            You are about to end your session
            {agent ? <> as <span className="font-black text-black">{agent.name}</span></> : ""}. Any unsaved actions will be lost.
          </p>
          <div className="mt-5 flex gap-3">
            <button
              type="button"
              onClick={onConfirm}
              className="flex-1 border border-neutral-200 bg-black py-3 text-sm font-black uppercase tracking-wider text-white shadow-[0px_2px_8px_rgba(0,0,0,0.08)] transition-all hover:shadow-[0px_1px_3px_rgba(0,0,0,0.06)]"
            >
              Log Out
            </button>
            <button
              type="button"
              onClick={onClose}
              className="flex-1 border border-neutral-200 bg-white py-3 text-sm font-black uppercase tracking-wider transition-colors hover:bg-black hover:text-white"
            >
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── Agent Selector dropdown ──────────────────────────────────────────────────
export function AgentSelector({
  selectedAgentId,
  onChange,
}: {
  selectedAgentId: string | null
  onChange: (agentId: string | null) => void
}) {
  const [agents, setAgents] = useState<Agent[]>([])
  const [currentUser, setCurrentUser] = useState<{ id: string; name: string; role: string; is_admin: boolean } | null>(null)
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    // 1. Fetch current agent identity
    fetch("/api/agent/me")
      .then((r) => r.ok ? r.json() : null)
      .then((me) => {
        if (me) {
          setCurrentUser(me)
          // Only administrators may query the full agency directory
          if (me.is_admin || me.role === "admin") {
            fetch("/api/agents")
              .then((r) => r.json())
              .then((data) => { if (Array.isArray(data)) setAgents(data) })
              .catch(() => {})
          }
        }
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false)
    }
    document.addEventListener("mousedown", handleClickOutside)
    document.addEventListener("keydown", handleKeyDown)
    return () => {
      document.removeEventListener("mousedown", handleClickOutside)
      document.removeEventListener("keydown", handleKeyDown)
    }
  }, [])

  // For non-admin agents: show their own name and hide the selector
  if (currentUser && !currentUser.is_admin) {
    const initials = currentUser.name ? currentUser.name.split(" ").map((n: string) => n[0]).join("").slice(0, 2).toUpperCase() : "AG"
    return (
      <div className="flex items-center gap-3 border border-neutral-200 bg-white px-3 py-2 text-left shadow-[0px_2px_8px_rgba(0,0,0,0.08)] sm:px-4">
        <div className="flex h-8 w-8 items-center justify-center border border-neutral-200 bg-primary text-xs font-black shrink-0">
          {initials}
        </div>
        <div className="flex flex-col items-start min-w-0">
          <span className="text-xs font-black uppercase tracking-wider sm:text-sm leading-tight truncate">
            {currentUser.name}
          </span>
          <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider leading-tight">
            Assigned Deals Only
          </span>
        </div>
      </div>
    )
  }

  const current = selectedAgentId ? agents.find((a) => a.id === selectedAgentId) : null
  const displayLabel = current
    ? `${current.initials} — ${current.name}`
    : "All Sales Reps"

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        id="agent-selector-btn"
        onClick={() => setOpen((prev) => !prev)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className="flex items-center gap-3 border border-neutral-200 bg-white px-3 py-2 text-left shadow-[0px_2px_8px_rgba(0,0,0,0.08)] transition-shadow hover:shadow-[0px_2px_12px_rgba(0,0,0,0.12)] sm:px-4"
      >
        <div className="flex h-8 w-8 items-center justify-center border border-neutral-200 bg-primary text-xs font-black shrink-0">
          {current?.initials ?? "EV"}
        </div>
        <div className="flex flex-col items-start min-w-0">
          <span className="text-xs font-black uppercase tracking-wider sm:text-sm leading-tight truncate">
            {displayLabel}
          </span>
          {current && (
            <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider leading-tight">
              {current.role}
            </span>
          )}
          {!current && (
            <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider leading-tight">
              All Reps View
            </span>
          )}
        </div>
        <ChevronDown
          className={`h-4 w-4 shrink-0 transition-transform ${open ? "rotate-180" : ""}`}
          strokeWidth={3}
        />
      </button>

      {open && (
        <div
          role="listbox"
          aria-label="Select sales rep"
          className="absolute right-0 top-full z-20 mt-2 min-w-[220px] border border-neutral-200 bg-white shadow-[0px_4px_16px_rgba(0,0,0,0.12)]"
        >
          {/* All Reps View option */}
          <button
            type="button"
            role="option"
            aria-selected={selectedAgentId === null}
            onClick={() => { onChange(null); setOpen(false) }}
            className={`flex w-full items-center gap-3 border-b border-neutral-100 px-4 py-3 text-left transition-colors hover:bg-black hover:text-white ${selectedAgentId === null ? "bg-primary/10" : ""}`}
          >
            <div className="flex h-7 w-7 items-center justify-center bg-black text-primary text-[10px] font-black shrink-0">
              EV
            </div>
            <div className="flex flex-col items-start">
              <span className="text-xs font-black uppercase tracking-wider">All Sales Reps</span>
              <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider group-hover:text-white">All Reps View</span>
            </div>
          </button>

          {/* Per-agent options */}
          {agents.map((agent, i) => (
            <button
              key={agent.id}
              type="button"
              role="option"
              aria-selected={selectedAgentId === agent.id}
              onClick={() => { onChange(agent.id); setOpen(false) }}
              className={`flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-black hover:text-white ${i < agents.length - 1 ? "border-b border-neutral-100" : ""} ${selectedAgentId === agent.id ? "bg-primary/10" : ""}`}
            >
              <div className="flex h-7 w-7 items-center justify-center bg-neutral-900 text-primary text-[10px] font-black shrink-0">
                {agent.initials}
              </div>
              <div className="flex flex-col items-start">
                <span className="text-xs font-black uppercase tracking-wider">{agent.name}</span>
                <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">{agent.role}</span>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Agent menu (Profile + Logout) ────────────────────────────────────────────
interface AgentMenuProps {
  onLogout?: () => void
  selectedAgent: Agent | null
}

export function AgentMenu({ onLogout, selectedAgent }: AgentMenuProps) {
  const [open,         setOpen]         = useState(false)
  const [profileOpen,  setProfileOpen]  = useState(false)
  const [logoutOpen,   setLogoutOpen]   = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false)
      }
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false)
    }
    document.addEventListener("mousedown", handleClickOutside)
    document.addEventListener("keydown", handleKeyDown)
    return () => {
      document.removeEventListener("mousedown", handleClickOutside)
      document.removeEventListener("keydown", handleKeyDown)
    }
  }, [])

  function handleProfile() {
    setOpen(false)
    setProfileOpen(true)
  }

  function handleLogoutClick() {
    setOpen(false)
    setLogoutOpen(true)
  }

  function handleLogoutConfirm() {
    setLogoutOpen(false)
    onLogout?.()
  }

  return (
    <>
      <div ref={containerRef} className="relative">
        <button
          type="button"
          id="agent-menu-btn"
          onClick={() => setOpen((prev) => !prev)}
          aria-haspopup="menu"
          aria-expanded={open}
          className="flex h-10 w-10 items-center justify-center border border-neutral-200 bg-white shadow-[0px_2px_8px_rgba(0,0,0,0.08)] transition-shadow hover:shadow-[0px_2px_12px_rgba(0,0,0,0.12)]"
          title="Agent profile & options"
        >
          <UserCircle2 className="h-5 w-5" strokeWidth={2} />
        </button>

        {open ? (
          <div
            role="menu"
            className="absolute right-0 top-full z-20 mt-3 w-48 border border-neutral-200 bg-white shadow-[0px_2px_8px_rgba(0,0,0,0.08)]"
          >
            <button
              type="button"
              role="menuitem"
              onClick={handleProfile}
              className="flex w-full items-center gap-2.5 border-b border-neutral-200 px-4 py-3 text-left text-xs font-black uppercase tracking-wider transition-colors hover:bg-black hover:text-white sm:text-sm"
            >
              <UserCircle2 className="h-4 w-4" strokeWidth={2.5} />
              Profile
            </button>
            <button
              type="button"
              role="menuitem"
              onClick={handleLogoutClick}
              className="flex w-full items-center gap-2.5 px-4 py-3 text-left text-xs font-black uppercase tracking-wider transition-colors hover:bg-black hover:text-white sm:text-sm"
            >
              <LogOut className="h-4 w-4" strokeWidth={2.5} />
              Log Out
            </button>
          </div>
        ) : null}
      </div>

      {/* Modals — rendered outside the dropdown container */}
      <ProfileDrawer open={profileOpen} onClose={() => setProfileOpen(false)} agent={selectedAgent} />
      <LogoutModal
        open={logoutOpen}
        onClose={() => setLogoutOpen(false)}
        onConfirm={handleLogoutConfirm}
        agent={selectedAgent}
      />
    </>
  )
}

