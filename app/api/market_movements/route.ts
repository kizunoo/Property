import { NextRequest, NextResponse } from "next/server"
import { getSupabase, isSupabaseConfigured } from "@/lib/supabaseClient"

export const maxDuration = 15

const FASTAPI_URL = process.env.FASTAPI_URL ?? process.env.BACKEND_URL ?? "http://localhost:8000"

async function fallbackSupabase(limitNum: number) {
  if (!isSupabaseConfigured()) return []
  const supabase = getSupabase()
  try {
    const { data: rows, error: historyErr } = await supabase
      .from("property_price_history")
      .select("*, properties(address, neighborhood)")
      .order("changed_at", { ascending: false })
      .limit(limitNum)
    if (!historyErr && rows && rows.length > 0) {
      return rows
    }
  } catch {
    // Ignore and try signals
  }

  try {
    const { data: signals } = await supabase
      .from("signals")
      .select("*, properties(address, neighborhood)")
      .eq("type", "price_change")
      .order("created_at", { ascending: false })
      .limit(limitNum)

    if (!signals) return []

    return signals.map((s: any) => {
      const msg = s.message || ""
      let change_pct = 0.05
      const m = msg.match(/(\d+(?:\.\d+)?)%/)
      const pct_val = m ? parseFloat(m[1]) : 5.0
      if (msg.includes("rose") || msg.includes("jumped")) {
        change_pct = pct_val / 100.0
      } else if (msg.includes("dropped") || msg.includes("fell")) {
        change_pct = -pct_val / 100.0
      }
      return {
        id: s.id,
        property_id: s.property_id,
        old_value: 0,
        new_value: 0,
        change_pct,
        changed_at: s.created_at,
        properties: s.properties || null,
      }
    })
  } catch {
    return []
  }
}

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url)
  const limit = searchParams.get("limit") ?? "10"
  const limitNum = parseInt(limit, 10) || 10
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 6_000)
  try {
    const upstream = await fetch(
      FASTAPI_URL + "/api/market_movements?limit=" + limit,
      { signal: controller.signal }
    )
    clearTimeout(timer)
    if (upstream.ok) {
      const data = await upstream.json()
      if (Array.isArray(data) && data.length > 0) {
        return NextResponse.json(data)
      }
    }
  } catch {
    clearTimeout(timer)
  }

  const fallbackData = await fallbackSupabase(limitNum)
  return NextResponse.json(fallbackData)
}
