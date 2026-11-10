// lib/fetch-quotes.ts
// Frontend API wrappers for same-origin /api/quotes endpoints.
// Never throws; returns { ok: false, error: "..." } on failure.

import {
  mapQuotesPayload,
  type ActivityRow,
  type QuoteRequest,
  type RequestKind,
  type SupplierQuote,
} from "./quotes"

export type FetchQuotesResult =
  | {
      ok: true
      data: {
        requests: QuoteRequest[]
        quotes: SupplierQuote[]
        activity: ActivityRow[]
      }
    }
  | { ok: false; error: string }

export type QuoteRequestResult =
  | { ok: true; data: QuoteRequest }
  | { ok: false; error: string }

export type LogActivityResult =
  | { ok: true; activity?: ActivityRow }
  | { ok: false; error: string }

export async function fetchQuotes(): Promise<FetchQuotesResult> {
  try {
    const res = await fetch("/api/quotes", {
      method: "GET",
      cache: "no-store",
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      return { ok: false, error: err?.detail || err?.error || "Failed to fetch quotes" }
    }
    const json = await res.json()
    const mapped = mapQuotesPayload(json)
    return { ok: true, data: mapped }
  } catch (err: any) {
    return { ok: false, error: err?.message || "Network error fetching quotes" }
  }
}

export async function createQuoteRequest(
  clientId: string,
  propertyId: string,
  marketPriceMyr: number,
  kind: RequestKind = "quote"
): Promise<QuoteRequestResult> {
  try {
    const res = await fetch("/api/quotes/request", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        client_id: clientId,
        property_id: propertyId,
        market_price_myr: marketPriceMyr,
        kind,
      }),
      cache: "no-store",
    })
    const json = await res.json().catch(() => ({}))
    if (!res.ok) {
      return { ok: false, error: json?.detail || json?.error || "Failed to create quote request" }
    }
    const mapped = mapQuotesPayload({ requests: [json] })
    if (mapped.requests.length === 0) {
      return { ok: false, error: "Invalid response from server" }
    }
    return { ok: true, data: mapped.requests[0] }
  } catch (err: any) {
    return { ok: false, error: err?.message || "Network error creating quote request" }
  }
}

export async function approveQuoteRequest(
  id: string,
  body?: string
): Promise<QuoteRequestResult> {
  try {
    const res = await fetch(`/api/quotes/${encodeURIComponent(id)}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ draft_body: body }),
      cache: "no-store",
    })
    const json = await res.json().catch(() => ({}))
    if (!res.ok) {
      return { ok: false, error: json?.detail || json?.error || "Failed to approve quote request" }
    }
    const mapped = mapQuotesPayload({ requests: [json] })
    if (mapped.requests.length === 0) {
      return { ok: false, error: "Invalid response from server" }
    }
    return { ok: true, data: mapped.requests[0] }
  } catch (err: any) {
    return { ok: false, error: err?.message || "Network error approving quote request" }
  }
}

export async function cancelQuoteRequest(id: string): Promise<QuoteRequestResult> {
  try {
    const res = await fetch(`/api/quotes/${encodeURIComponent(id)}/cancel`, {
      method: "POST",
      cache: "no-store",
    })
    const json = await res.json().catch(() => ({}))
    if (!res.ok) {
      return { ok: false, error: json?.detail || json?.error || "Failed to cancel quote request" }
    }
    const mapped = mapQuotesPayload({ requests: [json] })
    if (mapped.requests.length === 0) {
      return { ok: false, error: "Invalid response from server" }
    }
    return { ok: true, data: mapped.requests[0] }
  } catch (err: any) {
    return { ok: false, error: err?.message || "Network error cancelling quote request" }
  }
}

export async function logQuoteActivity(
  kind: "expiry_followup_sent" | "expiry_dismissed" | "requote_dismissed",
  refId: string,
  summary: string
): Promise<LogActivityResult> {
  try {
    const res = await fetch("/api/quotes/log", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        kind,
        ref_id: refId,
        summary,
      }),
      cache: "no-store",
    })
    const json = await res.json().catch(() => ({}))
    if (!res.ok) {
      return { ok: false, error: json?.detail || json?.error || "Failed to log quote activity" }
    }
    const mapped = mapQuotesPayload({ activity: json.activity ? [json.activity] : [] })
    return { ok: true, activity: mapped.activity[0] }
  } catch (err: any) {
    return { ok: false, error: err?.message || "Network error logging quote activity" }
  }
}

export async function publishQuoteToPortal(
  quoteId: string,
  priceMyr?: number,
  notes?: string
): Promise<{ ok: boolean; error?: string; portalQuoteId?: string }> {
  try {
    const res = await fetch(`/api/quotes/${encodeURIComponent(quoteId)}/publish-to-portal`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ price_myr: priceMyr, notes }),
      cache: "no-store",
    })
    const json = await res.json().catch(() => ({}))
    if (!res.ok) {
      return { ok: false, error: json?.detail || json?.error || "Failed to publish quote to portal" }
    }
    return { ok: true, portalQuoteId: json?.portal_quote_id }
  } catch (err: any) {
    return { ok: false, error: err?.message || "Network error publishing quote to portal" }
  }
}

