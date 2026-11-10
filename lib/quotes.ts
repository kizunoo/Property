// lib/quotes.ts
// Pure business logic for simulated supplier quotes.
// No imports, no network, no storage, no timers, deterministic only.
// Current time is always a parameter (nowMs).

export const SIM_LABEL = "SIMULATED SUPPLIER"
export const REQUOTE_DROP_PCT = 0.03 // market this far under a locked quote
export const EXPIRY_NUDGE_DAYS = 3 // days left that trigger a follow-up
export const RECENT_HOURS = 24 // "arrived recently" window
const MS_DAY = 86400000
const MS_HOUR = 3600000

export interface SupplierQuote {
  id: string
  requestId?: string | null
  clientId: string
  propertyId: string
  priceMyr: number
  leadTimeWeeks: number | null
  terms: string | null
  sourceText?: string
  issuedAt: string
  expiresAt: string
  supersededBy: string | null
}

export type RequestKind = "quote" | "requote"
export type RequestStatus = "draft" | "sent" | "quoted" | "failed" | "cancelled"

export interface QuoteRequest {
  id: string
  clientId: string
  propertyId: string
  kind: RequestKind
  status: RequestStatus
  draftSubject?: string | null
  draftBody?: string | null
  marketPriceMyr: number | null
  sentAt: string | null
  replyDueAt: string | null
  createdAt: string
}

export interface ActivityRow {
  id: string
  kind: string // e.g. request_sent, quote_received, expiry_followup_sent, expiry_dismissed, requote_dismissed
  summary: string
  refId: string | null
  createdAt: string
}

export interface AgentAction {
  id: string
  kind: "requote" | "expiry"
  clientId: string
  propertyId: string
  quoteId: string
  title: string
  detail: string
  draft: string | null // text for the company (expiry only); requote drafts come from the backend
  marketPriceMyr: number | null
  sortKey: number
}

export interface Names {
  client: (id: string) => string
  robot: (id: string) => string
}

export function validNumber(x: unknown): x is number {
  return typeof x === "number" && Number.isFinite(x) && x > 0
}

function toMs(iso: string | null | undefined): number | null {
  if (!iso) return null
  const t = Date.parse(iso)
  return Number.isFinite(t) ? t : null
}

export function isValidQuote(q: SupplierQuote, nowMs: number): boolean {
  if (!validNumber(q.priceMyr) || q.supersededBy) return false
  const exp = toMs(q.expiresAt)
  return exp !== null && exp > nowMs
}

export function daysLeft(q: SupplierQuote, nowMs: number): number {
  const exp = toMs(q.expiresAt)
  if (exp === null) return 0
  return Math.max(0, Math.ceil((exp - nowMs) / MS_DAY))
}

export function latestValidQuote(
  quotes: SupplierQuote[],
  clientId: string,
  propertyId: string,
  nowMs: number
): SupplierQuote | null {
  let best: SupplierQuote | null = null
  let bestAt = -Infinity
  for (const q of quotes) {
    if (q.clientId !== clientId || q.propertyId !== propertyId) continue
    if (!isValidQuote(q, nowMs)) continue
    const at = toMs(q.issuedAt) ?? -Infinity
    if (at > bestAt) {
      best = q
      bestAt = at
    }
  }
  return best
}

export type PairPriceKind = "real" | "quote" | "market" | "none"

// Price order for ONE company and robot pair:
// real price, then a valid simulated supplier quote, then the robot's displayed
// market price, then none.
export function pairPrice(
  realPrice: unknown,
  quote: SupplierQuote | null,
  robotDisplayPrice: unknown,
  nowMs: number
): { value: number | null; kind: PairPriceKind } {
  if (validNumber(realPrice)) return { value: realPrice, kind: "real" }
  if (quote && isValidQuote(quote, nowMs)) return { value: quote.priceMyr, kind: "quote" }
  if (validNumber(robotDisplayPrice)) return { value: robotDisplayPrice, kind: "market" }
  return { value: null, kind: "none" }
}

