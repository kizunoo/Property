import type { ReactNode } from "react"
import type { Metadata } from "next"

export const metadata: Metadata = {
  title: "Client Portal — PIPELINE.EV",
  description: "Your personalised robotics portal — secure client access",
}

export default function PortalLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* Portal-specific top bar — completely separate from agent dashboard */}
      <header className="fixed top-0 left-0 right-0 z-50 h-14 border-b border-border bg-card/95 backdrop-blur-sm flex items-center justify-between px-6 shadow-[var(--shadow-xs)]">
        <div className="flex items-center gap-3">
          {/* Wordmark block */}
          <div className="flex h-8 w-8 items-center justify-center border border-border bg-black">
            <span className="text-primary text-sm font-black">P</span>
          </div>
          <div>
            <div className="font-sans text-sm font-bold leading-none tracking-tight">
              PIPELINE<span className="text-muted-foreground">.EV</span>
            </div>
            <div className="text-[10px] font-black uppercase tracking-wider text-muted-foreground leading-tight mt-0.5">
              Client Portal
            </div>
          </div>
        </div>
        <span className="inline-flex items-center gap-1.5 border border-border bg-muted px-3 py-1 text-[10px] font-black uppercase tracking-wider text-muted-foreground">
          Secure access
        </span>
      </header>

      {/* Page content starts below fixed header */}
      <div className="pt-14">{children}</div>
    </div>
  )
}
