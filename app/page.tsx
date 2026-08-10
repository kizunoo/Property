"use client"

import { useState } from "react"
import { LoginScreen } from "@/components/pipeline/login-screen"
import { PipelineDashboard } from "@/components/pipeline/pipeline-dashboard"

export default function Home() {
  const [authenticated, setAuthenticated] = useState(false)

  if (!authenticated) {
    return <LoginScreen onSignIn={() => setAuthenticated(true)} />
  }

  return <PipelineDashboard />
}