// Positive pct means the market is BELOW the quote (a requote may be worth asking for).
export function compareToMarket(
  quotePrice: unknown,
  marketPrice: unknown
): { diff: number; pct: number } | null {
  if (!validNumber(quotePrice) || !validNumber(marketPrice)) return null
  const diff = quotePrice - marketPrice
  return { diff, pct: diff / quotePrice }
}

export function hasOpenRequest(
  requests: QuoteRequest[],
  clientId: string,
  propertyId: string,
  kind: RequestKind,
  afterMs: number
): boolean {
  return requests.some((r) => {
    if (r.clientId !== clientId || r.propertyId !== propertyId || r.kind !== kind) return false
    if (r.status !== "draft" && r.status !== "sent") return false
    const created = toMs(r.createdAt) ?? 0
    return created >= afterMs
  })
}

function hasActivity(activity: ActivityRow[], kinds: string[], refId: string): boolean {
  return activity.some((a) => a.refId === refId && kinds.includes(a.kind))
}

export function expiryDraft(
  names: Names,
  quote: SupplierQuote,
  nowMs: number
): string {
  const day = toMs(quote.expiresAt) ?? nowMs
  const date = new Date(day).toISOString().slice(0, 10)
  const lead =
    quote.leadTimeWeeks != null ? `, lead time ${quote.leadTimeWeeks} weeks` : ""
  return (
    `Hi ${names.client(quote.clientId)}, a quick reminder that the supplier quote for ` +
    `${names.robot(quote.propertyId)} (RM ${Math.round(quote.priceMyr).toLocaleString("en-US")}${lead}) ` +
    `is held until ${date}. Reply to confirm and I will keep it reserved. ` +
    `(${SIM_LABEL} quote, demo system.)`
  )
}

export interface ActionInput {
  quotes: SupplierQuote[]
  requests: QuoteRequest[]
  activity: ActivityRow[]
  marketByRobot: Record<string, number | null | undefined>
  nowMs: number
  names: Names
}

export function agentActions(input: ActionInput): AgentAction[] {
  const { quotes, requests, activity, marketByRobot, nowMs, names } = input
  const latest = new Map<string, SupplierQuote>()
  for (const q of quotes) {
    if (!isValidQuote(q, nowMs)) continue
    const key = `${q.clientId}|${q.propertyId}`
    const cur = latest.get(key)
    if (!cur || (toMs(q.issuedAt) ?? 0) > (toMs(cur.issuedAt) ?? 0)) latest.set(key, q)
  }
  const out: AgentAction[] = []
  for (const q of latest.values()) {
    const left = daysLeft(q, nowMs)
    const issued = toMs(q.issuedAt) ?? 0
    const robot = names.robot(q.propertyId)
    const client = names.client(q.clientId)

    if (left <= EXPIRY_NUDGE_DAYS && !hasActivity(activity, ["expiry_followup_sent", "expiry_dismissed"], q.id)) {
      out.push({
        id: `expiry:${q.id}`,
        kind: "expiry",
        clientId: q.clientId,
        propertyId: q.propertyId,
        quoteId: q.id,
        title: `Quote for ${client} expires in ${left} day${left === 1 ? "" : "s"}`,
        detail: `${robot}, RM ${Math.round(q.priceMyr).toLocaleString("en-US")}. A follow-up is ready to review.`,
        draft: expiryDraft(names, q, nowMs),
        marketPriceMyr: null,
        sortKey: left,
      })
    }

    const market = marketByRobot[q.propertyId]
    const cmp = compareToMarket(q.priceMyr, market)
    if (
      cmp &&
      cmp.pct >= REQUOTE_DROP_PCT &&
      !hasOpenRequest(requests, q.clientId, q.propertyId, "requote", issued) &&
      !hasActivity(activity, ["requote_dismissed"], q.id)
    ) {
      out.push({
        id: `requote:${q.id}`,
        kind: "requote",
        clientId: q.clientId,
        propertyId: q.propertyId,
        quoteId: q.id,
        title: `Market is ${(cmp.pct * 100).toFixed(1)}% under the quote for ${client}`,
        detail: `${robot}: quoted RM ${Math.round(q.priceMyr).toLocaleString("en-US")}, market now RM ${Math.round(market as number).toLocaleString("en-US")}. Ask the supplier to requote.`,
        draft: null,
        marketPriceMyr: market as number,
        sortKey: 1000 - cmp.pct * 100,
      })
    }
  }
  out.sort((a, b) =>
    a.kind === b.kind ? a.sortKey - b.sortKey : a.kind === "expiry" ? -1 : 1
  )
  return out
}

