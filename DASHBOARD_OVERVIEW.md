# PIPELINE.EV — Client Priority Console

A Neo-Brutalist internal B2B dashboard for real estate agents to prioritize clients by **Expected Value** (`Probability × Property Value`). This document describes exactly what exists in the codebase today: the design system, every component, the data model, and the interactive behavior.

---

## 1. Design System (`app/globals.css`, `app/layout.tsx`)

**Aesthetic:** Neo-Brutalist. Stark white canvas, pure black ink, one acid-yellow accent. Zero softness — no gradients-as-decoration, no rounded corners, no blur.

| Token | Value | Usage |
|---|---|---|
| `--background` | `oklch(1 0 0)` (white) | Page background |
| `--foreground` | `oklch(0 0 0)` (black) | Text |
| `--primary` / `--accent` | `oklch(0.87 0.19 96)` (acid yellow) | The **one** signature color — Expected Value chips, active tier badge, emphasis stat card, invite confirmation |
| `--border` / `--input` / `--ring` | `oklch(0 0 0)` (black) | Every border in the app |
| `--radius` | `0rem` | Sharp corners everywhere — enforced via `--radius-sm/md/lg/xl` all set to `0rem` |
| `--tier-1` | acid yellow | VIP badge |
| `--tier-2` | light gray | Warm badge (black bg in table) |
| `--tier-3` | white | Cold badge |

**Typography:** Two fonts only, loaded via `next/font/google` in `app/layout.tsx`:
- **Space Grotesk** (`font-sans`) — headings, numbers, body
- **Space Mono** (`font-mono`) — IDs, currency figures, agent codes (typewriter/ledger feel)

Small labels are always `text-xs font-black uppercase tracking-wider`.

**Signature visual motifs (defined once in CSS, reused everywhere):**
```css
/* Diagonal hazard stripes — used on the hero stat card */
.stripes-diagonal {
  background-image: repeating-linear-gradient(45deg, transparent, transparent 10px,
    rgba(0,0,0,0.06) 10px, rgba(0,0,0,0.06) 20px);
}
```

**The signature shadow** used on every card/button/table for depth (hard offset, no blur):
```
shadow-[8px_8px_0px_0px_rgba(0,0,0,1)]   /* hero card, table */
shadow-[6px_6px_0px_0px_rgba(0,0,0,1)]   /* stat cards */
shadow-[4px_4px_0px_0px_rgba(0,0,0,1)]   /* agent chip, active pill */
shadow-[3px_3px_0px_0px_rgba(0,0,0,1)]   /* invite button, invite toast */
```
On hover/active, shadows compress and elements physically shift (`-translate-x-0.5 -translate-y-0.5` or `translate-x-0.5 translate-y-0.5`) — simulating a button being "pressed into" its shadow.

`color-scheme: light` is forced at the CSS and `<meta>` level so the app never flips to a browser/OS dark mode — the brutalist palette is intentional and fixed.

---

## 2. Page Structure (`app/page.tsx` → `components/pipeline/pipeline-dashboard.tsx`)

The whole app is one client component, `PipelineDashboard`, rendered top-to-bottom as:

```
┌─────────────────────────────────────────────┐
│ HEADER (logo + product name / agent chip)    │
├─────────────────────────────────────────────┤
│ SUMMARY METRICS (hero card + 2 stat cards)    │
│ SUMMARY METRICS ROW 2 (3 stat cards)          │
├─────────────────────────────────────────────┤
│ SEGMENT FILTER PILLS         [invite toast]   │
├─────────────────────────────────────────────┤
│ MASTER DATA TABLE (10 clients, sortable feel) │
├─────────────────────────────────────────────┤
│ FOOTER (formula legend)                       │
└─────────────────────────────────────────────┘
```

### Header
- Black square logo mark (crosshair/plus icon in a `border-4 border-black bg-black` box) + wordmark **"PIPELINE.EV"** (`.EV` in muted gray) + subtitle **"Client Priority Console"**.
- Right side: an agent identity chip — black-bordered box with initials avatar (`RD`) in acid yellow + name **"R. Delgado — Senior Agent"**. Sits in its own bordered/shadowed pill.
- Bottom border is a thick `border-b-4 border-black` rule separating header from content.

