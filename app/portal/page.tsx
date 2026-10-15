"use client"

import { useState, useRef, useEffect } from "react"
import { useRouter } from "next/navigation"
import { ArrowRight, KeyRound, Mail, ShieldCheck, AlertTriangle } from "lucide-react"

export default function PortalLoginPage() {
  const router = useRouter()
  const [identifier, setIdentifier] = useState("")
  const [code, setCode] = useState("")
  const [isLegacyMode, setIsLegacyMode] = useState(false)
  const [loading, setLoading] = useState(false)
  const [requestingCode, setRequestingCode] = useState(false)
  const [infoMessage, setInfoMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    inputRef.current?.focus()
  }, [isLegacyMode])

  async function handleRequestCode(e: React.MouseEvent) {
    e.preventDefault()
    const trimmedId = identifier.trim()
    if (!trimmedId) {
      setError("Please enter your email or WhatsApp number first.")
      return
    }

    setRequestingCode(true)
    setError(null)
    setInfoMessage(null)

    try {
      const res = await fetch("/api/portal/auth/request-code", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ identifier: trimmedId }),
      })
      const data = await res.json()
      setInfoMessage(data.message || "If the contact exists, a login code has been sent.")
    } catch {
      setError("Connection error requesting code. Please try again.")
    } finally {
      setRequestingCode(false)
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setInfoMessage(null)

    if (isLegacyMode) {
      const trimmedCode = code.trim().toUpperCase()
      if (!trimmedCode) return
      setLoading(true)

      try {
        const res = await fetch("/api/portal/auth/legacy-login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ code: trimmedCode, access_code: trimmedCode }),
        })
        const data = await res.json()
        if (!res.ok) {
          setError(data.error ?? "Invalid access code or legacy logins disabled.")
          return
        }
        const targetId = data.client_id || data.company?.id
        router.push(`/portal/${targetId}`)
      } catch {
        setError("Connection error. Please try again.")
      } finally {
        setLoading(false)
      }
      return
    }

    // Personal Single-Use Login Code Mode
    const trimmedId = identifier.trim()
    const trimmedCode = code.trim().toUpperCase()
    if (!trimmedId || !trimmedCode) {
      setError("Please enter both your identifier and single-use login code.")
      return
    }

    setLoading(true)
    try {
      const res = await fetch("/api/portal/auth/verify-code", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ identifier: trimmedId, code: trimmedCode }),
      })
      const data = await res.json()
      if (!res.ok) {
        setError(data.error ?? "Invalid login code. Please verify and try again.")
        return
      }
      const targetId = data.client_id || data.company?.id
      router.push(`/portal/${targetId}`)
    } catch {
      setError("Connection error. Please try again.")
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="stripes-diagonal relative flex min-h-[calc(100vh-56px)] items-center justify-center overflow-hidden bg-background px-4 py-10">
      <div className="relative z-10 w-full max-w-md">
        {/* Logo lockup */}
        <div className="mb-6 flex items-center justify-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center border border-border bg-black">
            <span className="text-lg font-black text-primary">P</span>
          </div>
          <div>
            <div className="font-sans text-2xl font-bold leading-none tracking-tight">
              PIPELINE<span className="text-muted-foreground">.EV</span>
            </div>
            <div className="text-[11px] font-black uppercase tracking-wider text-muted-foreground">
              Client Portal v2
            </div>
          </div>
        </div>

        {/* Card */}
        <form
          onSubmit={handleSubmit}
          className="flex flex-col gap-5 border border-border bg-card p-6 shadow-[var(--shadow-md)] sm:p-8"
        >
          {/* Header strip */}
          <div className="border-b border-border pb-4">
            <span className="inline-flex items-center gap-1.5 border border-border bg-primary px-3 py-1 text-xs font-black uppercase tracking-wider">
              <ShieldCheck className="h-3.5 w-3.5" strokeWidth={3} />
              B2B Secure Access
            </span>
            <h1 className="mt-3 text-2xl font-bold tracking-tight sm:text-3xl">
              {isLegacyMode ? "Company Access" : "Sign in to Portal"}
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              {isLegacyMode
                ? "Enter your company's shared access code (legacy fallback)."
                : "Enter your work identifier and rep-issued single-use code."}
            </p>
          </div>

          {infoMessage && (
            <div className="border border-border bg-secondary p-3 text-xs font-semibold text-foreground">
              {infoMessage}
            </div>
          )}

          {!isLegacyMode ? (
            <>
              {/* Identifier Input */}
              <label className="flex flex-col gap-2">
                <span className="flex items-center gap-2 text-xs font-black uppercase tracking-wider">
                  <Mail className="h-4 w-4" strokeWidth={2.5} />
                  Work Email or WhatsApp
                </span>
                <input
                  id="portal-identifier"
                  ref={inputRef}
                  type="text"
                  value={identifier}
                  onChange={(e) => {
                    setIdentifier(e.target.value)
                    setError(null)
                  }}
                  placeholder="name@company.com or 601XXXXXXXX"
                  autoComplete="username"
                  spellCheck={false}
                  className="border border-border bg-white px-3 py-3 text-sm font-semibold text-black placeholder:text-muted-foreground focus:outline-none focus-visible:border-primary"
                />
              </label>

              {/* Single-Use Code Input */}
              <label className="flex flex-col gap-2">
                <div className="flex items-center justify-between">
                  <span className="flex items-center gap-2 text-xs font-black uppercase tracking-wider">
                    <KeyRound className="h-4 w-4" strokeWidth={2.5} />
                    Single-Use Login Code
                  </span>
                  <button
                    type="button"
                    onClick={handleRequestCode}
                    disabled={requestingCode || !identifier.trim()}
                    className="text-[11px] font-bold text-muted-foreground underline decoration-primary underline-offset-2 hover:text-foreground disabled:opacity-50"
                  >
                    {requestingCode ? "Sending…" : "Request code"}
                  </button>
                </div>
                <input
                  id="portal-login-code"
                  type="text"
                  value={code}
                  onChange={(e) => {
                    setCode(e.target.value.toUpperCase())
                    setError(null)
                  }}
                  placeholder="XXXXXX"
                  maxLength={10}
                  autoComplete="one-time-code"
                  spellCheck={false}
                  className="border border-border bg-white px-3 py-3 font-mono text-sm font-bold tracking-widest text-black placeholder:text-muted-foreground focus:outline-none focus-visible:border-primary uppercase"
                />
              </label>
            </>
          ) : (
            <label className="flex flex-col gap-2">
              <span className="flex items-center gap-2 text-xs font-black uppercase tracking-wider">
                <KeyRound className="h-4 w-4" strokeWidth={2.5} />
                Legacy Company Access Code
              </span>
              <input
                id="portal-legacy-code"
                ref={inputRef}
                type="text"
                value={code}
                onChange={(e) => {
                  setCode(e.target.value.toUpperCase())
                  setError(null)
                }}
                placeholder="XXXXXXXX"
                maxLength={12}
                autoComplete="off"
                spellCheck={false}
                className="border border-border bg-white px-3 py-3 font-mono text-sm font-bold tracking-widest text-black placeholder:text-muted-foreground focus:outline-none focus-visible:border-primary uppercase"
              />
              <div className="flex items-center gap-1.5 text-[11px] text-amber-700 font-semibold mt-1">
                <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
                Legacy login is read-only with restricted pricing.
              </div>
            </label>
          )}

          {error && (
            <p className="text-xs font-semibold text-destructive">{error}</p>
          )}

          {/* Submit Button */}
          <button
            id="portal-login-btn"
            type="submit"
            disabled={loading || !code.trim() || (!isLegacyMode && !identifier.trim())}
            className="group mt-2 flex items-center justify-center gap-3 border border-border bg-black py-4 text-base font-black uppercase tracking-wider text-white shadow-[var(--shadow-sm)] transition-shadow hover:shadow-[var(--shadow-md)] disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {loading ? "Verifying…" : "Access Portal"}
            {!loading && (
              <ArrowRight className="h-5 w-5 text-primary transition-transform group-hover:translate-x-1" strokeWidth={3} />
            )}
          </button>

          {/* Toggle Legacy Mode */}
          <div className="border-t border-border pt-4 text-center">
            <button
              type="button"
              onClick={() => {
                setIsLegacyMode(!isLegacyMode)
                setError(null)
                setInfoMessage(null)
                setCode("")
              }}
              className="text-xs font-bold text-muted-foreground underline decoration-primary underline-offset-4 hover:text-foreground"
            >
              {isLegacyMode
                ? "← Switch to personal single-use login code"
                : "Have a legacy company code instead?"}
            </button>
          </div>
        </form>
      </div>
    </main>
  )
}
