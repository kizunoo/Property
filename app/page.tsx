/**
 * app/page.tsx
 * The root page now delegates authentication entirely to proxy.ts (middleware).
 * - If no agent_session cookie is present, proxy.ts redirects to /login.
 * - If authenticated, render the pipeline dashboard directly.
 * No in-memory login state or LoginScreen here.
 */
import { PipelineDashboard } from "@/components/pipeline/pipeline-dashboard"
import { CopilotPanel } from "@/components/pipeline/copilot-panel"
import { PriorityInquiries } from "@/components/pipeline/priority-inquiries"

export default function Home() {
  return (
    <>
      <PriorityInquiries />
      <PipelineDashboard />
      <CopilotPanel />
    </>
  )
  return <PipelineDashboard />
}