### Summary Metrics (Requirement #1)
Two-row grid of stat cards, `grid-cols-1 md:grid-cols-2 lg:grid-cols-4`:

**Row 1:**
1. **Hero card** (spans 2 columns) — "Total Pipeline Value"
   - Diagonal stripe texture overlay (`.stripes-diagonal`)
   - Label in a small bordered chip
   - Huge number: `text-5xl → text-7xl font-bold` showing the currency-formatted sum of all clients' Expected Value
   - Sub-caption in an acid-yellow bordered chip: *"Sum of E(x) across 10 active clients"*
   - Heaviest shadow in the app (`8px_8px`)
2. **Total VIPs** stat card — count of Tier 1 clients, `emphasis` mode (acid-yellow background, black icon chip), star icon
3. **Avg. Buy Probability** stat card — average probability across all 10 clients as a %, target/crosshair icon

**Row 2 (3-column grid):**
4. **Tier 2 · Warm** count, clock icon
5. **Tier 3 · Cold** count, clock icon
6. **Total Property Value** — combined value of all target listings, target icon

Each `StatCard` (`components/pipeline/stat-card.tsx`) is a self-contained bordered block:
```tsx
<div className="border-4 border-black p-5 shadow-[6px_6px_0px_0px_rgba(0,0,0,1)]">
  <label>  {/* uppercase, bottom-border underline */}
  <icon-chip /> {/* black square, white or yellow icon */}
  <value />    {/* big bold number */}
  <detail />   {/* small muted caption */}
</div>
```

### Segment Filter (Requirement #2)
`SegmentPills` (`components/pipeline/segment-pills.tsx`) — four pill buttons, `role="tablist"`:

| Pill | Filters to |
|---|---|
| **All Clients** | Every client |
| **Tier 1 · VIP** | `probability >= 65%` |
| **Tier 2 · Warm** | `35% – 64%` |
| **Tier 3 · Cold** | `< 35%` |

Each pill shows a live count badge (e.g. `All Clients [10]`, `Tier 1 · VIP [5]`). The active pill is inverted to solid black with white text and is visually "pressed" (shifted up-left into its shadow); inactive pills are white and lift on hover.

Next to the pills, a **transient confirmation toast** appears after an invite is sent: an acid-yellow bordered chip reading *"Invite generated for [Client Name]"*.

### Master Data Table (Requirement #3)
`ClientTable` (`components/pipeline/client-table.tsx`) — a single `border-4 border-black` block with a scrollable `<table>` inside (`min-w-[880px]`, horizontal scroll on mobile). Header row is solid black with white uppercase text. Body rows alternate white / light-gray (`bg-secondary`) for scan-ability, separated by 2px black rules.

**Columns:**
| Column | Rendering |
|---|---|
| **Client** | Black square avatar with initials + name (bold) + `CLT-00X · Agent Name` in mono/muted below |
| **Target Property** | Plain bold text, e.g. "14 Cobalt Ridge, Aspen Heights" |
| **Property Value** | Right-aligned, mono font, currency |
| **Probability** | A mini black-bordered progress bar (filled black to the probability %) + mono percentage label |
| **Expected Value** | Highlighted in an acid-yellow bordered chip, mono font — this is the priority-sort signal |
| **Segment** | `TierBadge` — colored pill: **VIP** (yellow), **WARM** (black), **COLD** (white outline) |
| **Action** | Tier 1 rows only: **"Generate Invite"** button. All other rows show a muted em-dash `—` |

Rows are pre-sorted **descending by Expected Value** (highest-priority clients float to the top automatically) in `lib/pipeline-data.ts`.

### Generate Invite Button (Requirement #4)
Only rendered when `client.tier === "TIER_1"`. Behavior:
- Default state: solid black button, white uppercase text, `shadow-[3px_3px_0px_0px_rgba(0,0,0,1)]`, label **"Generate Invite"**.
- On click: shadow collapses and button shifts down-right (pressed effect), local state flips to `invited[client.id] = true`, label becomes **"Invite Sent"**, button turns white/muted and becomes `disabled`.
- Simultaneously triggers `onGenerateInvite(client)` in the parent, which populates the toast next to the filter pills: *"Invite generated for [Name]"*.