export function briefing(
  quotes: SupplierQuote[],
  requests: QuoteRequest[],
  actions: AgentAction[],
  nowMs: number
): string[] {
  const lines: string[] = []
  const recent = quotes.filter((q) => {
    const at = toMs(q.issuedAt)
    return at !== null && nowMs - at >= 0 && nowMs - at <= RECENT_HOURS * MS_HOUR
  }).length
  const waiting = requests.filter((r) => r.status === "sent").length
  const expiring = actions.filter((a) => a.kind === "expiry").length
  const under = actions.filter((a) => a.kind === "requote").length
  if (recent > 0) lines.push(`${recent} supplier quote${recent === 1 ? "" : "s"} arrived in the last 24 hours.`)
  if (waiting > 0) lines.push(`${waiting} request${waiting === 1 ? " is" : "s are"} waiting for a supplier reply.`)
  if (expiring > 0) lines.push(`${expiring} quote${expiring === 1 ? "" : "s"} expire${expiring === 1 ? "s" : ""} within ${EXPIRY_NUDGE_DAYS} days.`)
  if (under > 0) lines.push(`Market price is ${(REQUOTE_DROP_PCT * 100).toFixed(0)}% or more under ${under} locked quote${under === 1 ? "" : "s"}.`)
  return lines.length ? lines : ["No agent activity yet."]
}

export function mapQuotesPayload(json: unknown): {
  requests: QuoteRequest[]
  quotes: SupplierQuote[]
  activity: ActivityRow[]
} {
  const empty = { requests: [], quotes: [], activity: [] }
  if (!json || typeof json !== "object") return empty
  const raw = json as Record<string, unknown>

  const requests: QuoteRequest[] = []
  if (Array.isArray(raw.requests)) {
    for (const r of raw.requests) {
      if (!r || typeof r !== "object") continue
      const req = r as Record<string, unknown>
      if (typeof req.id !== "string" || typeof req.client_id !== "string" || typeof req.property_id !== "string") {
        continue
      }
      const kind = req.kind === "requote" ? "requote" : "quote"
      const status = typeof req.status === "string" ? (req.status as RequestStatus) : "draft"
      requests.push({
        id: req.id,
        clientId: req.client_id,
        propertyId: req.property_id,
        kind,
        status,
        draftSubject: typeof req.draft_subject === "string" ? req.draft_subject : null,
        draftBody: typeof req.draft_body === "string" ? req.draft_body : null,
        marketPriceMyr: typeof req.market_price_myr === "number" ? req.market_price_myr : null,
        sentAt: typeof req.sent_at === "string" ? req.sent_at : null,
        replyDueAt: typeof req.reply_due_at === "string" ? req.reply_due_at : null,
        createdAt: typeof req.created_at === "string" ? req.created_at : "",
      })
    }
  }

  const quotes: SupplierQuote[] = []
  if (Array.isArray(raw.quotes)) {
    for (const q of raw.quotes) {
      if (!q || typeof q !== "object") continue
      const quo = q as Record<string, unknown>
      if (typeof quo.id !== "string" || typeof quo.client_id !== "string" || typeof quo.property_id !== "string") {
        continue
      }
      const price = typeof quo.price_myr === "number" ? quo.price_myr : Number(quo.price_myr)
      if (!validNumber(price)) continue
      quotes.push({
        id: quo.id,
        requestId: typeof quo.request_id === "string" ? quo.request_id : null,
        clientId: quo.client_id,
        propertyId: quo.property_id,
        priceMyr: price,
        leadTimeWeeks: typeof quo.lead_time_weeks === "number" ? quo.lead_time_weeks : null,
        terms: typeof quo.terms === "string" ? quo.terms : null,
        sourceText: typeof quo.source_text === "string" ? quo.source_text : undefined,
        issuedAt: typeof quo.issued_at === "string" ? quo.issued_at : "",
        expiresAt: typeof quo.expires_at === "string" ? quo.expires_at : "",
        supersededBy: typeof quo.superseded_by === "string" ? quo.superseded_by : null,
      })
    }
  }

  const activity: ActivityRow[] = []
  if (Array.isArray(raw.activity)) {
    for (const a of raw.activity) {
      if (!a || typeof a !== "object") continue
      const act = a as Record<string, unknown>
      if (typeof act.id !== "string" || typeof act.kind !== "string") continue
      activity.push({
        id: act.id,
        kind: act.kind,
        summary: typeof act.summary === "string" ? act.summary : "",
        refId: typeof act.ref_id === "string" ? act.ref_id : null,
        createdAt: typeof act.created_at === "string" ? act.created_at : "",
      })
    }
  }

  return { requests, quotes, activity }
}

