export type Tier = "TIER_1" | "TIER_2" | "TIER_3"

export interface Client {
  id: string
  name: string
  initials: string
  property: string
  propertyValue: number
  probability: number
  expectedValue: number
  tier: Tier
  agent: string
}

export const TIER_LABEL: Record<Tier, string> = {
  TIER_1: "TIER 1 — VIP",
  TIER_2: "TIER 2 — WARM",
  TIER_3: "TIER 3 — COLD",
}

export const TIER_SHORT: Record<Tier, string> = {
  TIER_1: "VIP",
  TIER_2: "WARM",
  TIER_3: "COLD",
}

function getTier(probability: number): Tier {
  if (probability >= 0.65) return "TIER_1"
  if (probability >= 0.35) return "TIER_2"
  return "TIER_3"
}

function initialsOf(name: string) {
  return name
    .split(" ")
    .map((part) => part[0])
    .join("")
    .toUpperCase()
    .slice(0, 2)
}

interface RawClient {
  name: string
  property: string
  propertyValue: number
  probability: number
  agent: string
}

const RAW_CLIENTS: RawClient[] = [
  { name: "Marcus Whitfield", property: "14 Cobalt Ridge, Aspen Heights", propertyValue: 2_450_000, probability: 0.91, agent: "R. Delgado" },
  { name: "Priya Anand", property: "Unit 22B, Harborview Towers", propertyValue: 1_180_000, probability: 0.78, agent: "T. Okafor" },
  { name: "Dominic Ferraro", property: "308 Willow Bend Lane", propertyValue: 640_000, probability: 0.52, agent: "R. Delgado" },
  { name: "Ilse van der Berg", property: "9 Meridian Court, Lakeside", propertyValue: 3_120_000, probability: 0.71, agent: "S. Nakamura" },
  { name: "Owen Kowalski", property: "441 Birchwood Terrace", propertyValue: 415_000, probability: 0.24, agent: "T. Okafor" },
  { name: "Fatima Al-Sayed", property: "Penthouse, The Ashcombe", propertyValue: 4_800_000, probability: 0.68, agent: "S. Nakamura" },
  { name: "Grant Ellsworth", property: "77 Prairie Fields Rd", propertyValue: 890_000, probability: 0.41, agent: "R. Delgado" },
  { name: "Renata Souza", property: "12 Copper Kettle Row", propertyValue: 525_000, probability: 0.33, agent: "T. Okafor" },
  { name: "Cillian Boyle", property: "6 Foundry Loft, Old Mill District", propertyValue: 1_650_000, probability: 0.83, agent: "S. Nakamura" },
  { name: "Yuki Tanaka", property: "203 Sable Point Drive", propertyValue: 275_000, probability: 0.12, agent: "R. Delgado" },
]

export const CLIENTS: Client[] = RAW_CLIENTS.map((c, i) => {
  const expectedValue = Math.round(c.probability * c.propertyValue)
  return {
    id: `CLT-${String(i + 1).padStart(3, "0")}`,
    name: c.name,
    initials: initialsOf(c.name),
    property: c.property,
    propertyValue: c.propertyValue,
    probability: c.probability,
    expectedValue,
    tier: getTier(c.probability),
    agent: c.agent,
  }
}).sort((a, b) => b.expectedValue - a.expectedValue)

export const currency = (value: number) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value)

export const percent = (value: number) => `${Math.round(value * 100)}%`

export interface Property {
  id: string
  name: string
  address: string
  value: number
  status: "LISTED" | "PENDING" | "UNDER OFFER"
}

export const PROPERTIES: Property[] = [
  {
    id: "PROP-001",
    name: "Cobalt Ridge Estate",
    address: "14 Cobalt Ridge, Aspen Heights",
    value: 2_450_000,
    status: "UNDER OFFER",
  },
  {
    id: "PROP-002",
    name: "Harborview Towers",
    address: "Unit 22B, Harborview Towers",
    value: 1_180_000,
    status: "PENDING",
  },
  {
    id: "PROP-003",
    name: "The Ashcombe Penthouse",
    address: "Penthouse, The Ashcombe",
    value: 4_800_000,
    status: "LISTED",
  },
]
