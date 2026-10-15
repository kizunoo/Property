// ─── lib/portal-api.ts ───────────────────────────────────────────────────────
// Typed fetch helpers for the client portal.
// All helpers go through the Next.js BFF (/api/portal/...) — never directly
// to FastAPI. No internal scoring fields are requested or returned.
// ─────────────────────────────────────────────────────────────────────────────

import type {
  DashboardData,
  DemosData,
  Demo,
  ActivityData,
  InquiriesData,
  InquiryMessage,
  CatalogData,
  Quote,
  QuotesData,
  PreferencesPayload,
  PreferencesData,
} from "@/lib/portal-types"

// ─── Helpers ─────────────────────────────────────────────────────────────────

class PortalApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
    this.name = "PortalApiError"
  }
}

async function apiFetch<T>(url: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(url, opts)
  const data = await res.json()
  if (!res.ok) {
    throw new PortalApiError(res.status, data?.error ?? `Request failed (${res.status})`)
  }
  return data as T
}

// ─── Dashboard ───────────────────────────────────────────────────────────────

export async function fetchDashboard(clientId: string): Promise<DashboardData> {
  return apiFetch<DashboardData>(`/api/portal/${clientId}/dashboard`)
}

// ─── Demos ───────────────────────────────────────────────────────────────────

export async function fetchMyDemos(clientId: string): Promise<DemosData> {
  return apiFetch<DemosData>(`/api/portal/${clientId}/demos`)
}

export async function confirmDemo(
  clientId: string,
  demoId: string,
): Promise<{ success: boolean; demo_id: string; status: string; ics_url?: string | null }> {
  return apiFetch<{ success: boolean; demo_id: string; status: string; ics_url?: string | null }>(
    `/api/portal/${clientId}/demos/${demoId}/confirm`,
    { method: "POST" }
  )
}

export async function cancelDemo(
  clientId: string,
  demoId: string,
  reason?: string,
): Promise<{ success: boolean; demo_id: string; status: string }> {
  return apiFetch<{ success: boolean; demo_id: string; status: string }>(
    `/api/portal/${clientId}/demos/${demoId}/cancel`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason }),
    }
  )
}

export interface RescheduleDemoPayload {
  preferred_date?: string | null
  notes?: string | null
}

export async function rescheduleDemo(
  clientId: string,
  demoId: string,
  payload: RescheduleDemoPayload,
): Promise<{ success: boolean; old_demo_id: string; new_demo?: any; status: string; message: string }> {
  return apiFetch<{ success: boolean; old_demo_id: string; new_demo?: any; status: string; message: string }>(
    `/api/portal/${clientId}/demos/${demoId}/reschedule`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  )
}

export interface RequestDemoPayload {
  property_id: string
  preferred_date?: string | null
  notes?: string | null
}

export interface RequestDemoResult {
  success: boolean
  message: string
  viewing?: { id: string } | null
  existing_id?: string
}

export async function requestDemo(
  clientId: string,
  payload: RequestDemoPayload,
): Promise<RequestDemoResult> {
  return apiFetch<RequestDemoResult>(`/api/portal/${clientId}/request_demo`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
}

// ─── Activity ────────────────────────────────────────────────────────────────

export async function fetchActivity(clientId: string): Promise<ActivityData> {
  return apiFetch<ActivityData>(`/api/portal/${clientId}/activity`)
}

// ─── Catalog & Feedback ──────────────────────────────────────────────────────

export interface CatalogFilters {
  category?: string
  property_type?: string
  min_price?: number | string
  max_price?: number | string
  max_lead_time_weeks?: number | string
  min_payload_kg?: number | string
  environment?: string
  search?: string
  sort?: string
}

export async function fetchCatalog(clientId: string, filters?: CatalogFilters): Promise<CatalogData> {
  const params = new URLSearchParams()
  if (filters) {
    Object.entries(filters).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") {
        params.set(k, String(v))
      }
    })
  }
  const qs = params.toString() ? `?${params.toString()}` : ""
  return apiFetch<CatalogData>(`/api/portal/${clientId}/catalog${qs}`)
}

