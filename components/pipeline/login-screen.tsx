"use client"

import { useState, type FormEvent } from "react"
import { ArrowRight, Building2, KeyRound, ShieldAlert, UserRound } from "lucide-react"

interface LoginScreenProps {
  onSignIn: () => void
}

export function LoginScreen({ onSignIn }: LoginScreenProps) {
  const [agentId, setAgentId] = useState("")
  const [password, setPassword] = useState("")

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    onSignIn()
  }

  return (
    <main className="relative flex min-h-screen items-center justify-center overflow-hidden bg-background px-4 py-10">
      <div className="stripes-diagonal pointer-events-none absolute inset-0" />

      <div className="relative z-10 w-full max-w-md">
        <div className="mb-6 flex items-center justify-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center border-4 border-black bg-black">
            <Building2 className="h-6 w-6 text-primary" strokeWidth={2.5} />
          </div>
          <div>
            <div className="font-sans text-2xl font-bold leading-none tracking-tight">
              PIPELINE<span className="text-muted-foreground">.EV</span>
            </div>
            <div className="text-[11px] font-black uppercase tracking-wider text-muted-foreground">
              Client Priority Console
            </div>
          </div>
        </div>

        <form
          onSubmit={handleSubmit}
          className="flex flex-col gap-5 border-4 border-black bg-card p-6 shadow-[8px_8px_0px_0px_rgba(0,0,0,1)] sm:p-8"
        >
          <div className="border-b-4 border-black pb-4">
            <span className="inline-flex items-center gap-1.5 border-2 border-black bg-primary px-3 py-1 text-xs font-black uppercase tracking-wider">
              <ShieldAlert className="h-3.5 w-3.5" strokeWidth={3} />
              Restricted Access
            </span>
            <h1 className="mt-3 text-2xl font-bold tracking-tight sm:text-3xl">Agent Sign In</h1>
          </div>

          <label className="flex flex-col gap-2">
            <span className="flex items-center gap-2 text-xs font-black uppercase tracking-wider">
              <UserRound className="h-4 w-4" strokeWidth={3} />
              Agent ID
            </span>
            <input
              value={agentId}
              onChange={(event) => setAgentId(event.target.value)}
              placeholder="e.g. RD-4471"
              autoComplete="username"
              className="border-2 border-black bg-white px-3 py-3 font-mono text-sm font-bold text-black placeholder:text-muted-foreground focus:outline-none focus-visible:shadow-[3px_3px_0px_0px_rgba(0,0,0,1)]"
            />
          </label>

          <label className="flex flex-col gap-2">
            <span className="flex items-center gap-2 text-xs font-black uppercase tracking-wider">
              <KeyRound className="h-4 w-4" strokeWidth={3} />
              Password
            </span>
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="••••••••"
              autoComplete="current-password"
              className="border-2 border-black bg-white px-3 py-3 font-mono text-sm font-bold text-black placeholder:text-muted-foreground focus:outline-none focus-visible:shadow-[3px_3px_0px_0px_rgba(0,0,0,1)]"
            />
          </label>

          <button
            type="submit"
            className="group mt-2 flex items-center justify-center gap-3 border-4 border-black bg-black py-5 text-base font-black uppercase tracking-wider text-white shadow-[6px_6px_0px_0px_rgba(0,0,0,1)] transition-transform hover:-translate-x-0.5 hover:-translate-y-0.5 hover:shadow-[8px_8px_0px_0px_rgba(0,0,0,1)] active:translate-x-0 active:translate-y-0 active:shadow-none sm:text-lg"
          >
            Sign In
            <ArrowRight className="h-5 w-5 text-primary transition-transform group-hover:translate-x-1" strokeWidth={3} />
          </button>

          <p className="text-center text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
            Demo mode — any credentials will grant access
          </p>
        </form>
      </div>
    </main>
  )
}
