"use client"

import { useRouter, usePathname } from "next/navigation"
import { useEffect, useRef } from "react"
import { gsap } from "gsap"
import { LogOut } from "lucide-react"
import type { PortalTab } from "@/lib/portal-types"
import "./portal-tab-nav.css"

// ─── Tab definitions ──────────────────────────────────────────────────────────

const PORTAL_TABS: Array<{ key: PortalTab; label: string }> = [
  { key: "overview",  label: "Overview"  },
  { key: "matches",   label: "Matches"   },
  { key: "catalog",   label: "Catalog"   },
  { key: "viewings",  label: "Viewings"  },
  { key: "activity",  label: "Activity"  },
  { key: "messages",  label: "Messages"  },
  { key: "profile",   label: "Preferences" },
]

// ─── Portal Tab Nav ───────────────────────────────────────────────────────────
// Uses the same GSAP wipe animation and CSS tokens as the agent TabNav
// (rect-tab, is-active, hover-block, label-stack, tab-label, tab-label-hover)
// — portal just adds horizontal-scroll for mobile.

function PortalTabNav({
  activeTab,
  onSelect,
}: {
  activeTab: PortalTab
  onSelect: (tab: PortalTab) => void
}) {
  const circleRefs = useRef<(HTMLSpanElement | null)[]>([])
  const tlRefs     = useRef<ReturnType<typeof gsap.timeline>[]>([])
  const activeTweenRefs = useRef<gsap.core.Tween[]>([])

  useEffect(() => {
    const layout = () => {
      circleRefs.current.forEach((rect, i) => {
        if (!rect?.parentElement) return
        const pill = rect.parentElement
        const h = pill.getBoundingClientRect().height

        gsap.set(rect, { scaleY: 0, transformOrigin: "bottom center" })

        const label      = pill.querySelector(".tab-label")      as HTMLElement | null
        const hoverLabel = pill.querySelector(".tab-label-hover") as HTMLElement | null
        if (label)      gsap.set(label,      { y: 0 })
        if (hoverLabel) gsap.set(hoverLabel, { y: h, opacity: 0 })

        tlRefs.current[i]?.kill()
        const tl = gsap.timeline({ paused: true })
        tl.to(rect, { scaleY: 1, duration: 0.18, ease: "power2.out", overwrite: "auto" }, 0)
        if (label)      tl.to(label,      { y: -h, duration: 0.18, ease: "power2.out", overwrite: "auto" }, 0)
        if (hoverLabel) tl.to(hoverLabel, { y: 0, opacity: 1, duration: 0.18, ease: "power2.out", overwrite: "auto" }, 0)
        tlRefs.current[i] = tl
      })
    }
    layout()
    window.addEventListener("resize", layout)
    return () => window.removeEventListener("resize", layout)
  }, [])

  useEffect(() => {
    PORTAL_TABS.forEach((tab, i) => {
      if (tab.key === activeTab) {
        tlRefs.current[i]?.seek(0).pause()
        activeTweenRefs.current[i]?.kill()
      }
    })
  }, [activeTab])

  const handleEnter = (i: number) => {
    if (PORTAL_TABS[i].key === activeTab) return
    const tl = tlRefs.current[i]
    if (!tl) return
    activeTweenRefs.current[i]?.kill()
    activeTweenRefs.current[i] = tl.tweenTo(tl.duration(), {
      duration: 0.15, ease: "power2.out", overwrite: "auto",
    })
  }

  const handleLeave = (i: number) => {
    const tl = tlRefs.current[i]
    if (!tl) return
    activeTweenRefs.current[i]?.kill()
    activeTweenRefs.current[i] = tl.tweenTo(0, {
      duration: 0.12, ease: "power2.out", overwrite: "auto",
    })
  }

  return (
    <nav className="portal-tab-nav" aria-label="Portal navigation">
      <ul className="portal-tab-list scrollbar-none" role="tablist">
        {PORTAL_TABS.map((tab, i) => (
          <li key={tab.key} role="none">
            <button
              type="button"
              role="tab"
              id={`portal-tab-${tab.key}`}
              aria-selected={activeTab === tab.key}
              className={`rect-tab${activeTab === tab.key ? " is-active" : ""}`}
              onMouseEnter={() => handleEnter(i)}
              onMouseLeave={() => handleLeave(i)}
              onClick={() => onSelect(tab.key)}
            >
              <span
                className="hover-block"
                aria-hidden="true"
                ref={(el) => { circleRefs.current[i] = el }}
              />
              <span className="label-stack">
                <span className="tab-label">{tab.label}</span>
                <span className="tab-label-hover" aria-hidden="true">{tab.label}</span>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </nav>
  )
}

// ─── Shell ────────────────────────────────────────────────────────────────────

export interface PortalShellProps {
  clientId: string
  clientName: string
  sessionInfo?: import("@/lib/portal-api").PortalMeData | null
  children: React.ReactNode
  /** Controlled from outside so the page can read/set ?tab= in URL */
  activeTab: PortalTab
  onTabChange: (tab: PortalTab) => void
}

export function PortalShell({
  clientName,
  sessionInfo,
  children,
  activeTab,
  onTabChange,
}: PortalShellProps) {
  const router   = useRouter()
  const pathname = usePathname()

  async function handleSignOut() {
    try {
      const { logoutPortal } = await import("@/lib/portal-api")
      await logoutPortal()
    } catch {
      // ignore
    }
    router.push("/portal")
  }

  const contactLabel = sessionInfo?.contact_name || clientName.split(" ")[0]
  const roleLabel = sessionInfo?.is_legacy
    ? "Guest (Legacy)"
    : sessionInfo?.portal_role?.replace("_", " ") || "Member"

  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* ── Fixed header ──────────────────────────────────────────────────── */}
      <header
        id="portal-header"
        className="fixed top-0 left-0 right-0 z-50 border-b border-border bg-card/95 backdrop-blur-sm shadow-[var(--shadow-xs)]"
      >
        {/* Top strip: logo + client name + logout */}
        <div className="flex h-14 items-center justify-between px-4 sm:px-6 gap-4">
          {/* Wordmark */}
          <div className="flex items-center gap-3 shrink-0">
            <div className="flex h-8 w-8 items-center justify-center border border-border bg-black">
              <span className="text-primary text-sm font-black">P</span>
            </div>
            <div className="hidden sm:block">
              <div className="font-sans text-sm font-bold leading-none tracking-tight">
                PIPELINE<span className="text-muted-foreground">.EV</span>
              </div>
              <div className="text-[10px] font-black uppercase tracking-wider text-muted-foreground leading-tight mt-0.5">
                Client Portal v2
              </div>
            </div>
          </div>

          {/* Client & Role pill */}
          <div className="hidden sm:flex items-center gap-2">
            <span className="inline-flex items-center border border-border bg-secondary px-3 py-1 text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
              {contactLabel}
            </span>
            <span className="inline-flex items-center border border-border bg-primary/20 px-2.5 py-0.5 text-[10px] font-black uppercase tracking-wider text-foreground">
              {roleLabel}
            </span>
          </div>

          {/* Logout */}
          <button
            id="portal-signout-btn"
            onClick={handleSignOut}
            className="ml-auto flex items-center gap-2 border border-border bg-muted px-3 py-1.5 text-[11px] font-black uppercase tracking-wider text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors shrink-0"
          >
            <LogOut className="h-3.5 w-3.5" strokeWidth={2.5} />
            <span className="hidden sm:inline">Sign out</span>
          </button>
        </div>

        {/* Legacy Warning Banner */}
        {sessionInfo?.is_legacy && (
          <div className="border-t border-amber-300 bg-amber-50 px-4 py-2 text-xs font-semibold text-amber-900 flex items-center justify-between">
            <span>
              ⚠️ Viewing via legacy company code. Read-only mode: pricing and team management are disabled. Ask your administrator for a personal login code.
            </span>
          </div>
        )}

        {/* Tab bar — full-width, horizontally scrollable on mobile */}
        <div className="border-t border-border bg-card overflow-x-auto scrollbar-none">
          <PortalTabNav
            activeTab={activeTab}
            onSelect={(tab) => {
              onTabChange(tab)
              // Push to URL so refresh/back/forward work
              const url = new URL(pathname, window.location.origin)
              url.searchParams.set("tab", tab)
              router.replace(url.pathname + url.search, { scroll: false })
            }}
          />
        </div>
      </header>

      {/* Content — padded to clear fixed header (h-14 top bar + ~44px tab bar) */}
      <main className="pt-[102px] min-h-screen" id="portal-content">
        {children}
      </main>
    </div>
  )
}
