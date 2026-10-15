// ─── lib/portal-types.ts ─────────────────────────────────────────────────────
// All types here are CLIENT-SAFE: no ML probability, tier, expected_value,
// buy probability, agent reasoning, internal notes, or scoring breakdowns.
// ─────────────────────────────────────────────────────────────────────────────

export type PortalTab =
  | "overview"
  | "matches"
  | "catalog"
  | "demos"
  | "quotes"
  | "activity"
  | "messages"
  | "profile"

// ─── Dashboard (overview + matches) ──────────────────────────────────────────

export interface MatchUnit {
  property_id: string
  name: string
  cost: number | null
  environment: string | null
  image_url: string | null
  property_type: string | null
  specs?: Record<string, any>
  payload_tier: number | null
  operational_range_sqft: number | null
  nav_sensors: number | null
  estimated_annual_savings: number | null
  payback_months: number | null
  /** Comes from client_facing_reasoning_cache — never from agent internal prompts */
  reasoning: string | null
  my_feedback?: UnitFeedback | null
}

export interface DashboardDemo {
  id: string
  property_id?: string | null
  property_name: string | null
  scheduled_at: string | null
  status: string
}

export interface DashboardData {
  client_name: string
  client_id: string
  relationship_stage: string
  matches: MatchUnit[]
  scheduled_demos: DashboardDemo[]
  unread_messages?: number
  quotes_awaiting?: number
  pending_demo_confirmations?: number
}

// ─── Demos / Demonstrations (backed by scheduled_viewings) ───────────────────

export interface Demo {
  id: string
  status: string
  scheduled_at: string | null
  property_id?: string | null
  property_name: string | null
  property_environment: string | null
  confirmation_status?: string | null
  client_confirmed_at?: string | null
  ics_url?: string | null
  can_confirm?: boolean
  can_cancel?: boolean
  can_reschedule?: boolean
  poc_criteria?: string[]
  poc_feedback?: string | null
  poc_outcome?: "proceed" | "decline" | "undecided" | null
  can_edit_poc_criteria?: boolean
  can_submit_poc_feedback?: boolean
}

export interface DemosData {
  demos: Demo[]
}

// ─── Unit Feedback ───────────────────────────────────────────────────────────

export interface UnitFeedback {
  interest: "interested" | "not_interested" | null
  reason?: string | null
  is_saved: boolean
}

// ─── Catalog ─────────────────────────────────────────────────────────────────

export interface CatalogUnit {
  property_id: string
  name: string
  sku?: string | null
  manufacturer?: string | null
  category?: string | null
  specs?: Record<string, any>
  lead_time_weeks?: number | null
  stock_status?: string | null
  spec_sheet_url?: string | null
  currency?: string
  cost: number | null
  environment: string | null
  image_url: string | null
  property_type: string | null
  payload_tier: number | null
  operational_range_sqft: number | null
  nav_sensors: number | null
  estimated_annual_savings: number | null
  payback_months: number | null
  matched: boolean
  my_feedback?: UnitFeedback | null
}

export interface CatalogData {
  units: CatalogUnit[]
  matched_property_ids: string[]
}

// ─── Quotes ──────────────────────────────────────────────────────────────────

export interface Quote {
  id: string
  property_id: string
  property_name: string
  quantity: number
  notes?: string | null
  status: "requested" | "sent" | "accepted" | "declined"
  requested_at: string
  responded_at?: string | null
  quoted_amount?: number | null
  currency?: string
  customer_note?: string | null
  valid_until?: string | null
  sent_at?: string | null
}

export interface QuotesData {
  quotes: Quote[]
}

// ─── Messages & Inquiries ────────────────────────────────────────────────────

export interface InquiryMessage {
  id: string
  inquiry_id: string
  sender: "company" | "rep"
  body: string
  read_at: string | null
  created_at: string
}

export interface Inquiry {
  id: string
  message: string
  status: string
  agent_reply: string | null
  created_at: string
  property_name: string | null
  property_id: string | null
  messages?: InquiryMessage[]
  unread_count?: number
}

export interface InquiriesData {
  inquiries: Inquiry[]
  total_unread?: number
}

// ─── Activity ────────────────────────────────────────────────────────────────

export type ActivityEventType = "demo" | "message" | "quote" | "profile"

export interface ActivityItem {
  event_type: ActivityEventType
  label: string
  at: string | null
  ref_id: string
}

export interface ActivityData {
  activity: ActivityItem[]
}

// ─── Profile & Preferences ───────────────────────────────────────────────────

export type FinancingStatus = 'cash' | 'pre-approved' | 'in-progress' | 'unspecified' | 'leasing'
export type MoveInTimeline = '< 3 months' | '3-6 months' | '6-12 months' | 'flexible'

export interface ContactPerson {
  id: string
  name: string
  role: string
  title?: string | null
  email?: string | null
}

export interface FacilityProfileData {
  facility_type?: "warehouse" | "manufacturing" | "healthcare" | "cleaning" | "retail_hospitality" | null
  floor_area_sqm?: number | null
  environment_notes?: string | null
  primary_use_case?: "transport" | "cleaning" | "palletizing" | "security" | "delivery" | null
  timeline?: "0-3m" | "3-6m" | "6-12m" | "12m+" | null
  budget_band?: "<50k" | "50-150k" | "150-500k" | "500k+" | null
}

export interface PreferencesPayload {
  stated_budget?: number | null
  preferred_neighborhood?: string | null
  secondary_neighborhood?: string | null
  financing_status?: FinancingStatus | null
  move_in_timeline?: MoveInTimeline | null
  property_type_preference?: string | null
  industry?: string | null
  facility_type?: string | null
  facility_size_sqm?: number | null
  use_case?: string | null
  purchase_timeline?: string | null
  existing_automation?: string | null
  facility_profile?: FacilityProfileData | null
}

export interface PreferencesData extends PreferencesPayload {
  client_id: string
  profile_updated_at?: string | null
  facility_profile?: FacilityProfileData | null
  contacts?: ContactPerson[]
  matches_refreshed_count: number
  updated_fields: string[]
  available_property_types?: string[]
  available_environments?: string[]
}
