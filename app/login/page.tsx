"use client"

import { useState, type FormEvent } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { Bot, KeyRound, Lock, Mail, ShieldAlert, AlertCircle, Loader2 } from "lucide-react"

export default function LoginPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const returnUrl = searchParams.get("returnUrl") || "/"

  const [mode, setMode] = useState<"login" | "enroll">("login")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [enrollmentCode, setEnrollmentCode] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  async function handleLogin(e: FormEvent) {
    e.preventDefault()
    if (!email || !password) return
    setLoading(true)
    setError(null)
    setSuccess(null)

    try {
      const res = await fetch("/api/agent/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      })
      const data = await res.json()
      if (!res.ok) {
        setError(data.detail || "Authentication failed. Check your credentials.")
        return
      }
      router.push(returnUrl)
      router.refresh()
    } catch {
      setError("Network error connecting to login server.")
    } finally {
      setLoading(false)
    }
  }

  async function handleEnroll(e: FormEvent) {
    e.preventDefault()
    if (!enrollmentCode || !password) return
    setLoading(true)
    setError(null)
    setSuccess(null)

    try {
      const res = await fetch("/api/agent/enroll", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enrollment_code: enrollmentCode, password }),
      })
      const data = await res.json()
      if (!res.ok) {
        setError(data.detail || "Enrollment failed. Invalid or expired code.")
        return
      }
      setSuccess("Enrollment complete! You can now log in with your email and password.")
      setMode("login")
      setPassword("")
    } catch {
      setError("Network error connecting to enrollment service.")
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="relative flex min-h-screen items-center justify-center overflow-hidden bg-background px-4 py-10">
      <div className="relative z-10 w-full max-w-md">
        <div className="mb-6 flex items-center justify-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center border border-border bg-black text-primary">
            <Bot className="h-6 w-6" strokeWidth={2.5} />
          </div>
          <div>
            <div className="font-sans text-2xl font-bold leading-none tracking-tight text-foreground">
              PIPELINE<span className="text-muted-foreground">.EV</span>
            </div>
            <div className="text-[11px] font-black uppercase tracking-wider text-muted-foreground">
              Industrial Robotics Brokerage
            </div>
          </div>
        </div>

        <div className="border border-border bg-card p-6 shadow-[var(--shadow-md)] sm:p-8">
          <div className="border-b border-border pb-4 mb-5">
            <span className="inline-flex items-center gap-1.5 border border-border bg-primary/20 px-2.5 py-1 text-[11px] font-black uppercase tracking-wider text-foreground">
              <ShieldAlert className="h-3.5 w-3.5 text-primary" strokeWidth={3} />
              Internal Console Access
            </span>
            <div className="mt-3 flex gap-4 text-sm font-bold">
              <button
                type="button"
                onClick={() => { setMode("login"); setError(null); setSuccess(null); }}
                className={`pb-1 border-b-2 transition-colors ${
                  mode === "login" ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"
                }`}
              >
                Sign In
              </button>
              <button
                type="button"
                onClick={() => { setMode("enroll"); setError(null); setSuccess(null); }}
                className={`pb-1 border-b-2 transition-colors ${
                  mode === "enroll" ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"
                }`}
              >
                Enroll with Code
              </button>
            </div>
          </div>

          {error && (
            <div className="mb-4 flex items-start gap-2.5 rounded border border-rose-300 bg-rose-50 p-3 text-xs text-rose-800">
              <AlertCircle className="h-4 w-4 shrink-0 text-rose-600 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          {success && (
            <div className="mb-4 rounded border border-emerald-300 bg-emerald-50 p-3 text-xs text-emerald-800">
              {success}
            </div>
          )}

          {mode === "login" ? (
            <form onSubmit={handleLogin} className="flex flex-col gap-4">
              <label className="flex flex-col gap-1.5">
                <span className="flex items-center gap-1.5 text-xs font-bold text-foreground">
                  <Mail className="h-3.5 w-3.5 text-muted-foreground" />
                  Work Email
                </span>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="rep@pipeline-ev.internal"
                  required
                  autoComplete="username"
                  className="rounded border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </label>

              <label className="flex flex-col gap-1.5">
                <span className="flex items-center gap-1.5 text-xs font-bold text-foreground">
                  <Lock className="h-3.5 w-3.5 text-muted-foreground" />
                  Password
                </span>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••••••"
                  required
                  autoComplete="current-password"
                  className="rounded border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </label>

              <button
                type="submit"
                disabled={loading}
                className="mt-2 flex items-center justify-center gap-2 rounded bg-primary px-4 py-2.5 text-xs font-black uppercase tracking-wider text-black hover:bg-primary/90 disabled:opacity-50"
              >
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Sign In to Pipeline"}
              </button>
            </form>
          ) : (
            <form onSubmit={handleEnroll} className="flex flex-col gap-4">
              <label className="flex flex-col gap-1.5">
                <span className="flex items-center gap-1.5 text-xs font-bold text-foreground">
                  <KeyRound className="h-3.5 w-3.5 text-muted-foreground" />
                  One-Time Enrollment Code
                </span>
                <input
                  type="text"
                  value={enrollmentCode}
                  onChange={(e) => setEnrollmentCode(e.target.value.toUpperCase())}
                  placeholder="12-character code from admin"
                  required
                  className="rounded border border-border bg-background px-3 py-2 text-sm uppercase font-mono tracking-wider text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </label>

              <label className="flex flex-col gap-1.5">
                <span className="flex items-center gap-1.5 text-xs font-bold text-foreground">
                  <Lock className="h-3.5 w-3.5 text-muted-foreground" />
                  Set New Password (min 12 chars)
                </span>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="At least 12 characters"
                  required
                  minLength={12}
                  className="rounded border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </label>

              <button
                type="submit"
                disabled={loading}
                className="mt-2 flex items-center justify-center gap-2 rounded bg-primary px-4 py-2.5 text-xs font-black uppercase tracking-wider text-black hover:bg-primary/90 disabled:opacity-50"
              >
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Activate Agent Account"}
              </button>
            </form>
          )}

          <div className="mt-6 border-t border-border pt-4 text-center">
            <p className="text-[11px] text-muted-foreground">
              Client buyer?{" "}
              <a href="/portal" className="font-bold text-foreground underline underline-offset-2">
                Access Company Portal
              </a>
            </p>
          </div>
        </div>
      </div>
    </main>
  )
}
