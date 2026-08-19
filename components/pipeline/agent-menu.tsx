"use client"

import { useEffect, useRef, useState } from "react"
import { ChevronDown, LogOut, UserCircle2, X } from "lucide-react"
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet"

// ─── Static agent data ────────────────────────────────────────────────────────
const AGENT = {
  initials: "RD",
  name:     "R. Delgado",
  role:     "Senior Agent",
  email:    "r.delgado@pipeline.ev",
  region:   "Kuala Lumpur Metro",
  since:    "2019",
  closedDeals: 47,
  totalVolume: "$128M",
}

// ─── Profile drawer ───────────────────────────────────────────────────────────
function ProfileDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <Sheet open={open} onOpenChange={(o) => { if (!o) onClose() }}>
      <SheetContent
        side="right"
        className="flex w-full flex-col gap-0 overflow-y-auto border-l-4 border-black bg-white p-0 shadow-[-8px_0px_0px_0px_rgba(0,0,0,1)] sm:max-w-[400px]"
      >
        <SheetTitle className="sr-only">Agent Profile</SheetTitle>

        {/* Header */}
        <div className="flex items-start justify-between gap-4 border-b-4 border-black bg-black p-5 sm:p-6">
          <div className="flex items-center gap-4">
            <div className="flex h-16 w-16 items-center justify-center border-4 border-primary bg-primary text-2xl font-black text-black">
              {AGENT.initials}
            </div>
            <div>
              <div className="text-lg font-black leading-tight text-white">{AGENT.name}</div>
              <div className="mt-0.5 text-xs font-black uppercase tracking-wider text-primary">{AGENT.role}</div>
              <div className="mt-1 font-mono text-[11px] text-white/60">{AGENT.email}</div>
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
          {/* Stats */}
          <div className="grid grid-cols-2 gap-3">
            {[
              { label: "Region",       value: AGENT.region },
              { label: "Agent Since",  value: AGENT.since },
              { label: "Closed Deals", value: String(AGENT.closedDeals) },
              { label: "Total Volume", value: AGENT.totalVolume },
            ].map(({ label, value }) => (
              <div key={label} className="border-4 border-black p-4 shadow-[4px_4px_0px_0px_rgba(0,0,0,1)]">
                <div className="text-[10px] font-black uppercase tracking-wider text-muted-foreground">{label}</div>
                <div className="mt-1 font-mono text-xl font-black leading-tight">{value}</div>
              </div>
            ))}
          </div>

          {/* Identifier */}
          <div className="border-4 border-black bg-black p-4">
            <div className="text-[10px] font-black uppercase tracking-wider text-white/60">Agent ID</div>
            <div className="mt-1 font-mono text-sm font-black text-primary">AGT-2019-KL-047</div>
          </div>
        </div>

        {/* Footer */}
        <div className="mt-auto border-t-4 border-black p-5 sm:p-6">
          <button
            type="button"
            onClick={onClose}
            className="w-full border-4 border-black bg-white py-3 text-sm font-black uppercase tracking-wider transition-colors hover:bg-black hover:text-white"
          >
            Close Profile
          </button>
        </div>
      </SheetContent>
    </Sheet>
  )
}

// ─── Logout confirmation modal ────────────────────────────────────────────────
function LogoutModal({ open, onClose, onConfirm }: { open: boolean; onClose: () => void; onConfirm: () => void }) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center">
      {/* Overlay */}
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      {/* Dialog */}
      <div className="relative border-4 border-black bg-white shadow-[8px_8px_0px_0px_rgba(0,0,0,1)] w-full max-w-sm mx-4">
        <div className="border-b-4 border-black bg-black px-5 py-4">
          <div className="flex items-center gap-2">
            <LogOut className="h-4 w-4 text-primary" strokeWidth={2.5} />
            <span className="text-sm font-black uppercase tracking-wider text-white">Confirm Log Out</span>
          </div>
        </div>
        <div className="p-5">
          <p className="text-sm font-bold text-muted-foreground leading-relaxed">
            You are about to end your session as <span className="font-black text-black">{AGENT.name}</span>. Any unsaved actions will be lost.
          </p>
          <div className="mt-5 flex gap-3">
            <button
              type="button"
              onClick={onConfirm}
              className="flex-1 border-4 border-black bg-black py-3 text-sm font-black uppercase tracking-wider text-white shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] transition-all hover:translate-x-0.5 hover:translate-y-0.5 hover:shadow-none"
            >
              Log Out
            </button>
            <button
              type="button"
              onClick={onClose}
              className="flex-1 border-4 border-black bg-white py-3 text-sm font-black uppercase tracking-wider transition-colors hover:bg-black hover:text-white"
            >
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── Agent menu ───────────────────────────────────────────────────────────────
interface AgentMenuProps {
  onLogout?: () => void
}

export function AgentMenu({ onLogout }: AgentMenuProps) {
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
          onClick={() => setOpen((prev) => !prev)}
          aria-haspopup="menu"
          aria-expanded={open}
          className="flex items-center gap-3 border-2 border-black bg-white px-3 py-2 text-left shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] transition-transform hover:-translate-x-0.5 hover:-translate-y-0.5 hover:shadow-[6px_6px_0px_0px_rgba(0,0,0,1)] sm:px-4"
        >
          <div className="flex h-8 w-8 items-center justify-center border-2 border-black bg-primary text-xs font-black">
            {AGENT.initials}
          </div>
          <div className="text-xs font-black uppercase tracking-wider sm:text-sm">
            {AGENT.name} — {AGENT.role}
          </div>
          <ChevronDown
            className={`h-4 w-4 shrink-0 transition-transform ${open ? "rotate-180" : ""}`}
            strokeWidth={3}
          />
        </button>

        {open ? (
          <div
            role="menu"
            className="absolute right-0 top-full z-20 mt-3 w-56 border-4 border-black bg-white shadow-[6px_6px_0px_0px_rgba(0,0,0,1)]"
          >
            <button
              type="button"
              role="menuitem"
              onClick={handleProfile}
              className="flex w-full items-center gap-2.5 border-b-2 border-black px-4 py-3 text-left text-xs font-black uppercase tracking-wider transition-colors hover:bg-black hover:text-white sm:text-sm"
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
      <ProfileDrawer open={profileOpen} onClose={() => setProfileOpen(false)} />
      <LogoutModal
        open={logoutOpen}
        onClose={() => setLogoutOpen(false)}
        onConfirm={handleLogoutConfirm}
      />
    </>
  )
}
