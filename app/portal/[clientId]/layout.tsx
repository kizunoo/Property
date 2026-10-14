import type { ReactNode } from "react"
import type { Metadata } from "next"
import { Toaster } from "@/components/ui/toaster"

export const metadata: Metadata = {
  title: "Your Portal — PIPELINE.EV",
  description: "Your personalised robotics recommendations — secure client access",
}

/**
 * Portal shell layout — wraps /portal/[clientId] only.
 * The root /portal layout stays minimal (login page needs no tab bar / shell).
 * The actual shell chrome (header, tabs, logout) is rendered in PortalShell
 * which is a client component in the page itself so it can read sessionStorage.
 */
export default function ClientPortalLayout({ children }: { children: ReactNode }) {
  return (
    <>
      {children}
      <Toaster />
    </>
  )
}