### Footer
Thin legend under a `border-t-4 border-black` rule: *"E(x) = P(Buy) × Property Value — Segmentation: Tier 1 ≥ 65% · Tier 2 35–64% · Tier 3 < 35%"* — states the exact math and thresholds driving the whole dashboard.

---

## 3. Data Model (`lib/pipeline-data.ts`)

10 realistic mock clients, generated from raw input and derived fields computed at module load:

```ts
export interface Client {
  id: string              // "CLT-001"
  name: string
  initials: string         // auto-derived from name
  property: string         // target listing address
  propertyValue: number    // USD
  probability: number      // 0–1
  expectedValue: number    // = round(probability * propertyValue)
  tier: "TIER_1" | "TIER_2" | "TIER_3"   // derived from probability
  agent: string
}
```

Tier thresholds:
```ts
function getTier(probability) {
  if (probability >= 0.65) return "TIER_1"  // VIP
  if (probability >= 0.35) return "TIER_2"  // WARM
  return "TIER_3"                            // COLD
}
```

**Sample rows** (sorted by Expected Value, descending):

| Client | Property | Value | Prob. | Expected Value | Tier |
|---|---|---|---|---|---|
| Fatima Al-Sayed | Penthouse, The Ashcombe | $4,800,000 | 68% | **$3,264,000** | VIP |
| Marcus Whitfield | 14 Cobalt Ridge, Aspen Heights | $2,450,000 | 91% | **$2,229,500** | VIP |
| Ilse van der Berg | 9 Meridian Court, Lakeside | $3,120,000 | 71% | **$2,215,200** | VIP |
| Cillian Boyle | 6 Foundry Loft, Old Mill District | $1,650,000 | 83% | **$1,369,500** | VIP |
| Priya Anand | Unit 22B, Harborview Towers | $1,180,000 | 78% | **$920,400** | VIP |
| Dominic Ferraro | 308 Willow Bend Lane | $640,000 | 52% | $332,800 | WARM |
| Grant Ellsworth | 77 Prairie Fields Rd | $890,000 | 41% | $364,900 | WARM |
| Renata Souza | 12 Copper Kettle Row | $525,000 | 33% | $173,250 | COLD |
| Owen Kowalski | 441 Birchwood Terrace | $415,000 | 24% | $99,600 | COLD |
| Yuki Tanaka | 203 Sable Point Drive | $275,000 | 12% | $33,000 | COLD |

Helper formatters also live here: `currency()` (Intl `en-US` USD, no decimals) and `percent()` (rounded whole-number %).

---

## 4. File Map

```
app/
  layout.tsx                  → fonts (Space Grotesk / Space Mono), metadata, forced light color-scheme
  page.tsx                    → renders <PipelineDashboard />
  globals.css                 → design tokens, stripe pattern, shadow/border system
components/pipeline/
  pipeline-dashboard.tsx       → page composition, derived totals, invite-toast state
  stat-card.tsx                → reusable bordered metric card
  segment-pills.tsx            → tier filter tabs with live counts
  client-table.tsx             → master data table + TierBadge + Generate Invite logic
lib/
  pipeline-data.ts              → Client type, mock data, tier logic, formatters
```

---

## 5. Interaction Summary

1. **Filter** — clicking a segment pill instantly filters the table client-side (no network calls); counts on each pill always reflect the full dataset regardless of active filter.
2. **Invite** — clicking "Generate Invite" on any VIP row disables that button, relabels it "Invite Sent," and surfaces a dismiss-free confirmation chip near the filters.
3. **Responsive** — grid stacks to 1 column on mobile, table becomes horizontally scrollable (`overflow-x-auto`, hidden scrollbar), header switches to stacked layout below `sm`.
4. **No external UI libraries** — every element (buttons, badges, table, cards) is hand-built with Tailwind only, per the constraint against shadcn/ui or other component kits.
