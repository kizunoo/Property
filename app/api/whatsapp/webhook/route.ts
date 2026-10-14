import { NextRequest, NextResponse } from "next/server"

export const maxDuration = 15
const FASTAPI_URL = process.env.FASTAPI_URL ?? process.env.BACKEND_URL ?? "http://localhost:8000"

export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url)
    const mode = searchParams.get("hub.mode")
    const verify_token = searchParams.get("hub.verify_token")
    const challenge = searchParams.get("hub.challenge")
    const VERIFY_TOKEN = process.env.WHATSAPP_VERIFY_TOKEN || "5e71124027fbce99e78aa91b4023f9f5ed7a0b2654b82651"

    if (mode === "subscribe") {
      if (!verify_token || verify_token === VERIFY_TOKEN) {
        return new Response(challenge ?? "", {
          status: 200,
          headers: { "Content-Type": "text/plain" },
        })
      }
      return new Response("Verification token mismatch", { status: 403 })
    }

    const upstream = await fetch(`${FASTAPI_URL}/api/whatsapp/webhook?${searchParams.toString()}`)
    return new Response(await upstream.text(), { status: upstream.status })
  } catch (err: any) {
    return new Response(err?.message ?? "Error", { status: 500 })
  }
}

export async function POST(req: NextRequest) {
  try {
    const rawText = await req.text()
    const signature = req.headers.get("x-hub-signature-256")
    const fs = await import("fs")
    const path = await import("path")
    const logLine = `[${new Date().toISOString()}] POST sig=${signature ? "YES" : "NO"} len=${rawText.length}\n${rawText.slice(0, 300)}\n---\n`
    fs.appendFileSync(path.join(process.cwd(), "backend", "webhook_hits.log"), logLine, "utf-8")

    const headers: Record<string, string> = { "Content-Type": "application/json" }
    if (signature) {
      headers["X-Hub-Signature-256"] = signature
    }
    const upstream = await fetch(`${FASTAPI_URL}/api/whatsapp/webhook`, {
      method: "POST",
      headers,
      body: rawText,
    })
    const upstreamText = await upstream.text()
    fs.appendFileSync(path.join(process.cwd(), "backend", "webhook_hits.log"), `[UPSTREAM STATUS ${upstream.status}]: ${upstreamText}\nFULL BODY:\n${rawText}\n===\n`, "utf-8")
    let data = { status: "ok" }
    try { data = JSON.parse(upstreamText) } catch {}
    return new Response(upstreamText, {
      status: upstream.status,
      headers: { "Content-Type": "application/json" },
    })
  } catch (err: any) {
    return NextResponse.json({ status: "acknowledged_with_error", error: err?.message }, { status: 200 })
  }
}
