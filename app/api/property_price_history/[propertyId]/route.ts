import { NextRequest, NextResponse } from "next/server"
import { getSupabase, isSupabaseConfigured } from "@/lib/supabaseClient"

export const maxDuration = 15

const FASTAPI_URL = process.env.FASTAPI_URL ?? process.env.BACKEND_URL ?? "http://localhost:8000"

async function fallbackSupabaseHistory(propertyId: string) {
  if (!isSupabaseConfigured()) return []
  const supabase = getSupabase()

  try {
    const { data: rows, error } = await supabase
      .from("property_price_history")
      .select("*")
      .eq("property_id", propertyId)
      .order("changed_at", { ascending: true })

    if (!error && rows && rows.length > 0) {
      return rows
    }
  } catch {
    // Ignore and fallback to signals
  }

  try {
    const { data: signals } = await supabase
      .from("signals")
      .select("*")
      .eq("type", "price_change")
      .eq("property_id", propertyId)
      .order("created_at", { ascending: true })

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

      const mPrice = msg.match(/RM([\d,]+)/)
      const priceVal = mPrice ? parseFloat(mPrice[1].replace(/,/g, "")) : 2000000.0

      return {
        id: s.id,
        property_id: propertyId,
        old_value: priceVal / (1 + change_pct),
        new_value: priceVal,
        change_pct,
        changed_at: s.created_at,
      }
    })
  } catch {
    return []
  }
}

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ propertyId: string }> }
) {
  const { propertyId } = await params
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 6_000)
  try {
    const upstream = await fetch(
      FASTAPI_URL + "/api/property_price_history/" + propertyId,
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

  const fallback = await fallbackSupabaseHistory(propertyId)
  return NextResponse.json(fallback)
}
