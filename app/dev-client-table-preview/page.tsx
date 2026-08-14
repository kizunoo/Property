"use client"

import { ClientTable } from "@/components/pipeline/client-table"
import type { DeduplicatedClient } from "@/lib/pipeline-data"

const NAMES = [
  "Alexandra Montgomery-Whitfield",
  "Bo Chen",
  "Priyanka Ramachandran Iyer",
  "J. Kim",
  "Christopher Alexander Fitzgerald III",
  "Wei",
  "Fatima Al-Rashid Hussaini",
  "Sam",
]

const PROPERTIES = [
  "12 Jalan Bukit Bintang, The Pavilion Residences Tower B, Unit 45-03",
  "88 Ampang",
  "The Establishment KLCC, Menara South Wing, Level 32",
  "7 Damansara Heights Enclave",
]

const NEIGHBORHOODS = ["KLCC", "Bangsar", "Mont Kiara", "Damansara Heights", "Bukit Bintang"]

function makeMockClient(i: number): DeduplicatedClient {
  const name = NAMES[i % NAMES.length]
  const property = PROPERTIES[i % PROPERTIES.length]
  const tiers: DeduplicatedClient["tier"][] = ["TIER_1", "TIER_2", "TIER_3"]
  return {
    clientId: `mock-${i}`,
    name,
    initials: name
      .split(" ")
      .map((p) => p[0])
      .join("")
      .toUpperCase()
      .slice(0, 2),
    tier: tiers[i % tiers.length],
    statedBudget: 2_000_000,
    preferredNeighborhood: NEIGHBORHOODS[i % NEIGHBORHOODS.length],
    pastViewings: i % 5,
    bestMatch: {
      evalId: `eval-${i}`,
      propertyId: `prop-${i}`,
      property,
      propertyValue: 1_500_000 + i * 137_000,
      probability: 0.35 + ((i * 7) % 60) / 100,
      expectedValue: 500_000 + i * 42_000,
      neighborhood: NEIGHBORHOODS[i % NEIGHBORHOODS.length],
    },
    otherMatchCount: i % 4,
    allMatches: [],
  }
}

const MOCK_CLIENTS: DeduplicatedClient[] = Array.from({ length: 28 }, (_, i) => makeMockClient(i))

export default function DevClientTablePreview() {
  return (
    <main className="min-h-screen bg-background p-8">
      <div className="mx-auto max-w-6xl">
        <ClientTable
          clients={MOCK_CLIENTS}
          onGenerateInvite={() => {}}
          onSelect={() => {}}
        />
        <div className="h-[1400px]" />
      </div>
    </main>
  )
}