export async function saveUnitFeedback(
  clientId: string,
  propertyId: string,
  feedback: { interest?: "interested" | "not_interested" | null; reason?: string | null; is_saved?: boolean }
): Promise<{ property_id: string; interest: "interested" | "not_interested" | null; reason?: string | null; is_saved: boolean }> {
  return apiFetch(`/api/portal/${clientId}/catalog/${propertyId}/feedback`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(feedback),
  })
}

// ─── Quotes ──────────────────────────────────────────────────────────────────

export async function fetchQuotes(clientId: string): Promise<QuotesData> {
  return apiFetch<QuotesData>(`/api/portal/${clientId}/quotes`)
}

export async function requestQuote(
  clientId: string,
  payload: { property_id: string; quantity: number; notes?: string }
): Promise<Quote> {
  return apiFetch<Quote>(`/api/portal/${clientId}/quotes`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
}

export async function respondQuote(
  clientId: string,
  quoteId: string,
  payload:
    | { status?: "accepted" | "declined"; response?: "accepted" | "declined"; note?: string }
    | ("accepted" | "declined"),
  optionalNote?: string
): Promise<Quote> {
  const body =
    typeof payload === "string"
      ? { response: payload, note: optionalNote }
      : { response: payload.response ?? payload.status, note: payload.note ?? optionalNote }
  return apiFetch<Quote>(`/api/portal/${clientId}/quotes/${quoteId}/respond`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
}

// ─── Inquiries & Messages ────────────────────────────────────────────────────

export async function fetchInquiries(clientId: string): Promise<InquiriesData> {
  return apiFetch<InquiriesData>(`/api/portal/${clientId}/inquiries`)
}

export interface SubmitInquiryPayload {
  property_id?: string | null
  message: string
}

export interface SubmitInquiryResult {
  id: string
  client_id: string
  property_id?: string | null
  message: string
  status: string
}

export async function submitInquiry(
  clientId: string,
  payload: SubmitInquiryPayload,
): Promise<SubmitInquiryResult> {
  return apiFetch<SubmitInquiryResult>(`/api/portal/${clientId}/inquiry`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
}

export async function postInquiryMessage(
  clientId: string,
  inquiryId: string,
  body: string
): Promise<InquiryMessage> {
  return apiFetch<InquiryMessage>(`/api/portal/${clientId}/inquiries/${inquiryId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ body }),
  })
}

export async function markInquiryRead(
  clientId: string,
  inquiryId: string
): Promise<{ success: boolean }> {
  return apiFetch<{ success: boolean }>(`/api/portal/${clientId}/inquiries/${inquiryId}/read`, {
    method: "POST",
  })
}

// ─── Preferences & Profile ───────────────────────────────────────────────────

export async function fetchPreferences(clientId: string): Promise<PreferencesData> {
  return apiFetch<PreferencesData>(`/api/portal/${clientId}/preferences`)
}

export async function savePreferences(
  clientId: string,
  payload: PreferencesPayload,
): Promise<PreferencesData> {
  return apiFetch<PreferencesData>(`/api/portal/${clientId}/preferences`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
}

// ─── Auth / Session ──────────────────────────────────────────────────────────

export interface PortalMeData {
  authenticated: boolean
  session_id: string
  contact_id: string | null
  contact_name: string
  portal_role: "admin" | "evaluator" | "finance_viewer" | "legacy_readonly"
  client_id: string
  client_name: string
  is_legacy: boolean
}

export async function fetchAuthMe(): Promise<PortalMeData> {
  return apiFetch<PortalMeData>("/api/portal/auth/me")
}

export async function logoutPortal(): Promise<void> {
  await fetch("/api/portal/auth/logout", { method: "POST" })
}

export { PortalApiError }