// selftest matching quote_reference.ts
function assert(cond: boolean, msg: string): void {
  if (!cond) throw new Error("selftest FAILED: " + msg)
}

export function selftest(): void {
  const now = Date.UTC(2026, 10, 3, 9, 0, 0)
  const iso = (ms: number) => new Date(ms).toISOString()
  const mk = (id: string, price: number, issuedDays: number, expiresDays: number, sup: string | null = null): SupplierQuote => ({
    id, clientId: "c1", propertyId: "p1", priceMyr: price, leadTimeWeeks: 8, terms: null,
    issuedAt: iso(now + issuedDays * MS_DAY), expiresAt: iso(now + expiresDays * MS_DAY), supersededBy: sup,
  })
  const names: Names = { client: () => "Ancom", robot: () => "PUDU T300" }

  // validity
  assert(isValidQuote(mk("a", 100000, -1, 13), now), "valid quote")
  assert(!isValidQuote(mk("a", 100000, -15, -1), now), "expired quote")
  assert(!isValidQuote(mk("a", 100000, -1, 13, "b"), now), "superseded quote")
  assert(!isValidQuote(mk("a", 0, -1, 13), now), "zero price")
  assert(daysLeft(mk("a", 100000, -1, 13), now) === 13, "days left")
  assert(daysLeft(mk("a", 100000, -15, -1), now) === 0, "days left floors at 0")

  // price order
  const q = mk("a", 100000, -1, 13)
  assert(pairPrice(5000, q, 90000, now).kind === "real", "real wins")
  assert(pairPrice(null, q, 90000, now).value === 100000, "quote beats market")
  assert(pairPrice(null, mk("a", 100000, -15, -1), 90000, now).kind === "market", "expired quote falls to market")
  assert(pairPrice(null, null, null, now).kind === "none", "none")
  assert(pairPrice(NaN, null, -1, now).kind === "none", "invalid values ignored")

  // compare
  const c = compareToMarket(100000, 96000)
  assert(c !== null && Math.abs(c.pct - 0.04) < 1e-9 && c.diff === 4000, "compare")
  assert(compareToMarket(100000, null) === null, "compare invalid")

  // latest valid quote
  const older = mk("old", 110000, -5, 9)
  const newer = mk("new", 100000, -1, 13)
  assert(latestValidQuote([older, newer], "c1", "p1", now)?.id === "new", "newest wins")
  assert(latestValidQuote([older, newer], "c1", "zzz", now) === null, "other pair none")

  // actions: requote fires at 4% under, not at 2%
  const base = { quotes: [q], requests: [] as QuoteRequest[], activity: [] as ActivityRow[], nowMs: now, names }
  const under4 = agentActions({ ...base, marketByRobot: { p1: 96000 } })
  assert(under4.length === 1 && under4[0].kind === "requote", "requote at 4%")
  assert(under4[0].draft === null && under4[0].marketPriceMyr === 96000, "requote payload")
  assert(agentActions({ ...base, marketByRobot: { p1: 98000 } }).length === 0, "no requote at 2%")
  assert(agentActions({ ...base, marketByRobot: { p1: undefined } }).length === 0, "no market, no action")

  // open requote request suppresses the action; dismissal suppresses it
  const open: QuoteRequest = {
    id: "r1", clientId: "c1", propertyId: "p1", kind: "requote", status: "sent",
    marketPriceMyr: 96000, sentAt: iso(now), replyDueAt: iso(now + 60000), createdAt: iso(now),
  }
  assert(agentActions({ ...base, requests: [open], marketByRobot: { p1: 96000 } }).length === 0, "open requote suppresses")
  const dismissed: ActivityRow = { id: "x", kind: "requote_dismissed", summary: "", refId: "a", createdAt: iso(now) }
  assert(agentActions({ ...base, activity: [dismissed], marketByRobot: { p1: 96000 } }).length === 0, "dismissed suppresses")

  // expiry fires at 3 days, not at 4; done activity suppresses it
  const soon = mk("s", 100000, -11, 3)
  const exp = agentActions({ ...base, quotes: [soon], marketByRobot: {} })
  assert(exp.length === 1 && exp[0].kind === "expiry" && exp[0].draft !== null, "expiry at 3 days")
  assert(exp[0].draft!.includes("SIMULATED SUPPLIER") && exp[0].draft!.includes("2026-11-06"), "expiry draft text")
  assert(agentActions({ ...base, quotes: [mk("s", 100000, -10, 4)], marketByRobot: {} }).length === 0, "no expiry at 4 days")
  const done: ActivityRow = { id: "y", kind: "expiry_followup_sent", summary: "", refId: "s", createdAt: iso(now) }
  assert(agentActions({ ...base, quotes: [soon], activity: [done], marketByRobot: {} }).length === 0, "followup sent suppresses")

  // ordering: expiry before requote
  const both = agentActions({ ...base, quotes: [soon], marketByRobot: { p1: 90000 } })
  assert(both.length === 2 && both[0].kind === "expiry" && both[1].kind === "requote", "order")

  // briefing
  assert(briefing([], [], [], now)[0] === "No agent activity yet.", "empty briefing")
  const lines = briefing([q], [open], both, now)
  assert(lines.some((l) => l.includes("waiting")) && lines.some((l) => l.includes("expire")), "briefing lines")

  // purity: inputs untouched
  const frozen = JSON.stringify(base)
  agentActions({ ...base, marketByRobot: { p1: 90000 } })
  assert(JSON.stringify(base) === frozen, "inputs not mutated")

  // mapQuotesPayload tests
  const emptyRes = mapQuotesPayload(null)
  assert(emptyRes.requests.length === 0 && emptyRes.quotes.length === 0 && emptyRes.activity.length === 0, "null payload safe")
  const garbageRes = mapQuotesPayload("garbage")
  assert(garbageRes.requests.length === 0, "string payload safe")
  const mixedRes = mapQuotesPayload({
    requests: [{ id: "r1", client_id: "c1", property_id: "p1", kind: "quote", status: "draft" }, { bad: true }],
    quotes: [{ id: "q1", client_id: "c1", property_id: "p1", price_myr: 100000, issued_at: iso(now), expires_at: iso(now) }, { price_myr: -5 }],
    activity: [{ id: "a1", kind: "test", summary: "hi" }, null],
  })
  assert(mixedRes.requests.length === 1 && mixedRes.requests[0].id === "r1", "valid request kept")
  assert(mixedRes.quotes.length === 1 && mixedRes.quotes[0].id === "q1", "valid quote kept")
  assert(mixedRes.activity.length === 1 && mixedRes.activity[0].id === "a1", "valid activity kept")
}

