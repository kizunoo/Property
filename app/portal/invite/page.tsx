"use client"

import { useEffect, useState, Suspense } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { Loader2, AlertCircle } from "lucide-react"

function InviteContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const token = searchParams.get("token")
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!token) {
      setError("No invite token provided in link.")
      return
    }

    async function redeemInvite() {
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
        router.push(`/portal/${data.client_id}`)
      } catch {
        setError("Network error validating invite. Please try again.")
      }
    }

    redeemInvite()
  }, [token, router])

  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background px-4">
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
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center bg-background">
          <Loader2 className="h-6 w-6 animate-spin text-primary" />
        </div>
      }
    >
      <InviteContent />
    </Suspense>
  )
}
