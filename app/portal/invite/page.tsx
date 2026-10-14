"use client"

import { useEffect, useState, Suspense } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import Head from "next/head"
import { Loader2, AlertCircle } from "lucide-react"

function InviteContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    // 1. Prioritize URL fragment (#token=...) to keep tokens out of server logs & Referers
    let tokenValue = ""
    if (typeof window !== "undefined" && window.location.hash) {
      const hashParams = new URLSearchParams(window.location.hash.replace(/^#/, ""))
      tokenValue = hashParams.get("token") || ""
      // Scrub token from hash in browser history immediately
      if (tokenValue) {
        window.history.replaceState(null, "", window.location.pathname)
      }
    }

    // 2. Fallback to query parameter (?token=...)
    if (!tokenValue) {
      tokenValue = searchParams.get("token") || ""
    }

    if (!tokenValue) {
      setError("No invite token provided in link.")
      return
    }

    async function redeemInvite(token: string) {
      try {
        const res = await fetch("/api/portal/auth/verify-invite", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token }),
        })
        const data = await res.json()
        if (!res.ok) {
          setError(data.error || "Invite link is invalid or has expired.")
          return
        }
        // Redirect without token in redirect URL
        router.push(`/portal/${data.client_id}`)
      } catch {
        setError("Network error validating invite. Please try again.")
      }
    }

    redeemInvite(tokenValue)
  }, [searchParams, router])

  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background px-4">
        <meta name="referrer" content="no-referrer" />
        <div className="w-full max-w-md rounded-[8px] border border-destructive/40 bg-card p-6 text-center shadow-[var(--shadow-md)]">
          <AlertCircle className="mx-auto h-8 w-8 text-destructive mb-3" />
          <h2 className="text-base font-bold text-foreground mb-1">Invite Link Invalid</h2>
          <p className="text-xs text-muted-foreground mb-4">{error}</p>
          <a
            href="/portal"
            className="inline-flex items-center justify-center rounded-[6px] border border-border bg-black px-4 py-2 text-xs font-black uppercase tracking-wider text-white hover:bg-zinc-800"
          >
            Go to Portal Login
          </a>
        </div>
      </div>
    )
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <meta name="referrer" content="no-referrer" />
      <div className="flex flex-col items-center gap-3">
        <Loader2 className="h-6 w-6 animate-spin text-primary" />
        <p className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
          Authenticating invite…
        </p>
      </div>
    </div>
  )
}

export default function PortalInvitePage() {
  return (
    <>
      <meta name="referrer" content="no-referrer" />
      <Suspense
        fallback={
          <div className="flex min-h-screen items-center justify-center bg-background">
            <meta name="referrer" content="no-referrer" />
            <Loader2 className="h-6 w-6 animate-spin text-primary" />
          </div>
        }
      >
        <InviteContent />
      </Suspense>
    </>
  )
}
